#!/usr/bin/env python3
"""Assemble a folder of pictures into PDF(s) — one image per page, in order.

Reads image files from a source directory (default: "pictures"), sorts
them by the number embedded in each filename (so sample_1 ... sample_100 land
in ascending order regardless of zero-padding), and writes one image per page.

Supported picture types: JPG/JPEG, PNG, BMP, GIF, TIFF, WEBP (and HEIC/HEIF if
the optional pillow-heif package is installed). Extend IMAGE_EXTS to add more.

If a file can't be read (corrupt, wrong contents, unsupported), it is skipped
with a clear WARNING naming that exact file, and the PDF is still built from the
rest — you are never left guessing which picture was the problem.

Splitting
    --parts N splits the run into N separate PDFs, dividing the images as evenly
    as possible into contiguous chunks (handy when a print shop balks at one big
    file). The first (total % N) parts get one extra image; order is preserved.

Conserving space
    --max-height downscales each image to at most that many pixels tall, and
    --quality re-encodes the pages as JPEG. These two knobs — pixels and JPEG
    quality — are what shrink the file. --dpi only sets the physical page size.

Shrinking onto the page (room for notes)
    --margin leaves that many inches of blank border, scaling the image down and
    centering it (shrunk, not cropped). --page sets the sheet size: "match"
    (default phone aspect), "letter", "a4", or "WxH" inches; --bg sets the border
    colour.

Three to a page (landscape)
    --per-page 3 places three pictures side-by-side across one landscape page, in
    file order (ideal for phone screenshots). --gap sets the blank border and the
    spacing between the three pictures, in centimetres (default 0.5). Each picture
    is scaled to fit its column (aspect kept, centred, never cropped). The
    space/size flags above (--max-height, --quality, --parts, --page, --bg) still
    apply; --page picks the sheet, oriented landscape (default Letter).

Page numbers (optional)
    --number-pages burns a small neutral-grey page number (0001, 0002, ...) onto
    each page, over the content, so it survives printing and re-scanning.
    --number-corner picks the corner (bottom-right by default; also bottom-left,
    top-right, top-left) and implies --number-pages. Numbers continue across
    --parts files. Stamped JPEGs are re-encoded at quality 90.
    --number-folder puts the folder's name in front of each number
    ("beach 0001") — with --recursive every folder stamps its own name
    (matching its PDF's name) and the count restarts at 0001 per folder.
    Also implies --number-pages.

A whole directory of folders (batch)
    --recursive walks the source folder and writes one PDF per folder that
    directly holds pictures (the top folder included), each named after its
    folder — holiday/beach -> beach.pdf. --out then names the output FOLDER
    (default: "<src> PDFs" next to the source). Hidden folders and zip
    artefacts like __MACOSX are ignored; two folders sharing a name get their
    path baked in ("2023 - photos.pdf"). Every other option applies to each
    folder's PDF independently (--parts splits each one, page numbers restart
    at 0001), and a folder whose pictures can't be read is reported and
    skipped without stopping the rest of the batch.

Usage:
    python generate_pdf.py                                  # one PDF from every picture
    python generate_pdf.py --parts 3                        # 34 + 33 + 33
    python generate_pdf.py --recursive --src scans          # one PDF per folder
    python generate_pdf.py --number-pages                   # 0001... bottom right
    python generate_pdf.py --number-corner top-left         # 0001... top left
    python generate_pdf.py --max-height 1000 --quality 60   # compact single PDF
    python generate_pdf.py --page letter --margin 0.5 --quality 70   # note margins
    python generate_pdf.py --per-page 3                     # 3 across, landscape
    python generate_pdf.py --per-page 3 --gap 0.5 --quality 70   # 3-up, half-cm gap
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import re
import sys

# The live progress bar lives alongside this script; if it's ever missing
# (e.g. this file was copied out on its own) fall back to a silent no-op so the
# tool still runs exactly as before.
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


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
PAGE_PRESETS = {"letter": (8.5, 11.0), "a4": (8.2677, 11.6929)}  # inches (w, h)
# Known picture types we can't handle without an extra package — worth naming
# explicitly so the user isn't left wondering why they were ignored.
NEEDS_PLUGIN_EXTS = (".heic", ".heif")

# Optional: also accept HEIC/HEIF (e.g. iPhone photos) when the pillow-heif
# package happens to be installed. No hard dependency — this is silently
# skipped if it's missing, so .heic files are reported rather than erroring.
try:
    import pillow_heif  # noqa: F401
    pillow_heif.register_heif_opener()
    IMAGE_EXTS = IMAGE_EXTS + NEEDS_PLUGIN_EXTS
    NEEDS_PLUGIN_EXTS = ()
except Exception:
    pass


def natural_key(path: str):
    """Order by the last run of digits in the filename, then the name itself.

    Files that contain a number sort first (numerically); files without one
    sort afterwards alphabetically. This keeps sample_2 before sample_10 even
    if the names were not zero-padded.
    """
    name = os.path.basename(path)
    nums = re.findall(r"\d+", name)
    if nums:
        return (0, int(nums[-1]), name.lower())
    return (1, 0, name.lower())


def collect_images(src_dir: str):
    """Return (image_files_sorted, ignored_needs_plugin_files)."""
    if not os.path.isdir(src_dir):
        sys.exit(f"error: source directory not found: {src_dir!r}")
    files, needs_plugin = [], []
    for p in glob.glob(os.path.join(glob.escape(src_dir), "*")):
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext in IMAGE_EXTS:
            files.append(p)
        elif ext in NEEDS_PLUGIN_EXTS:
            needs_plugin.append(p)
    files.sort(key=natural_key)
    return files, needs_plugin


# Never descend into these during --recursive: zip-extraction artefacts and
# Python caches hold no user pictures (or, worse, unreadable AppleDouble junk).
SKIP_DIR_NAMES = {"__MACOSX", "__pycache__"}


def find_image_folders(src_dir: str, exclude_dir: str | None = None):
    """Every folder under src_dir that directly holds pictures, src_dir first.

    Returns a list of (dir_path, rel_parts) where rel_parts is the folder's
    path under src_dir as a tuple (empty for src_dir itself), ordered by path
    with the same natural number sort used for files. Hidden (dot-prefixed)
    folders, SKIP_DIR_NAMES and exclude_dir (the output folder, so a re-run
    never scans its own results) are not entered. Dot-prefixed files
    (.DS_Store, "._IMG.jpg" AppleDouble forks) don't count as pictures here,
    matching collect_images, whose glob never matches hidden files — else a
    junk-only folder would be "found" and then turn out to hold nothing.
    """
    src_dir = os.path.abspath(src_dir)
    exclude = os.path.realpath(exclude_dir) if exclude_dir else None
    found = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and d not in SKIP_DIR_NAMES
            and (exclude is None
                 or os.path.realpath(os.path.join(dirpath, d)) != exclude))
        if any(not f.startswith(".") and f.lower().endswith(IMAGE_EXTS)
               for f in filenames):
            rel = os.path.relpath(dirpath, src_dir)
            parts = () if rel == "." else tuple(rel.split(os.sep))
            found.append((dirpath, parts))
    found.sort(key=lambda fp: tuple(natural_key(part) for part in fp[1]))
    return found


def pdf_names_for(folders, src_dir: str) -> list[str]:
    """A distinct output filename for each folder from find_image_folders.

    Plain "<folder name>.pdf" whenever that is unambiguous. Folders sharing a
    name fall back to their path under the source joined with " - "
    ("2023 - photos.pdf"); a numeric suffix is the last resort, so the result
    is always collision-free.
    """
    src_name = os.path.basename(os.path.abspath(src_dir)) or "pictures"
    bases = [(parts[-1] if parts else src_name) for _, parts in folders]
    counts: dict[str, int] = {}
    for b in bases:
        counts[b] = counts.get(b, 0) + 1
    names, seen = [], set()
    for (_, parts), base in zip(folders, bases):
        name = base
        if counts[base] > 1 and parts:
            name = " - ".join(parts)
        if name in seen:
            k = 2
            while f"{name} {k}" in seen:
                k += 1
            name = f"{name} {k}"
        seen.add(name)
        names.append(name + ".pdf")
    return names


def split_evenly(items: list, n: int) -> list[list]:
    """Split a list into n contiguous chunks whose sizes differ by at most 1.

    The first (len(items) % n) chunks receive one extra item. Order is
    preserved, so concatenating the chunks reproduces the original list.
    """
    base, rem = divmod(len(items), n)
    chunks, start = [], 0
    for i in range(n):
        size = base + (1 if i < rem else 0)
        chunks.append(items[start:start + size])
        start += size
    return chunks


def part_path(out_path: str, index: int, n: int) -> str:
    """Output path for part `index` of `n` (1-based).

    For a single part the base --out path is used unchanged. For multiple parts
    a zero-padded ``_partX_of_N`` suffix is inserted before the extension, e.g.
    sample_imagery.pdf -> sample_imagery_part1_of_3.pdf.
    """
    if n == 1:
        return out_path
    stem, ext = os.path.splitext(out_path)
    width = len(str(n))
    return f"{stem}_part{index:0{width}d}_of_{n}{ext or '.pdf'}"


def describe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Optional burned-in page numbers
# ---------------------------------------------------------------------------
NUMBER_CORNERS = ("bottom-right", "bottom-left", "top-right", "top-left")


def stamp_page_number(im, number: int, corner: str, prefix: str = ""):
    """Burn a zero-padded page number ("0001") into one corner of a page.

    Drawn onto the pixels themselves, so it sits on top of the content and
    prints exactly as shown. Neutral mid-grey with a thin white outline keeps
    it readable over both dark photos and white paper. The text height scales
    with the page so it stays proportional at any raster size. A non-empty
    prefix (the folder's name) goes in front: "beach 0001".
    """
    from PIL import ImageDraw, ImageFont
    text = str(number).zfill(4)
    if prefix:
        text = f"{prefix} {text}"
    size = max(12, round(min(im.size) * 0.03))
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1: fixed-size bitmap font, still legible
        font = ImageFont.load_default()
    stroke = max(1, size // 14)
    draw = ImageDraw.Draw(im)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font,
                                             stroke_width=stroke)
    pad = max(6, size // 2)
    x = pad - left if "left" in corner else im.width - pad - right
    y = pad - top if "top" in corner else im.height - pad - bottom
    draw.text((x, y), text, font=font, fill=(128, 128, 128),
              stroke_width=stroke, stroke_fill=(255, 255, 255))
    return im


# ---------------------------------------------------------------------------
# Plain (lossless) engines — used when no space/layout flags are given.
# ---------------------------------------------------------------------------
def prepare_sources(files: list[str], force_reencode: bool = False, progress=None,
                    number_start: int = 0, number_corner: str = "bottom-right",
                    number_prefix: str = ""):
    """Turn each file into an img2pdf-ready source, skipping unreadable ones.

    Upright JPEG images in RGB/grayscale are passed through untouched (embedded
    losslessly, no re-encode). Everything else — including any image carrying an
    EXIF rotation — is decoded with Pillow, turned upright, and losslessly
    re-encoded to PNG bytes, which img2pdf reliably accepts, so a folder mixing
    jpg/png/bmp/gif/tiff/webp all lands in the PDF the right way up.

    With force_reencode=True nothing is passed through: every image is decoded
    and re-encoded (used as a fallback if img2pdf rejects a passed-through file).

    number_start > 0 stamps page numbers (number_start, number_start+1, ...)
    into number_corner. Stamping changes pixels, so nothing can pass through:
    JPEGs re-encode as JPEG quality 90 (visually identical, sanely sized)
    rather than ballooning into PNGs; everything else stays lossless PNG.

    Returns (sources, skipped) where skipped is a list of (path, reason).
    """
    from PIL import Image, ImageOps
    sources, skipped = [], []
    for p in files:
        if progress is not None:
            progress.step(os.path.basename(p))
        ext = os.path.splitext(p)[1].lower()
        try:
            with Image.open(p) as im:
                im.load()  # force a full decode: catches truncated/corrupt files
                # Orientation 1 (or absent) means the stored pixels already show
                # upright, so the JPEG bytes can be embedded as-is. Any other
                # value (e.g. an iPhone portrait) must be baked in by re-encoding.
                upright = im.getexif().get(0x0112, 1) == 1
                if (not force_reencode and not number_start and upright
                        and ext in (".jpg", ".jpeg") and im.mode in ("RGB", "L")):
                    sources.append(p)
                else:
                    im = ImageOps.exif_transpose(im)
                    rgb = im if im.mode == "RGB" else im.convert("RGB")
                    if number_start:
                        stamp_page_number(rgb, number_start + len(sources),
                                          number_corner, number_prefix)
                    buf = io.BytesIO()
                    if number_start and ext in (".jpg", ".jpeg"):
                        rgb.save(buf, format="JPEG", quality=90)
                    else:
                        rgb.save(buf, format="PNG")
                    sources.append(buf.getvalue())
        except Exception as exc:
            skipped.append((p, describe_error(exc)))
    return sources, skipped


def build_with_img2pdf(files: list[str], out_path: str, dpi: float, progress=None,
                       number_start: int = 0, number_corner: str = "bottom-right",
                       number_prefix: str = ""):
    import img2pdf
    sources, skipped = prepare_sources(files, progress=progress,
                                       number_start=number_start,
                                       number_corner=number_corner,
                                       number_prefix=number_prefix)
    if not sources:
        return 0, skipped
    if progress is not None:
        progress.note("assembling PDF")
    # Fix the DPI so every page is sized deterministically from its pixels
    # (page_inches = pixels / dpi), rather than depending on image metadata.
    layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    try:
        pdf = img2pdf.convert(sources, layout_fun=layout)
    except Exception:
        # A losslessly passed-through JPEG may be one img2pdf refuses. Re-encode
        # every image and retry so a single odd file can't sink the whole batch.
        if progress is not None:
            progress.note("re-encoding images")
        sources, skipped = prepare_sources(files, force_reencode=True,
                                           number_start=number_start,
                                           number_corner=number_corner,
                                           number_prefix=number_prefix)
        if not sources:
            return 0, skipped
        try:
            pdf = img2pdf.convert(sources, layout_fun=layout)
        except Exception as exc:
            sys.exit(f"error: could not assemble the PDF ({describe_error(exc)})")
    with open(out_path, "wb") as f:
        f.write(pdf)
    return len(sources), skipped


def build_with_pillow(files: list[str], out_path: str, dpi: float, progress=None,
                      number_start: int = 0, number_corner: str = "bottom-right",
                      number_prefix: str = ""):
    from PIL import Image, ImageOps
    pages, skipped = [], []
    for p in files:
        if progress is not None:
            progress.step(os.path.basename(p))
        try:
            im = Image.open(p)
            im.load()
            im = ImageOps.exif_transpose(im)  # honour EXIF rotation (phone photos)
            im = im if im.mode == "RGB" else im.convert("RGB")
            if number_start:
                stamp_page_number(im, number_start + len(pages), number_corner,
                                  number_prefix)
            pages.append(im)
        except Exception as exc:
            skipped.append((p, describe_error(exc)))
    if not pages:
        return 0, skipped
    if progress is not None:
        progress.note("assembling PDF")
    pages[0].save(
        out_path, "PDF", save_all=True, append_images=pages[1:],
        resolution=float(dpi),
    )
    return len(pages), skipped


# ---------------------------------------------------------------------------
# Composed pages — downscale / JPEG / margins. Each page is rendered onto a
# canvas and embedded as one raster, so page size = canvas size (full bleed).
# ---------------------------------------------------------------------------
def page_inches(page_spec: str, native_px: tuple[int, int], dpi: float):
    """Physical page size in inches for --page."""
    if page_spec == "match":
        return native_px[0] / dpi, native_px[1] / dpi
    s = page_spec.lower()
    if s in PAGE_PRESETS:
        return PAGE_PRESETS[s]
    if "x" in s:
        try:
            w, h = s.split("x")
            return float(w), float(h)
        except ValueError:
            pass
    sys.exit(f"error: --page must be 'match', 'letter', 'a4', or 'WxH' inches (got {page_spec!r})")


def compose_pages(files, dpi, max_height, quality, margin_in, page_spec, bg, progress=None,
                  number_start=0, number_corner="bottom-right", number_prefix=""):
    """Render each image onto a page canvas; return (page_blobs, raster, skipped).

    Unreadable files are skipped and recorded in `skipped` as (path, reason).
    raster (pixels-per-inch) is chosen so the physical page equals the requested
    size regardless of pixel count, sized from the first readable image. Every
    image is then scaled to fit within the margins (aspect kept, centred, never
    cropped), so a picture with more pixels than the first one shrinks onto the
    page instead of overflowing it.
    """
    from PIL import Image, ImageOps

    try:
        Image.new("RGB", (1, 1), bg)
    except Exception:
        sys.exit(f"error: --bg is not a valid colour: {bg!r}")

    def downscale(im):
        if max_height and im.height > max_height:
            s = max_height / im.height
            return im.resize((round(im.width * s), max_height), Image.LANCZOS)
        return im

    skipped = []
    bad = set()
    native = ref_size = None
    for p in files:  # find the first readable image to fix the canvas size
        try:
            with Image.open(p) as im:
                im.load()
                im = ImageOps.exif_transpose(im)
                native = im.size
                ref_size = downscale(im.convert("RGB")).size
            break
        except Exception as exc:
            skipped.append((p, describe_error(exc)))
            bad.add(p)
    if ref_size is None:
        return [], 1.0, skipped

    pw_in, ph_in = page_inches(page_spec, native, dpi)
    avail_w = max(0.01, pw_in - 2 * margin_in)
    avail_h = max(0.01, ph_in - 2 * margin_in)
    riw, rih = ref_size
    raster = riw / avail_w if (riw / rih) > (avail_w / avail_h) else rih / avail_h
    w_px = max(1, round(pw_in * raster))
    h_px = max(1, round(ph_in * raster))
    # The printable box in pixels. Each image is scaled to fit inside it so a
    # picture with more pixels than the reference can't overrun the page/margins.
    avail_w_px = avail_w * raster
    avail_h_px = avail_h * raster

    blobs = []
    for p in files:
        if progress is not None:
            progress.step(os.path.basename(p))
        if p in bad:
            continue
        try:
            with Image.open(p) as im:
                im.load()
                im = ImageOps.exif_transpose(im)
                im = downscale(im if im.mode == "RGB" else im.convert("RGB"))
                fit = min(1.0, avail_w_px / im.width, avail_h_px / im.height)
                if fit < 1.0:
                    im = im.resize((max(1, round(im.width * fit)),
                                    max(1, round(im.height * fit))), Image.LANCZOS)
                canvas = Image.new("RGB", (w_px, h_px), bg)
                canvas.paste(im, (round((w_px - im.width) / 2), round((h_px - im.height) / 2)))
                if number_start:
                    stamp_page_number(canvas, number_start + len(blobs),
                                      number_corner, number_prefix)
                buf = io.BytesIO()
                if quality:
                    canvas.save(buf, "JPEG", quality=quality, optimize=True)
                else:
                    canvas.save(buf, "PNG", optimize=True)
                blobs.append(buf.getvalue())
        except Exception as exc:
            skipped.append((p, describe_error(exc)))
    return blobs, raster, skipped


def multiup_page_inches(page_spec: str):
    """Landscape page size in inches for the --per-page layout.

    Accepts the same names as --page (letter/a4/WxH). "match" has no single
    aspect once several pictures share a page, so it falls back to US Letter.
    The result is always oriented landscape (width >= height).
    """
    s = page_spec.lower()
    if s == "match":
        w, h = PAGE_PRESETS["letter"]
    elif s in PAGE_PRESETS:
        w, h = PAGE_PRESETS[s]
    elif "x" in s:
        try:
            a, b = s.split("x")
            w, h = float(a), float(b)
        except ValueError:
            sys.exit(f"error: --page must be 'match', 'letter', 'a4', or 'WxH' inches (got {page_spec!r})")
    else:
        sys.exit(f"error: --page must be 'match', 'letter', 'a4', or 'WxH' inches (got {page_spec!r})")
    return max(w, h), min(w, h)


def compose_multiup_pages(files, dpi, max_height, quality, per_page, gap_cm, page_spec, bg, progress=None,
                          number_start=0, number_corner="bottom-right", number_prefix=""):
    """Render `per_page` pictures across each landscape page (one row of cells).

    Pictures are placed left-to-right in file order, each scaled to fit its cell
    (aspect kept, centred, never cropped). `gap_cm` is the blank border AND the
    spacing between cells. Unreadable files are skipped and recorded in `skipped`
    as (path, reason); the readable ones still flow into full pages. Returns
    (page_blobs, raster, skipped) exactly like compose_pages.
    """
    from PIL import Image, ImageOps

    try:
        Image.new("RGB", (1, 1), bg)
    except Exception:
        sys.exit(f"error: --bg is not a valid colour: {bg!r}")

    def downscale(im):
        if max_height and im.height > max_height:
            s = max_height / im.height
            return im.resize((round(im.width * s), max_height), Image.LANCZOS)
        return im

    n = per_page
    gap_in = gap_cm / 2.54
    pw_in, ph_in = multiup_page_inches(page_spec)
    cell_w_in = max(0.01, (pw_in - (n + 1) * gap_in) / n)
    cell_h_in = max(0.01, ph_in - 2 * gap_in)

    # Pixel geometry is fixed from the first readable picture, sized so that
    # reference picture lands at roughly native resolution inside its cell.
    state = {}

    def ensure_geometry(ref_w, ref_h):
        if state:
            return
        raster = max(ref_w / cell_w_in, ref_h / cell_h_in)
        state.update(
            raster=raster,
            W=max(1, round(pw_in * raster)),
            H=max(1, round(ph_in * raster)),
            gap_px=round(gap_in * raster),
            cell_w=max(1, round(cell_w_in * raster)),
            cell_h=max(1, round(cell_h_in * raster)),
        )

    blobs, skipped, group = [], [], []

    def flush():
        if not group:
            return
        canvas = Image.new("RGB", (state["W"], state["H"]), bg)
        for col, tile in enumerate(group):
            cell_x = state["gap_px"] + col * (state["cell_w"] + state["gap_px"])
            x = cell_x + (state["cell_w"] - tile.width) // 2
            y = state["gap_px"] + (state["cell_h"] - tile.height) // 2
            canvas.paste(tile, (x, y))
        if number_start:
            stamp_page_number(canvas, number_start + len(blobs), number_corner,
                              number_prefix)
        buf = io.BytesIO()
        if quality:
            canvas.save(buf, "JPEG", quality=quality, optimize=True)
        else:
            canvas.save(buf, "PNG", optimize=True)
        blobs.append(buf.getvalue())
        group.clear()

    for p in files:
        if progress is not None:
            progress.step(os.path.basename(p))
        try:
            with Image.open(p) as im:
                im.load()
                im = ImageOps.exif_transpose(im)
                im = downscale(im if im.mode == "RGB" else im.convert("RGB"))
                ensure_geometry(im.width, im.height)
                s = min(state["cell_w"] / im.width, state["cell_h"] / im.height)
                tw, th = max(1, round(im.width * s)), max(1, round(im.height * s))
                tile = im.resize((tw, th), Image.LANCZOS)
        except Exception as exc:
            skipped.append((p, describe_error(exc)))
            continue
        group.append(tile)
        if len(group) == n:
            flush()
    flush()

    if not state:
        return [], 1.0, skipped
    return blobs, state["raster"], skipped


def build(engine, files, out_path, dpi, *, max_height=0, quality=0,
          margin=0.0, page="match", bg="white", per_page=1, gap_cm=0.5, progress=None,
          number_start=0, number_corner="bottom-right", number_prefix=""):
    """Build one PDF. Returns (pages_written, skipped).

    number_start > 0 burns page numbers onto the pages, starting at that
    value (0001-style), into number_corner; 0 leaves pages untouched.
    A non-empty number_prefix goes in front of each number ("beach 0001").
    """
    if per_page > 1:
        # The N-per-page landscape layout is always a composed raster, so it
        # needs img2pdf just like the other space/layout options below.
        try:
            import img2pdf
        except ImportError:
            sys.exit("error: --per-page requires img2pdf (pip install img2pdf)")
        blobs, raster, skipped = compose_multiup_pages(
            files, dpi, max_height, quality, per_page, gap_cm, page, bg, progress=progress,
            number_start=number_start, number_corner=number_corner,
            number_prefix=number_prefix)
        if not blobs:
            return 0, skipped
        if progress is not None:
            progress.note("assembling PDF")
        layout = img2pdf.get_fixed_dpi_layout_fun((raster, raster))
        try:
            pdf = img2pdf.convert(blobs, layout_fun=layout)
        except Exception as exc:
            sys.exit(f"error: could not assemble the PDF ({describe_error(exc)})")
        with open(out_path, "wb") as f:
            f.write(pdf)
        return len(blobs), skipped

    advanced = bool(max_height) or bool(quality) or margin > 0 or page != "match"
    if not advanced:
        if engine == "img2pdf":
            return build_with_img2pdf(files, out_path, dpi, progress=progress,
                                      number_start=number_start,
                                      number_corner=number_corner,
                                      number_prefix=number_prefix)
        return build_with_pillow(files, out_path, dpi, progress=progress,
                                 number_start=number_start,
                                 number_corner=number_corner,
                                 number_prefix=number_prefix)
    try:
        import img2pdf
    except ImportError:
        sys.exit("error: --max-height/--quality/--margin/--page require img2pdf "
                 "(pip install img2pdf)")
    blobs, raster, skipped = compose_pages(files, dpi, max_height, quality, margin, page, bg, progress=progress,
                                           number_start=number_start, number_corner=number_corner,
                                           number_prefix=number_prefix)
    if not blobs:
        return 0, skipped
    if progress is not None:
        progress.note("assembling PDF")
    layout = img2pdf.get_fixed_dpi_layout_fun((raster, raster))
    try:
        pdf = img2pdf.convert(blobs, layout_fun=layout)
    except Exception as exc:
        sys.exit(f"error: could not assemble the PDF ({describe_error(exc)})")
    with open(out_path, "wb") as f:
        f.write(pdf)
    return len(blobs), skipped


def note_needs_plugin(needs_plugin: list[str]) -> None:
    if needs_plugin:
        print(f"note: ignoring {len(needs_plugin)} HEIC/HEIF file(s) such as "
              f"{os.path.basename(needs_plugin[0])} — convert them to JPEG/PNG, or "
              f"install pillow-heif to include them.", file=sys.stderr)


def make_pdfs(files, out_path, parts, args, engine, *, bar_label=None,
              number_prefix=""):
    """One whole --parts run: chunk the images and write the PDF file(s).

    Prints the per-part result lines, the split total and the skipped-file
    warnings. main() calls this once normally, or once per folder with
    --recursive (bar_label then names the folder on the progress bar, and
    number_prefix carries that folder's name into the page stamps).
    Returns (pages_written, bytes_written, files_skipped).
    """
    number_corner = args.number_corner or "bottom-right"
    chunks = split_evenly(files, parts)
    total_bytes = 0
    total_pages = 0
    all_skipped = []
    for i, chunk in enumerate(chunks, start=1):
        out = part_path(out_path, i, parts)
        if bar_label:
            bar_text = f"{bar_label} {i}/{parts}" if parts > 1 else bar_label
        else:
            bar_text = f"Part {i}/{parts}" if parts > 1 else "Building PDF"
        bar = ProgressBar(len(chunk), label=bar_text)
        pages_written, skipped = build(
            engine, chunk, out, args.dpi, max_height=args.max_height,
            quality=args.quality, margin=args.margin, page=args.page, bg=args.bg,
            per_page=args.per_page, gap_cm=args.gap, progress=bar,
            # Numbers continue across parts: the next part picks up right
            # after the pages already written (skipped files leave no gap).
            number_start=(1 + total_pages) if args.number_pages else 0,
            number_corner=number_corner, number_prefix=number_prefix)
        bar.close()
        all_skipped.extend(skipped)
        total_pages += pages_written
        label = f"part {i}/{parts}: " if parts > 1 else ""
        if pages_written == 0:
            print(f"  {label}no readable images — nothing written")
            continue
        nbytes = os.path.getsize(out)
        total_bytes += nbytes
        first, last = os.path.basename(chunk[0]), os.path.basename(chunk[-1])
        print(f"  {label}{pages_written} pages -> {out}  "
              f"[{nbytes / 1024 / 1024:.1f} MB]  ({first} ... {last})")

    if parts > 1:
        print(f"total: {total_pages} pages across {parts} files, "
              f"{total_bytes / 1024 / 1024:.1f} MB")

    if all_skipped:
        print(file=sys.stderr)
        for path, reason in all_skipped:
            print(f"WARNING: could not read {os.path.basename(path)} — skipped it "
                  f"[{reason}]", file=sys.stderr)
        print(f"WARNING: {len(all_skipped)} file(s) were skipped; the PDF was built "
              f"from the {total_pages} that worked.", file=sys.stderr)
    return total_pages, total_bytes, len(all_skipped)


def resolve_engine(name: str) -> str:
    if name != "auto":
        return name
    try:
        import img2pdf  # noqa: F401
        return "img2pdf"
    except ImportError:
        return "pillow"


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--src", default=os.path.join(here, "pictures"),
                    help='source image directory (default: "pictures")')
    ap.add_argument("--out", default=None,
                    help="output PDF path (default: pictures.pdf next to this "
                         "script); for --parts>1 a _partX_of_N suffix is added; "
                         "with --recursive this is the output FOLDER")
    ap.add_argument("--recursive", action="store_true",
                    help="one PDF per folder, named after it: this folder and "
                         "every folder inside it that directly holds pictures "
                         "(default output folder: '<src> PDFs' next to the source)")
    ap.add_argument("--parts", "-n", type=int, default=1, metavar="N",
                    help="split the images evenly into N separate PDFs (default: 1)")
    ap.add_argument("--dpi", type=float, default=150.0,
                    help="pixels-per-inch used to size each page (default: 150)")
    ap.add_argument("--max-height", type=int, default=0, metavar="PX",
                    help="downscale each image to at most PX pixels tall to save space "
                         "(0 = keep full resolution)")
    ap.add_argument("--quality", type=int, default=0, metavar="Q",
                    help="JPEG-encode pages at quality Q (1-95) to save space; "
                         "0 = lossless (default)")
    ap.add_argument("--margin", type=float, default=0.0, metavar="IN",
                    help="blank border in inches; shrinks the image onto the page "
                         "(0 = fill the page, default)")
    ap.add_argument("--page", default="match", metavar="SIZE",
                    help="page size: match (default), letter, a4, or WxH in inches")
    ap.add_argument("--bg", default="white",
                    help="margin/background colour (name or #RRGGBB; default white)")
    ap.add_argument("--per-page", type=int, default=1, metavar="N",
                    help="pictures per page: 1 (default), or 3 to place three "
                         "side-by-side across a landscape page, in file order")
    ap.add_argument("--gap", type=float, default=0.5, metavar="CM",
                    help="for --per-page>1: blank border and spacing between the "
                         "pictures, in centimetres (default: 0.5)")
    ap.add_argument("--number-pages", action="store_true",
                    help="burn a page number (0001, 0002, ...) onto each page, "
                         "on top of the picture; numbers run on across --parts")
    ap.add_argument("--number-corner", choices=list(NUMBER_CORNERS), default=None,
                    metavar="CORNER",
                    help="corner for the page number: bottom-right (default), "
                         "bottom-left, top-right or top-left; implies --number-pages")
    ap.add_argument("--number-folder", action="store_true",
                    help="put the folder's name in front of each page number "
                         "('beach 0001'); with --recursive each folder stamps "
                         "its own name; implies --number-pages")
    ap.add_argument("--engine", choices=["auto", "img2pdf", "pillow"], default="auto",
                    help="PDF engine for the plain lossless case (default: auto)")
    args = ap.parse_args()
    if (args.number_corner or args.number_folder) and not args.number_pages:
        args.number_pages = True

    if args.parts < 1:
        sys.exit(f"error: --parts must be >= 1 (got {args.parts})")
    if args.quality and not (1 <= args.quality <= 95):
        sys.exit(f"error: --quality must be 1-95 (got {args.quality})")
    if args.max_height < 0:
        sys.exit(f"error: --max-height must be >= 0 (got {args.max_height})")
    if args.margin < 0:
        sys.exit(f"error: --margin must be >= 0 (got {args.margin})")
    if args.per_page < 1:
        sys.exit(f"error: --per-page must be >= 1 (got {args.per_page})")
    if args.gap < 0:
        sys.exit(f"error: --gap must be >= 0 (got {args.gap})")
    if args.per_page > 1 and args.margin:
        print("note: --margin has no effect with --per-page; use --gap for the "
              "border and spacing.", file=sys.stderr)

    engine = resolve_engine(args.engine)

    notes = []
    if args.per_page > 1:
        notes.append(f"{args.per_page} per landscape page, {args.gap:g}cm gap")
    if args.max_height:
        notes.append(f"max-height {args.max_height}px")
    if args.quality:
        notes.append(f"JPEG q{args.quality}")
    if args.margin:
        notes.append(f"margin {args.margin:g}in")
    if args.page != "match":
        notes.append(f"page {args.page}")
    if args.number_pages:
        style = "folder name + 0001..." if args.number_folder else "0001..."
        notes.append(f"page numbers ({style}) {args.number_corner or 'bottom-right'}")
    if notes:
        print("options:", ", ".join(notes))

    if args.recursive:
        src_abs = os.path.abspath(args.src)
        if not os.path.isdir(src_abs):
            sys.exit(f"error: source directory not found: {args.src!r}")
        out_dir = args.out or (src_abs + " PDFs")
        folders = find_image_folders(src_abs, exclude_dir=out_dir)
        if not folders:
            sys.exit(f"error: no folders with supported images under {args.src!r} "
                     f"(looked for: {', '.join(e[1:] for e in IMAGE_EXTS)})")
        n = len(folders)
        print(f"found {n} folder{'s' if n != 1 else ''} with pictures under {src_abs}")
        print(f"writing one PDF per folder ({engine}, {args.dpi:g} dpi) into {out_dir}")
        os.makedirs(out_dir, exist_ok=True)
        names = pdf_names_for(folders, src_abs)
        made = 0
        grand_pages = 0
        grand_bytes = 0
        for i, ((folder, _), name) in enumerate(zip(folders, names), start=1):
            files, needs_plugin = collect_images(folder)
            note_needs_plugin(needs_plugin)
            if not files:  # e.g. pictures deleted between the scan and now
                continue
            stem = name[:-len(".pdf")]
            print(f"[{i}/{n}] {stem}")
            parts = min(args.parts, len(files))
            if parts < args.parts:
                print(f"  note: only {len(files)} picture(s) here — writing "
                      f"{parts} file{'s' if parts != 1 else ''} instead of "
                      f"{args.parts}.", file=sys.stderr)
            pages, nbytes, _ = make_pdfs(
                files, os.path.join(out_dir, name), parts, args, engine,
                bar_label=stem,
                # The stamp matches the PDF's name, so pages from two
                # same-named folders stay tellable apart on paper too.
                number_prefix=stem if args.number_folder else "")
            grand_pages += pages
            grand_bytes += nbytes
            if pages:
                made += 1
        print(f"batch total: {made} of {n} folder{'s' if n != 1 else ''} -> "
              f"{grand_pages} pages, {grand_bytes / 1024 / 1024:.1f} MB in {out_dir}")
        if grand_pages == 0:
            sys.exit("error: no images could be read — no PDF was produced.")
        return

    if args.out is None:
        args.out = os.path.join(here, "pictures.pdf")
    files, needs_plugin = collect_images(args.src)
    note_needs_plugin(needs_plugin)
    if not files:
        sys.exit(f"error: no supported images found in {args.src!r} "
                 f"(looked for: {', '.join(e[1:] for e in IMAGE_EXTS)})")
    if args.parts > len(files):
        sys.exit(f"error: --parts ({args.parts}) exceeds image count ({len(files)}); "
                 f"cannot make more parts than images")

    if args.parts == 1:
        print(f"building 1 PDF ({engine}, {args.dpi:g} dpi) from {len(files)} images")
    else:
        sizes = [len(c) for c in split_evenly(files, args.parts)]
        print(f"splitting {len(files)} images into {args.parts} parts "
              f"({engine}, {args.dpi:g} dpi): sizes {sizes}")

    prefix = (os.path.basename(os.path.abspath(args.src))
              if args.number_folder else "")
    total_pages, _, _ = make_pdfs(files, args.out, args.parts, args, engine,
                                  number_prefix=prefix)
    if total_pages == 0:
        sys.exit("error: no images could be read — no PDF was produced.")


if __name__ == "__main__":
    main()
