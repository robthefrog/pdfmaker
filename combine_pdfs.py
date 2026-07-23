#!/usr/bin/env python3
"""Combine every PDF in a folder into a single PDF, in order.

Reads the .pdf files from a source directory, orders them by the number embedded
in each filename (so part_2 lands before part_10 regardless of zero-padding, and
"Chapter 1", "Chapter 2" ... come out in the right order), and concatenates them
back-to-back into one output PDF. The pages of each file are kept intact and in
their original sequence.

Ordering
    --order name (default) sorts by filename the same way the picture tool does:
    by the number in the name first, then alphabetically. --order date sorts by
    each file's last-modified time (oldest first) instead — handy when the names
    carry no useful order but the files were saved in the sequence you want.

Robustness
    If one PDF is corrupt, unreadable, or password-protected in a way we can't
    open, it is skipped with a clear WARNING naming that exact file, and the
    combined PDF is still built from the rest — you are never left guessing which
    file was the problem. The output file itself is never swallowed back in, even
    if it happens to sit inside the source folder.

Usage:
    python combine_pdfs.py --src "/path/to/folder"
    python combine_pdfs.py --src "/path/to/folder" --out "/path/to/all.pdf"
    python combine_pdfs.py --src "/path/to/folder" --order date
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys

# Keep pypdf's own low-level chatter ("invalid pdf header", "EOF marker not
# found") out of the way — we report skipped files with our own clean WARNING.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.errors import PdfReadError
except ImportError:
    sys.exit(
        "error: the 'pypdf' package is not installed.\n"
        "       Install it with:  python -m pip install pypdf"
    )

# The live progress bar lives alongside this script; if it's ever missing fall
# back to a silent no-op so the tool still runs exactly as before.
try:
    from progress import ProgressBar
except Exception:
    class ProgressBar:  # minimal stand-in: no bar, original behaviour
        enabled = False

        def __init__(self, *a, **k):
            self.enabled = False

        def step(self, item="", plain=None):
            if plain is not None:
                print(plain)

        def note(self, text):
            pass

        def log(self, msg):
            print(msg, file=sys.stderr)

        def close(self):
            pass


def natural_key(path: str):
    """Order by the last run of digits in the filename, then the name itself.

    Files that contain a number sort first (numerically); files without one sort
    afterwards alphabetically. This keeps part_2 before part_10 even if the names
    were not zero-padded.
    """
    name = os.path.basename(path)
    nums = re.findall(r"\d+", name)
    if nums:
        return (0, int(nums[-1]), name.lower())
    return (1, 0, name.lower())


def collect_pdfs(src_dir: str, out_path: str, order: str) -> list[str]:
    """Return the source .pdf files in the chosen order, excluding the output."""
    if not os.path.isdir(src_dir):
        sys.exit(f"error: source folder not found: {src_dir!r}")
    out_abs = os.path.abspath(out_path)
    files = []
    for p in glob.glob(os.path.join(glob.escape(src_dir), "*")):
        if not os.path.isfile(p):
            continue
        if os.path.splitext(p)[1].lower() != ".pdf":
            continue
        if os.path.abspath(p) == out_abs:  # never fold the output back into itself
            continue
        files.append(p)
    if order == "date":
        files.sort(key=lambda p: (os.path.getmtime(p), natural_key(p)))
    else:
        files.sort(key=natural_key)
    return files


def describe_error(exc: Exception) -> str:
    """A short, human-friendly reason a PDF couldn't be read."""
    if isinstance(exc, PdfReadError):
        return "not a readable PDF (corrupt or malformed)"
    if isinstance(exc, FileNotFoundError):
        return "file disappeared before it could be read"
    if isinstance(exc, PermissionError):
        return "permission denied"
    msg = str(exc).strip()
    return msg or exc.__class__.__name__


def combine(files: list[str], out_path: str) -> tuple[int, int, list[str]]:
    """Merge files into out_path. Returns (pdfs_used, pages_written, skipped)."""
    writer = PdfWriter()
    used = 0
    pages = 0
    skipped: list[str] = []
    bar = ProgressBar(len(files), label="Combining")
    for path in files:
        name = os.path.basename(path)
        bar.step(name)
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                # Many "encrypted" PDFs carry an empty owner password; try that
                # transparently so they still combine without prompting.
                if reader.decrypt("") == 0:
                    raise PdfReadError("password-protected")
            # Stage this file's pages in a scratch writer first: if a page fails
            # to parse partway through, we skip the whole file cleanly instead of
            # leaving half of it in the output while reporting it as skipped.
            staged = PdfWriter()
            for page in reader.pages:
                staged.add_page(page)
            n = len(staged.pages)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            msg = f"WARNING: skipping {name!r} — {describe_error(exc)}"
            if bar.enabled:
                bar.log(msg)
            else:
                print(msg, file=sys.stderr)
            skipped.append(path)
            continue
        for page in staged.pages:
            writer.add_page(page)
        used += 1
        pages += n
        if not bar.enabled:
            print(f"  added {name}  ({n} page{'s' if n != 1 else ''})")
    bar.close()

    if used == 0:
        sys.exit("error: no readable PDFs were found to combine.")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        writer.write(fh)
    return used, pages, skipped


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Combine all PDFs in a folder into one PDF, in order.")
    ap.add_argument("--src", required=True,
                    help="folder containing the PDF files to combine")
    ap.add_argument("--out", default=None,
                    help="output PDF path (default: '<folder>-combined.pdf' "
                         "next to the source folder)")
    ap.add_argument("--order", choices=("name", "date"), default="name",
                    help="combine order: by filename number (default) or by "
                         "last-modified date")
    args = ap.parse_args()

    src = os.path.abspath(os.path.normpath(args.src))
    out = args.out or (src.rstrip("/") + "-combined.pdf")

    files = collect_pdfs(src, out, args.order)
    if not files:
        sys.exit(f"error: no .pdf files found in {src!r}")

    print(f"Combining {len(files)} PDF file(s) from:\n  {src}\n")
    used, pages, skipped = combine(files, out)

    print()
    print(f"Done!  Combined {used} PDF{'s' if used != 1 else ''} "
          f"({pages} page{'s' if pages != 1 else ''}) into:")
    print(f"  {out}")
    if skipped:
        print(f"\nSkipped {len(skipped)} file(s) that couldn't be read "
              f"(see the WARNING lines above).")


if __name__ == "__main__":
    main()
