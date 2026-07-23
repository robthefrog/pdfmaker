#!/bin/bash
# ============================================================
#  Combine PDFs — double-click to merge every PDF in a folder
#  into a single PDF file (kept in order).
#
#  The first time you run it, it quietly sets itself up
#  (needs an internet connection just that once). After
#  that it works offline. It shares the same private setup
#  as the "Make PDF" launcher next to it.
# ============================================================

# Everything below is relative to THIS folder (the one holding this launcher),
# so the whole folder can be moved or copied anywhere and still work.
# Resolve that folder to an absolute path (and handle spaces in the path).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

echo "============================================"
echo "   Combine PDFs"
echo "============================================"
echo

# --- 1. Make sure Python 3 is available -------------------------------------
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

# --- 2. First-run setup: a private, self-contained environment --------------
# Shares the same .venv as the "Make PDF" launcher; just makes sure the PDF
# merging component (pypdf) is present too.
VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import pypdf" >/dev/null 2>&1; then
  echo "Setting things up for the first time (about a minute)..."
  if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV" || { echo "Setup failed creating the environment."; read -n 1 -s -r -p "Press any key."; exit 1; }
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
  fi
  if ! "$VENV/bin/python" -m pip install --quiet pypdf; then
    echo
    echo "Couldn't download the needed components. Please check your"
    echo "internet connection and try again."
    read -n 1 -s -r -p "Press any key to close this window."
    exit 1
  fi
  echo "All set!"
  echo
fi

# --- 3. Choose the folder of PDFs -------------------------------------------
if [ "$#" -ge 1 ] && [ -d "$1" ]; then
  FOLDER="$1"
else
  echo "Which folder of PDFs should I combine into one?"
  echo "   - DRAG the folder into this window and press Return, or"
  echo "   - just press Return to use the 'pictures' folder next to this launcher."
  echo
  printf "Folder: "
  read -r FOLDER
fi

# Tidy up a dragged-in or pasted path (remove escaping and surrounding quotes).
FOLDER="${FOLDER//\\/}"
FOLDER="${FOLDER#\"}"; FOLDER="${FOLDER%\"}"
FOLDER="${FOLDER#\'}"; FOLDER="${FOLDER%\'}"
# Strip leading whitespace (never part of a real path) and a single trailing slash.
FOLDER="$(printf '%s' "$FOLDER" | sed -e 's/^[[:space:]]*//')"
FOLDER="${FOLDER%/}"

# Recover from lost trailing whitespace. Dragging a folder whose name ends in a
# space (e.g. "TJ Text Now ") loses that space by the time we get here, because
# `read` trims trailing whitespace off the line. If the path as given isn't a
# real folder, look in its parent for a folder whose name matches once trailing
# whitespace is ignored, and use that instead.
if [ -n "$FOLDER" ] && [ ! -d "$FOLDER" ]; then
  PARENT="$(dirname "$FOLDER")"
  BASE="$(basename "$FOLDER")"
  BASE="$(printf '%s' "$BASE" | sed -e 's/[[:space:]]*$//')"
  if [ -d "$PARENT" ]; then
    for ENTRY in "$PARENT"/*; do
      [ -d "$ENTRY" ] || continue
      ENAME="$(basename "$ENTRY")"
      ENAME="$(printf '%s' "$ENAME" | sed -e 's/[[:space:]]*$//')"
      if [ "$ENAME" = "$BASE" ]; then
        FOLDER="$ENTRY"
        break
      fi
    done
  fi
fi

# Empty answer -> use the built-in "pictures" folder.
if [ -z "$FOLDER" ]; then
  FOLDER="$DIR/pictures"
  mkdir -p "$FOLDER"
fi

if [ ! -d "$FOLDER" ]; then
  echo
  echo "I couldn't find that folder:"
  echo "   $FOLDER"
  echo "Please try again and drag the folder in, or press Return for 'pictures'."
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
fi

# --- 4. Ask which order to combine in ---------------------------------------
OPTS=()
echo "In what order should I combine the PDFs?"
echo "   1) By name  - by the number in each filename (part1, part2, ...)  (default)"
echo "   2) By date  - oldest file first (handy when names have no order)"
printf "Choose 1 or 2 [1]: "
read -r ORDER
echo
case "$ORDER" in
  2) OPTS+=(--order date) ;;
  *) : ;;  # default: by name
esac

# --- 5. Combine (saved right next to the PDFs folder) -----------------------
OUT="$FOLDER-combined.pdf"
echo "Combining the PDFs in:"
echo "   $FOLDER"
echo
if "$VENV/bin/python" "$DIR/combine_pdfs.py" --src "$FOLDER" --out "$OUT" "${OPTS[@]}"; then
  echo
  echo "Done!  Your combined PDF is here:"
  echo "   $OUT"
  open -R "$OUT" >/dev/null 2>&1 || true
else
  echo
  echo "Something went wrong - please read the message just above for the reason."
  echo "(A common cause is a folder with no .pdf files in it.)"
fi

echo
read -n 1 -s -r -p "Press any key to close this window."
exit 0
