#!/bin/bash
# ============================================================
#  Combine PDFs — double-click to merge every PDF in a folder
#  into a single PDF file (kept in order).
#
#  The first time you run it, it quietly sets itself up
#  (needs an internet connection just that once). After
#  that it works offline. It shares the same private setup
#  as the "Make PDF" launcher next to it.
#
#  All the real work happens in launcher.py, shared with the
#  Windows launcher (Combine PDFs.bat).
# ============================================================

# Run from THIS folder so the whole folder can be moved or copied anywhere and
# still work (handles spaces in the path).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 isn't installed yet — you only need to do this once."
  echo
  echo "  1. Go to:  https://www.python.org/downloads/macos/"
  echo "  2. Download the 'macOS 64-bit universal2 installer'."
  echo "  3. Open it and click Continue / Agree / Install."
  echo "  4. Double-click this launcher again."
  echo
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
fi

exec python3 "$DIR/launcher.py" combine "$@"
