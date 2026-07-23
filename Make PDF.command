#!/bin/bash
# ============================================================
#  PDF Maker — double-click to turn a folder of pictures
#  into a single PDF (one picture per page, in order).
#
#  The first time you run it, it quietly sets itself up
#  (needs an internet connection just that once). After
#  that it works offline.
# ============================================================

# Everything below is relative to THIS folder (the one holding this launcher),
# so the whole "PDF Maker" folder can be moved or copied anywhere and still work.
# Resolve that folder to an absolute path (and handle spaces in the path).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

echo "============================================"
echo "   PDF Maker"
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
VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import img2pdf, PIL" >/dev/null 2>&1; then
  echo "Setting things up for the first time (about a minute)..."
  python3 -m venv "$VENV" || { echo "Setup failed creating the environment."; read -n 1 -s -r -p "Press any key."; exit 1; }
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  if ! "$VENV/bin/python" -m pip install --quiet img2pdf Pillow; then
    echo
    echo "Couldn't download the needed components. Please check your"
    echo "internet connection and try again."
    read -n 1 -s -r -p "Press any key to close this window."
    exit 1
  fi
  echo "All set!"
  echo
fi

# --- 3. Choose the folder of pictures ---------------------------------------
if [ "$#" -ge 1 ] && [ -d "$1" ]; then
  FOLDER="$1"
else
  echo "Which folder of pictures should I turn into a PDF?"
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

# --- 4. Ask about layout, note margins and file size -----------------------
OPTS=()

echo "How many pictures per page?"
echo "   1) One   - one picture per page, filling it        (default)"
echo "   3) Three - three side-by-side on a landscape page  (great for phone screenshots)"
printf "Choose 1 or 3 [1]: "
read -r PERPAGE
echo

if [ "$PERPAGE" = "3" ]; then
  OPTS+=(--per-page 3)
  echo "How much space around and between the three pictures?"
  echo "   1) Half a centimetre   (default)"
  echo "   2) One centimetre      - a bit more breathing room"
  echo "   3) None                - the pictures sit edge to edge"
  printf "Choose 1, 2 or 3 [1]: "
  read -r GAP
  case "$GAP" in
    2) OPTS+=(--gap 1.0) ;;
    3) OPTS+=(--gap 0) ;;
    *) : ;;  # default: half a centimetre (built into the engine)
  esac
  echo
else
  echo "How much blank margin do you want for handwriting notes?"
  echo "   1) None  - the picture fills the whole page   (default)"
  echo "   2) Some  - a half-inch border on Letter paper"
  echo "   3) Lots  - a one-inch border on Letter paper"
  printf "Choose 1, 2 or 3 [1]: "
  read -r NOTES
  case "$NOTES" in
    2) OPTS+=(--page letter --margin 0.5) ;;
    3) OPTS+=(--page letter --margin 1.0) ;;
    *) : ;;  # default: fill the page
  esac
  echo
fi

echo "Do you want a smaller PDF file (easier to email or upload)?"
echo "   1) No       - best quality, largest file   (default)"
echo "   2) Smaller  - good quality, much smaller file"
echo "   3) Smallest - still readable, tiny file"
printf "Choose 1, 2 or 3 [1]: "
read -r SIZE
case "$SIZE" in
  2) OPTS+=(--max-height 1400 --quality 70) ;;
  3) OPTS+=(--max-height 1000 --quality 55) ;;
  *) : ;;  # default: best quality
esac
echo

echo "How many PDF files do you want? Splitting divides the pictures evenly"
echo "(keeping their order) - handy when one file is too big to email or print."
echo "   1 = one PDF    (default)"
echo "   2 = two PDFs"
echo "   4 = four PDFs"
printf "Type 1, 2 or 4 [1]: "
read -r SPLIT
PARTS=1
case "$SPLIT" in
  2) OPTS+=(--parts 2); PARTS=2 ;;
  4) OPTS+=(--parts 4); PARTS=4 ;;
  *) : ;;  # default: one PDF
esac
echo

# --- 6. Make the PDF (saved right next to the pictures folder) --------------
OUT="$FOLDER.pdf"
echo "Making your PDF from the pictures in:"
echo "   $FOLDER"
echo
if "$VENV/bin/python" "$DIR/generate_pdf.py" --src "$FOLDER" --out "$OUT" "${OPTS[@]}"; then
  echo
  if [ "$PARTS" -gt 1 ]; then
    echo "Done!  Your $PARTS PDF files are saved next to the pictures folder"
    echo "(their names end in _partX_of_${PARTS}.pdf - see the list just above)."
    open "$(dirname "$OUT")" >/dev/null 2>&1 || true
  else
    echo "Done!  Your PDF is here:"
    echo "   $OUT"
    open -R "$OUT" >/dev/null 2>&1 || true
  fi
else
  echo
  echo "Something went wrong - please read the message just above for the reason."
  echo "(A common cause is a folder with no .jpg/.png pictures in it.)"
fi

echo
read -n 1 -s -r -p "Press any key to close this window."
exit 0
