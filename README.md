# PDF Maker

Turn a folder of pictures into a PDF — one picture per page (or three
side-by-side on a landscape page), in order. Also combines a folder of PDFs
into a single file. Built for macOS: non-technical users just double-click a
launcher; everything is also available from the command line.

## What's in the box

| Item | What it is |
| --- | --- |
| **Make PDF.command** | Double-click launcher: pictures → PDF. Asks a few plain-English questions (pictures per page, margins, file size, splitting). |
| **Combine PDFs.command** | Double-click launcher: merges every PDF in a folder into one, in order. |
| `generate_pdf.py` | The picture-to-PDF engine (Pillow + img2pdf). |
| `combine_pdfs.py` | The PDF-merging engine (pypdf). |
| `pictures/` | Three sample images so you can try it immediately. |
| **READ ME FIRST.html** | A friendly illustrated guide for non-technical users. |

The launchers set up a private virtual environment (`.venv/`) on first run and
install their own dependencies — nothing is installed system-wide. To uninstall,
delete the folder.

## Prerequisites

PDF Maker needs **Python 3**. Everything else it fetches for itself on first run.

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

Check it worked with `python3 --version` — any Python 3.9 or newer is fine.

## Quick start (double-click)

1. Install Python 3 (see Prerequisites above) — one time only.
2. Put your pictures in the `pictures` folder (or have any folder ready).
3. Double-click **Make PDF.command** and answer the prompts.
   (First run: right-click → Open to get past Gatekeeper.)

The PDF is saved next to your pictures folder. See **READ ME FIRST.html** for
the full guide, including HEIC conversion tips and troubleshooting.

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
