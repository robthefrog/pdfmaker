#!/usr/bin/env python3
"""Tests for colour profiles on the composed pages of generate_pdf.py.

A picture's colour profile says what its numbers mean: the same "255, 0, 0"
is a different red in Display P3 (iPhone photos) than in sRGB. The layouts
that draw pictures onto a fresh page - smaller file, note margins, three to a
page - throw the profile away with the original file, so they have to convert
each picture to plain sRGB first, or wide-gamut photos come out washed out.

Washed-out is too subtle to assert on, so these tests use a deliberately
absurd profile instead: Pillow's own sRGB profile with its red and green
primaries exchanged. A red/green/blue/yellow card tagged with it should be
SHOWN as green/red/blue/yellow. Reading a page's corners therefore gives
"GRBY" when the profile was honoured and "RGBY" when it was dropped - a
difference no JPEG artefact can blur. Nothing here needs a real photo or a
copyrighted profile file, and nothing inside the repo is touched.

Run with any Python 3:  python3 tests/test_colour.py
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO, "generate_pdf.py")


def venv_python() -> str:
    if os.name == "nt":
        return os.path.join(REPO, ".venv", "Scripts", "python.exe")
    return os.path.join(REPO, ".venv", "bin", "python")


try:
    import PIL  # noqa: F401
    import pypdf  # noqa: F401
except ImportError:
    vp = venv_python()
    # Compare unresolved paths: on macOS .venv/bin/python is a symlink back
    # to the base interpreter, so realpath() would call them "the same" and
    # never switch into the venv. abspath still stops any re-exec loop.
    if os.path.exists(vp) and os.path.abspath(vp) != os.path.abspath(sys.executable):
        os.execv(vp, [vp] + sys.argv)
    sys.exit("These tests need Pillow and pypdf. Run a launcher once to "
             "create the .venv, or: pip install Pillow pypdf img2pdf")

try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # lets Pillow write the HEIC test picture
    HAVE_HEIC = True
except Exception:
    HAVE_HEIC = False

VENVPY = sys.executable
WORK = tempfile.mkdtemp(prefix="pdfmaker-test-")
CT = os.path.join(WORK, "ct")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# Profiles and pictures
# ---------------------------------------------------------------------------
def srgb_profile() -> bytes:
    from PIL import ImageCms
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def swapped_profile() -> bytes:
    """sRGB with its red and green primaries exchanged (see module docstring)."""
    icc = srgb_profile()
    count = struct.unpack(">I", icc[128:132])[0]
    tags = {}
    for i in range(count):
        entry = icc[132 + 12 * i:144 + 12 * i]
        tags[entry[:4]] = struct.unpack(">II", entry[4:])
    (r_off, r_len), (g_off, g_len) = tags[b"rXYZ"], tags[b"gXYZ"]
    assert r_len == g_len, "unexpected profile layout"
    out = bytearray(icc)
    out[r_off:r_off + r_len] = icc[g_off:g_off + g_len]
    out[g_off:g_off + g_len] = icc[r_off:r_off + r_len]
    return bytes(out)


QUADRANTS = {"R": (220, 30, 30), "G": (30, 180, 30),
             "B": (30, 30, 220), "Y": (230, 210, 30)}
SIZE = (160, 120)
HONOURED = "GRBY"   # the swapped profile was applied: red and green trade places
AS_STORED = "RGBY"  # the picture's own numbers, untouched


def card(size=SIZE):
    """Quadrant card: top-left Red, top-right Green, bottom-left Blue,
    bottom-right Yellow - reading the corners gives "RGBY"."""
    from PIL import Image
    w, h = size
    im = Image.new("RGB", size)
    im.paste(QUADRANTS["R"], (0, 0, w // 2, h // 2))
    im.paste(QUADRANTS["G"], (w // 2, 0, w, h // 2))
    im.paste(QUADRANTS["B"], (0, h // 2, w // 2, h))
    im.paste(QUADRANTS["Y"], (w // 2, h // 2, w, h))
    return im


def colour_name(rgb):
    r, g, b = rgb[:3]
    best = min(QUADRANTS, key=lambda k: sum(
        (a - c) ** 2 for a, c in zip((r, g, b), QUADRANTS[k])))
    dist = sum((a - c) ** 2 for a, c in zip((r, g, b), QUADRANTS[best]))
    return best if dist < 60 ** 2 else "?"


def corners(im):
    """The four quadrant colours read TL, TR, BL, BR (each one averaged)."""
    from PIL import Image
    tiny = im.convert("RGB").resize((2, 2), Image.BOX)
    return "".join(colour_name(tiny.getpixel(p))
                   for p in ((0, 0), (1, 0), (0, 1), (1, 1)))


def picture_area(page):
    """Crop a page image to its non-white content (drops margins/borders)."""
    from PIL import Image, ImageChops
    rgb = page.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white"))
    box = diff.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox()
    return rgb.crop(box) if box else rgb


def save(path, im, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, **kw)


def run_engine(args):
    return subprocess.run([VENVPY, ENGINE] + args,
                          capture_output=True, text=True, timeout=300)


def page_images(pdf_path):
    from pypdf import PdfReader
    if not os.path.isfile(pdf_path):
        return []
    out = []
    for page in PdfReader(pdf_path).pages:
        imgs = page.images
        out.append(imgs[0].image.convert("RGB") if imgs else None)
    return out


def setup():
    from PIL import Image
    swap, srgb = swapped_profile(), srgb_profile()
    # profiles/: every way a profile can arrive, plus two controls
    d = os.path.join(CT, "profiles")
    save(os.path.join(d, "p_1.jpg"), card(), quality=95, icc_profile=swap)
    save(os.path.join(d, "p_2.png"), card(), icc_profile=swap)
    save(os.path.join(d, "p_3.png"),
         card().convert("P", palette=Image.ADAPTIVE, colors=8), icc_profile=swap)
    save(os.path.join(d, "p_4.png"), card())                          # no profile
    save(os.path.join(d, "p_5.jpg"), card(), quality=95, icc_profile=srgb)
    # three/: differently-tagged pictures that must share one 3-up page
    d = os.path.join(CT, "three")
    save(os.path.join(d, "c_1.jpg"), card(), quality=95, icc_profile=swap)
    save(os.path.join(d, "c_2.png"), card())
    save(os.path.join(d, "c_3.png"), card(), icc_profile=swap)
    # single/: one tagged JPEG; broken/: a profile that is just garbage bytes
    save(os.path.join(CT, "single", "s_1.jpg"), card(), quality=95, icc_profile=swap)
    save(os.path.join(CT, "broken", "b_1.jpg"), card(), quality=95,
         icc_profile=b"this is not a colour profile at all")
    if HAVE_HEIC:
        save(os.path.join(CT, "heic", "IMG_1.HEIC"), card(), format="HEIF",
             quality=90, icc_profile=swap)


# What each page of profiles/ must show once profiles are honoured.
PROFILES_WANT = (("p_1.jpg  tagged JPEG", HONOURED),
                 ("p_2.png  tagged PNG", HONOURED),
                 ("p_3.png  tagged palette PNG", HONOURED),
                 ("p_4.png  no profile", AS_STORED),
                 ("p_5.jpg  tagged sRGB", AS_STORED))


def check_pages(pdf, want, crop=False):
    pages = page_images(pdf)
    check(f"{len(want)} pages", len(pages) == len(want), f"got {len(pages)}")
    for (label, expected), page in zip(want, pages):
        got = None
        if page is not None:
            got = corners(picture_area(page) if crop else page)
        check(f"{label} -> {expected}", got == expected, f"read {got}")


def t_smaller_file():
    print("C1: smaller-file mode (--quality) honours each picture's profile")
    out = os.path.join(CT, "smaller.pdf")
    r = run_engine(["--src", os.path.join(CT, "profiles"), "--out", out,
                    "--quality", "80"])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check_pages(out, PROFILES_WANT)

    # Shrinking happens before the conversion; the profile has to survive it.
    out = os.path.join(CT, "smaller_shrunk.pdf")
    r = run_engine(["--src", os.path.join(CT, "single"), "--out", out,
                    "--quality", "80", "--max-height", "60"])
    pages = page_images(out)
    got = pages[0] if pages else None
    check("--max-height too: an 80x60 page, profile still honoured",
          got is not None and got.size == (80, 60) and corners(got) == HONOURED,
          f"rc={r.returncode} size={getattr(got, 'size', None)} "
          f"read {corners(got) if got else None}")


def t_margins():
    print("C2: note-margin mode (--page/--margin) honours each picture's profile")
    out = os.path.join(CT, "margins.pdf")
    r = run_engine(["--src", os.path.join(CT, "profiles"), "--out", out,
                    "--page", "letter", "--margin", "0.5"])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check_pages(out, PROFILES_WANT, crop=True)


def t_three_up():
    print("C3: three differently-tagged pictures share one 3-up page correctly")
    out = os.path.join(CT, "three.pdf")
    r = run_engine(["--src", os.path.join(CT, "three"), "--out", out,
                    "--per-page", "3", "--gap", "0"])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    pages = page_images(out)
    check("1 page", len(pages) == 1, f"got {len(pages)}")
    if len(pages) == 1 and pages[0] is not None:
        # With no gap the three equal tiles sit edge to edge in one band.
        band = picture_area(pages[0])
        w, h = band.size
        want = (("c_1.jpg  tagged JPEG", HONOURED),
                ("c_2.png  no profile", AS_STORED),
                ("c_3.png  tagged PNG", HONOURED))
        for i, (label, expected) in enumerate(want):
            tile = band.crop((i * w // 3, 0, (i + 1) * w // 3, h))
            check(f"tile {i + 1}: {label} -> {expected}",
                  corners(tile) == expected, f"read {corners(tile)}")


def t_pillow_engine():
    print("C4: the fallback engine (--engine pillow) honours the profile too")
    out = os.path.join(CT, "pillow.pdf")
    r = run_engine(["--src", os.path.join(CT, "single"), "--out", out,
                    "--engine", "pillow"])
    pages = page_images(out)
    got = pages[0] if pages else None
    check(f"tagged JPEG -> {HONOURED}",
          r.returncode == 0 and got is not None and corners(got) == HONOURED,
          f"rc={r.returncode} read {corners(got) if got else None}")


def t_heic():
    print("C5: a tagged HEIC (what iPhones write) on a composed page")
    if not HAVE_HEIC:
        print("  --  skipped: writing a HEIC test picture needs pillow-heif here")
        return
    out = os.path.join(CT, "heic.pdf")
    r = run_engine(["--src", os.path.join(CT, "heic"), "--out", out,
                    "--quality", "80"])
    pages = page_images(out)
    got = pages[0] if pages else None
    check(f"tagged HEIC -> {HONOURED}",
          r.returncode == 0 and got is not None and corners(got) == HONOURED,
          f"rc={r.returncode} read {corners(got) if got else None} {r.stderr[-200:]}")


def t_broken_profile():
    print("C6: an unusable profile never costs the page")
    out = os.path.join(CT, "broken.pdf")
    r = run_engine(["--src", os.path.join(CT, "broken"), "--out", out,
                    "--quality", "80"])
    pages = page_images(out)
    got = pages[0] if pages else None
    check("exits 0 with the page in place", r.returncode == 0 and got is not None,
          (r.stdout + r.stderr)[-400:])
    check("shown as stored, since the profile can't be read",
          got is not None and corners(got) == AS_STORED,
          f"read {corners(got) if got else None}")
    check("no warning, no traceback",
          "WARNING" not in r.stderr and "Traceback" not in r.stderr,
          r.stderr[-400:])


def t_plain_mode_untouched():
    print("C7: plain mode still embeds the file as it is, profile attached")
    from pypdf import PdfReader
    out = os.path.join(CT, "plain.pdf")
    r = run_engine(["--src", os.path.join(CT, "single"), "--out", out])
    space = got = None
    if r.returncode == 0:
        xobjects = PdfReader(out).pages[0]["/Resources"]["/XObject"]
        cs = xobjects[list(xobjects)[0]]["/ColorSpace"]
        space = cs[0] if isinstance(cs, list) else cs
        got = page_images(out)[0]
    check("pixels as stored, and the page keeps the profile for the viewer",
          got is not None and corners(got) == AS_STORED and space == "/ICCBased",
          f"rc={r.returncode} read {corners(got) if got else None} space={space}")


def main():
    setup()
    t_smaller_file()
    t_margins()
    t_three_up()
    t_pillow_engine()
    t_heic()
    t_broken_profile()
    t_plain_mode_untouched()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    if FAIL:
        print(f"fixtures kept for inspection: {WORK}")
    else:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
