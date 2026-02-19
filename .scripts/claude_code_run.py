#!/usr/bin/env python3
"""claude_code_run.py

Wrap the Claude Code CLI with a pseudo-terminal (PTY).

Why:
- Some CLIs behave differently when stdout/stderr are not a TTY.
- Forcing a PTY helps avoid "waiting for a TTY" style hangs in automation.

This script streams the child PTY output to this process stdout and returns
Claude's exit code.

Usage:
  ./.scripts/claude_code_run.py -- -p "hello"
  ./.scripts/claude_code_run.py --cwd /path/to/repo --timeout 600 -- -c -p "continue"
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
from typing import Optional


class _AnsiStripper:
    """Best-effort ANSI escape sequence stripper.

    Designed for streaming: maintains state across chunks.
    """

    def __init__(self) -> None:
        self._state = "text"  # text|esc|csi|osc|dcs
        self._osc_esc = False
        self._dcs_esc = False

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        i = 0
        n = len(data)

        while i < n:
            b = data[i]

            if self._state == "text":
                if b == 0x1B:  # ESC
                    self._state = "esc"
                else:
                    out.append(b)
                i += 1
                continue

            if self._state == "esc":
                if i >= n:
                    break
                b2 = data[i]

                if b2 == ord("["):
                    self._state = "csi"
                elif b2 == ord("]"):
                    self._state = "osc"
                    self._osc_esc = False
                elif b2 == ord("P"):
                    self._state = "dcs"
                    self._dcs_esc = False
                else:
                    # Single-character escape sequences like ESC ( B
                    self._state = "text"
                i += 1
                continue

            if self._state == "csi":
                # Consume until final byte in 0x40-0x7E.
                if 0x40 <= b <= 0x7E:
                    self._state = "text"
                i += 1
                continue

            if self._state == "osc":
                # OSC ends with BEL or ST (ESC \\).
                if self._osc_esc:
                    if b == ord("\\"):
                        self._state = "text"
                    self._osc_esc = False
                    i += 1
                    continue

                if b == 0x07:  # BEL
                    self._state = "text"
                elif b == 0x1B:  # ESC
                    self._osc_esc = True
                i += 1
                continue

            if self._state == "dcs":
                # DCS ends with ST (ESC \\).
                if self._dcs_esc:
                    if b == ord("\\"):
                        self._state = "text"
                    self._dcs_esc = False
                    i += 1
                    continue

                if b == 0x1B:
                    self._dcs_esc = True
                i += 1
                continue

        return bytes(out)


def _get_winsz(fd: int) -> tuple[int, int, int, int]:
    data = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    rows, cols, xpix, ypix = struct.unpack("HHHH", data)
    return rows, cols, xpix, ypix


def _set_winsz(fd: int, winsz: tuple[int, int, int, int]) -> None:
    rows, cols, xpix, ypix = winsz
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, xpix, ypix))


def _kill_process_group(p: subprocess.Popen[bytes], sig: int) -> None:
    try:
        pgid = os.getpgid(p.pid)
    except Exception:
        return
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def run_with_pty(
    cmd: list[str],
    cwd: Optional[str],
    timeout_s: Optional[float],
    env: dict[str, str],
    strip_ansi: bool,
) -> int:
    master_fd, slave_fd = pty.openpty()

    # Best-effort: propagate current terminal size to the PTY.
    try:
        if sys.stdin.isatty():
            _set_winsz(slave_fd, _get_winsz(sys.stdin.fileno()))
    except Exception:
        pass

    p = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=cwd,
        env=env,
        start_new_session=True,  # create a new process group for reliable signaling
        text=False,
    )

    os.close(slave_fd)

    stdin_fd: Optional[int] = None
    raw_mode = False
    old_tty_attrs = None

    if sys.stdin.isatty():
        stdin_fd = sys.stdin.fileno()
        try:
            old_tty_attrs = termios.tcgetattr(stdin_fd)
            tty.setraw(stdin_fd)
            raw_mode = True
        except Exception:
            stdin_fd = None

        def _on_winch(_signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
            try:
                _set_winsz(master_fd, _get_winsz(stdin_fd))  # type: ignore[arg-type]
            except Exception:
                return

        try:
            signal.signal(signal.SIGWINCH, _on_winch)
        except Exception:
            pass

    stripper = _AnsiStripper() if strip_ansi else None

    try:
        start = time.monotonic()
        while True:
            if timeout_s is not None and (time.monotonic() - start) > timeout_s:
                _kill_process_group(p, signal.SIGTERM)
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _kill_process_group(p, signal.SIGKILL)
                return 124

            rlist: list[int] = [master_fd]
            if stdin_fd is not None:
                rlist.append(stdin_fd)

            ready, _, _ = select.select(rlist, [], [], 0.1)

            if master_fd in ready:
                try:
                    data = os.read(master_fd, 4096)
                except OSError as e:
                    # When the child exits, PTY reads can raise EIO.
                    if e.errno == errno.EIO:
                        data = b""
                    else:
                        raise

                if data:
                    if stripper is not None:
                        data = stripper.feed(data)
                    if data:
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                else:
                    # No more output. If process is done, exit; otherwise keep looping.
                    if p.poll() is not None:
                        break

            if stdin_fd is not None and stdin_fd in ready:
                try:
                    in_data = os.read(stdin_fd, 1024)
                except OSError:
                    in_data = b""

                if in_data:
                    try:
                        os.write(master_fd, in_data)
                    except OSError:
                        pass

            if p.poll() is not None:
                # Drain any remaining output quickly.
                try:
                    while True:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        if stripper is not None:
                            data = stripper.feed(data)
                        if data:
                            sys.stdout.buffer.write(data)
                            sys.stdout.buffer.flush()
                except OSError:
                    pass
                break

        return p.wait()

    finally:
        try:
            os.close(master_fd)
        except Exception:
            pass

        if raw_mode and stdin_fd is not None and old_tty_attrs is not None:
            try:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty_attrs)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--cwd", default=None, help="Working directory")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Timeout in seconds (exit 124 on timeout)",
    )
    parser.add_argument(
        "--claude-bin",
        default=os.environ.get("CLAUDE_BIN", "claude"),
        help="Claude Code executable (default: claude)",
    )
    parser.add_argument(
        "--strip-ansi",
        action="store_true",
        default=True,
        help="Strip ANSI escape sequences from output (default: on)",
    )
    parser.add_argument(
        "--keep-ansi",
        action="store_false",
        dest="strip_ansi",
        help="Do not strip ANSI escape sequences",
    )
    parser.add_argument(
        "claude_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to claude; prefix with -- to separate",
    )

    args = parser.parse_args()

    claude_args = list(args.claude_args)
    if claude_args and claude_args[0] == "--":
        claude_args = claude_args[1:]

    if not claude_args:
        parser.error("No claude args provided. Example: -- -p 'hello'")

    env = dict(os.environ)
    # Keep it predictable in automation.
    env.setdefault("TERM", env.get("TERM", "xterm-256color"))

    cmd = [args.claude_bin] + claude_args
    return run_with_pty(
        cmd=cmd,
        cwd=args.cwd,
        timeout_s=args.timeout,
        env=env,
        strip_ansi=args.strip_ansi,
    )


if __name__ == "__main__":
    raise SystemExit(main())
