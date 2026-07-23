#!/usr/bin/env python3
"""A small, dependency-free progress bar that behaves on macOS Terminal and
Windows Command Prompt alike.

The portability rules that keep it from turning into garbage on a legacy
console are the whole point of this file:

  * Redraw in place with a bare carriage return (``\\r``) and overwrite the old
    line with spaces — never emit ANSI cursor/erase codes, which an old
    cmd.exe prints literally as ``[K`` and friends.
  * Use Unicode block characters for a smooth bar only when the output stream
    can actually encode them (a UTF-8 Terminal). On a legacy code page it falls
    back to an ASCII ``#`` bar instead of mojibake.
  * Use colour only on a real TTY, and on Windows only after switching the
    console into virtual-terminal mode — a call that fails cleanly on Windows 7
    and 8, where we simply stay monochrome.
  * Disable itself entirely when the stream is not a TTY (piped or redirected),
    so log files don't fill up with carriage returns.

Each engine creates one bar per output file and drives it with step()/note()/
close(). If this module is ever missing, the engines fall back to a no-op, so
nothing breaks.
"""
from __future__ import annotations

import os
import shutil
import sys
import time

_SPIN_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPIN_ASCII = "|/-\\"


def _can_encode(text: str, stream) -> bool:
    """True if `text` survives the stream's encoding (so it won't crash write)."""
    enc = getattr(stream, "encoding", None) or "ascii"
    try:
        text.encode(enc)
        return True
    except (UnicodeError, LookupError):
        return False


def _enable_ansi(stream) -> bool:
    """Best-effort: return True if ANSI colour is safe to emit on `stream`."""
    if not getattr(stream, "isatty", lambda: False)():
        return False
    if os.name != "nt":
        return True  # POSIX terminals honour ANSI on a TTY
    # Windows 10+: try to switch the console into virtual-terminal mode. This
    # fails cleanly on older Windows, where we just go without colour.
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11 if stream is sys.stdout else -12)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(kernel32.SetConsoleMode(
            handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False


class ProgressBar:
    """Live one-line progress bar; safe to use even when output isn't a terminal."""

    def __init__(self, total, label="Working", stream=None):
        self.total = max(0, int(total))
        self.label = label
        self.stream = stream if stream is not None else sys.stdout
        self.count = 0
        self.enabled = self.total > 0 and getattr(
            self.stream, "isatty", lambda: False)()

        self._spin = 0
        self._last_len = 0
        self._last_draw = -1.0
        self._suffix = ""
        self._closed = False

        # Pick the fanciest glyph set the console can actually render.
        if self.enabled and _can_encode("█▏▕…⠋", self.stream):
            self._full, self._parts, self._empty = "█", "▏▎▍▌▋▊▉", " "
            self._lb, self._rb, self._ell = "▕", "▏", "…"
            self._spinner = _SPIN_UNICODE
        else:
            self._full, self._parts, self._empty = "#", "", "-"
            self._lb, self._rb, self._ell = "[", "]", "..."
            self._spinner = _SPIN_ASCII

        self._color = _enable_ansi(self.stream)

    # -- public API ----------------------------------------------------------
    def step(self, item="", plain=None):
        """Advance one unit. `item` labels the current work (e.g. a filename).
        `plain`, if given, prints only when the bar is disabled (non-TTY)."""
        self.count += 1
        self._suffix = ""
        if self.enabled:
            self._draw(self._safe(item))
        elif plain is not None:
            print(plain, file=self.stream)

    def note(self, text):
        """Swap the trailing filename for a status word (e.g. 'assembling PDF')."""
        if self.enabled:
            self._suffix = text
            self._draw(text, force=True)

    def log(self, msg):
        """Print a line above the bar without disturbing it (used for warnings)."""
        if not self.enabled:
            print(msg, file=self.stream)
            return
        self._wipe()
        print(msg, file=self.stream)
        self._last_len = 0
        self._draw(self._suffix, force=True)

    def close(self):
        """Erase the bar and leave the cursor at the start of a clean line."""
        if self._closed:
            return
        self._closed = True
        if self.enabled:
            self._wipe()
            self.stream.flush()

    # -- internals -----------------------------------------------------------
    def _wipe(self):
        self.stream.write("\r" + " " * self._last_len + "\r")

    def _safe(self, item):
        """Scrub a filename down to what the stream can encode (no crashes)."""
        if not item:
            return ""
        enc = getattr(self.stream, "encoding", None) or "utf-8"
        return item.encode(enc, "replace").decode(enc, "replace")

    def _draw(self, item="", force=False):
        now = time.monotonic()
        if (not force and self.count < self.total
                and now - self._last_draw < 0.05):
            return  # throttle to ~20 redraws/sec so huge batches stay snappy
        self._last_draw = now

        done = self.count >= self.total
        self._spin = (self._spin + 1) % len(self._spinner)
        spin = " " if done else self._spinner[self._spin]
        frac = 1.0 if self.total == 0 else min(1.0, self.count / self.total)
        pct = int(frac * 100)

        cols = shutil.get_terminal_size((80, 20)).columns
        head = f"  {self.label} {spin}  {pct:3d}% "
        tail = f" {self.count}/{self.total}"
        avail = cols - len(head) - len(tail) - 2
        if avail < 8:
            # Terminal too narrow for a bar — show a compact status instead.
            line = f"  {self.label} {spin} {pct:3d}% {self.count}/{self.total}"
            line = line[:max(0, cols - 1)]
            self._blit(line, line)
            return

        barlen = max(6, min(28, avail - 12))  # leave room for the item name
        body = self._bar_body(frac, barlen)
        bar_plain = self._lb + body + self._rb

        room = cols - len(head) - len(bar_plain) - len(tail) - 2
        item_seg = ""
        if item and room >= 4:
            if len(item) > room:
                item = self._ell + item[-(room - len(self._ell)):]
            item_seg = "  " + item

        plain = head + bar_plain + tail + item_seg
        if self._color:
            bar_out = f"{self._lb}\033[36m{body}\033[0m{self._rb}"
        else:
            bar_out = bar_plain
        self._blit(plain, head + bar_out + tail + item_seg)

    def _blit(self, plain, colored):
        pad = " " * max(0, self._last_len - len(plain))
        try:
            self.stream.write("\r" + colored + pad)
            self.stream.flush()
        except Exception:
            return
        self._last_len = len(plain)

    def _bar_body(self, frac, barlen):
        filled = frac * barlen
        whole = int(filled)
        if whole >= barlen:
            return self._full * barlen
        body = self._full * whole
        rem = filled - whole
        if self._parts and rem > 0:
            body += self._parts[min(len(self._parts) - 1, int(rem * len(self._parts)))]
        elif rem >= 0.5:
            body += self._full
        else:
            body += self._empty
        return body + self._empty * (barlen - len(body))
