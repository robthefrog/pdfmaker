# PDF Maker

Turn a folder of pictures into a PDF — one picture per page (or three
side-by-side on a landscape page), in order. Also combines a folder of PDFs
into a single file. Works on macOS and Windows: non-technical users just
double-click a launcher; everything is also available from the command line.

## What's in the box

| Item | What it is |
| --- | --- |
| **Make PDF.command** / **Make PDF.bat** | Double-click launchers (macOS / Windows): pictures → PDF. Asks a few plain-English questions (pictures per page, margins, file size, splitting). On Windows you can also drag a folder onto the icon. |
| **Combine PDFs.command** / **Combine PDFs.bat** | Double-click launchers (macOS / Windows): merges every PDF in a folder into one, in order. |
| `launcher.py` | The shared interactive flow behind all four launchers — first-run setup, the questions, and revealing the finished PDF. |
| `generate_pdf.py` | The picture-to-PDF engine (Pillow + img2pdf). |
| `combine_pdfs.py` | The PDF-merging engine (pypdf). |
| `pictures/` | Three sample images so you can try it immediately. |
| [**READ ME FIRST.md**](<READ ME FIRST.md>) | A friendly step-by-step guide for non-technical users. |

The launchers set up a private virtual environment (`.venv/`) on first run and
install their own dependencies — nothing is installed system-wide. To uninstall,
delete the folder.

## Prerequisites

PDF Maker needs **Python 3** (3.9 or newer). Everything else it fetches for
itself on first run.

### macOS

**Option A — python.org installer** (simplest, no terminal needed):
download and run the ["macOS 64-bit universal2 installer"](https://www.python.org/downloads/macos/).

**Option B — Homebrew** (if you prefer the terminal). First install
[Homebrew](https://brew.sh) if you don't have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

then install Python with it:

```bash
brew install python
```

Check it worked with `python3 --version`.

### Windows

Download the latest ["Windows installer (64-bit)"](https://www.python.org/downloads/windows/)
and run it. **On the first screen tick "Add python.exe to PATH"**, then click
*Install Now*. Check it worked by opening Command Prompt and running
`py --version`.

## Quick start (double-click)

1. Install Python 3 (see Prerequisites above) — one time only.
2. Put your pictures in the `pictures` folder (or have any folder ready).
3. Double-click **Make PDF.command** (macOS) or **Make PDF.bat** (Windows) and
   answer the prompts. First run only: on macOS right-click → Open to get past
   Gatekeeper; on Windows click "More info" → "Run anyway" if SmartScreen asks.

The PDF is saved next to your pictures folder. See
[**READ ME FIRST.md**](<READ ME FIRST.md>) for the full guide, including HEIC
conversion tips and troubleshooting.

## Command line

```bash
pip install img2pdf Pillow pypdf   # or let the launchers make their own .venv

# One picture per page, lossless:
python3 generate_pdf.py --src "path/to/pictures" --out out.pdf

# Letter paper with a margin for handwritten notes, compressed:
python3 generate_pdf.py --src "path/to/pictures" --page letter --margin 0.75 --max-height 1200 --quality 65

# Three phone screenshots per landscape page, half-centimetre gaps:
python3 generate_pdf.py --src "path/to/pictures" --per-page 3 --gap 0.5

# Split evenly into 3 PDFs (print shops, email limits):
python3 generate_pdf.py --src "path/to/pictures" --parts 3

# Merge a folder of PDFs, ordered by the number in each filename:
python3 combine_pdfs.py --src "path/to/pdfs"
```

Run either script with `--help` for every option.

## Behaviour worth knowing

- Files are ordered by the number embedded in the filename (`part_2` before
  `part_10`, no zero-padding needed); files without numbers sort alphabetically after.
- Unreadable or corrupt files are skipped with a WARNING naming the exact file —
  the PDF is still built from the rest.
- Supported picture types: JPG, PNG, BMP, GIF, TIFF, WEBP — and HEIC/HEIF if
  `pillow-heif` is installed.

## License

[MIT](LICENSE)
