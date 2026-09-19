#!/usr/bin/env python3
"""Tests for the optional file-name labels (--names) and their launcher menu.

Two styles are covered: "caption" (each name beside its own picture) and
"summary" (one line per page, optionally starting with the page identifier,
"beach - 0042 | IMG_1234.HEIC").

The one rule every layout test enforces: a label is NEVER drawn over a
picture. Room is found in the margin or made with a thin blank strip; the
picture's own pixels are never touched. To prove that without reading text
back, every fixture picture is a single flat colour on pages that are
embedded losslessly, so a picture's rectangle and the label's ink can both
be measured exactly and compared.

What the label SAYS is tested through the small pure functions that build
the text, against literal expected strings. Nothing inside the repo is
touched.

Run with any Python 3:  python3 tests/test_names.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO, "generate_pdf.py")
LAUNCHER = os.path.join(REPO, "launcher.py")


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

# The launcher only skips its venv setup when it is already running inside
# the project .venv - so the launcher tests must drive it with that interpreter.
VENVPY = venv_python() if os.path.exists(venv_python()) else sys.executable
WORK = tempfile.mkdtemp(prefix="pdfmaker-test-")
NT = os.path.join(WORK, "nt")

PASS = FAIL = 0

BLUE, ORANGE, GREEN = (60, 120, 200), (220, 130, 50), (70, 170, 110)
PORTRAIT = (600, 800)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# Fixtures and measuring tools
# ---------------------------------------------------------------------------
def make_pic(path, colour, size=PORTRAIT):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, colour).save(path)


def run_engine(args):
    return subprocess.run([VENVPY, ENGINE] + args,
                          capture_output=True, text=True, timeout=300)


def run_launcher(argv, answers, timeout=180):
    return subprocess.run([VENVPY, LAUNCHER] + argv, input=answers, text=True,
                          capture_output=True, timeout=timeout)


def pages_of(pdf_path):
    from pypdf import PdfReader
    if not os.path.isfile(pdf_path):
        return []
    out = []
    for page in PdfReader(pdf_path).pages:
        imgs = page.images
        out.append(imgs[0].image.convert("RGB") if imgs else None)
    return out


def build(name, src, extra):
    """Run the engine on folder `src`; return (result, list of page images)."""
    out = os.path.join(NT, name + ".pdf")
    r = run_engine(["--src", os.path.join(NT, src), "--out", out] + extra)
    return r, (pages_of(out) if r.returncode == 0 else [])


def _max_channel_diff(page, colour):
    from PIL import Image, ImageChops
    diff = ImageChops.difference(page, Image.new("RGB", page.size, colour))
    r, g, b = diff.split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def picture_box(page, colour):
    """Rectangle of the pixels that are exactly a fixture picture's colour."""
    return _max_channel_diff(page, colour).point(
        lambda v: 255 if v == 0 else 0).getbbox()


def ink_box(page, keep_out=()):
    """Rectangle of everything that isn't blank paper, ignoring `keep_out`
    rectangles (pictures, a page-number stamp)."""
    from PIL import ImageDraw
    work = page.copy()
    draw = ImageDraw.Draw(work)
    for box in keep_out:
        if box and box[2] > box[0] and box[3] > box[1]:
            draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill="white")
    return _max_channel_diff(work, (255, 255, 255)).point(
        lambda v: 255 if v > 20 else 0).getbbox()


def overlaps(a, b):
    return bool(a and b and a[0] < b[2] and b[0] < a[2]
                and a[1] < b[3] and b[1] < a[3])


def width(box):
    return box[2] - box[0] if box else 0


def centre_x(box):
    return (box[0] + box[2]) / 2


def solid(page, box, colour):
    """True when every pixel of `box` is exactly `colour` (picture untouched)."""
    return page.crop(box).getcolors(maxcolors=4) == [
        ((box[2] - box[0]) * (box[3] - box[1]), colour)]


def setup():
    make_pic(os.path.join(NT, "one", "photo_1.png"), BLUE)
    # lengths/: short name, long name, absurdly long name
    make_pic(os.path.join(NT, "lengths", "a_1.png"), BLUE)
    make_pic(os.path.join(NT, "lengths",
                          "a_considerably_longer_file_name_2.png"), ORANGE)
    make_pic(os.path.join(NT, "lengths", "x" * 140 + "_3.png"), GREEN)
    # same name, different ending (both lossless, so pages compare exactly)
    make_pic(os.path.join(NT, "ext_png", "same_1.png"), BLUE)
    make_pic(os.path.join(NT, "ext_bmp", "same_1.bmp"), BLUE)
    # three/: one 3-up page
    for i, (nm, c) in enumerate((("blue", BLUE), ("orange", ORANGE),
                                 ("green", GREEN)), 1):
        make_pic(os.path.join(NT, "three", f"{nm}_{i}.png"), c)
    # wide/: a landscape picture leaves white space below it on a portrait page
    make_pic(os.path.join(NT, "wide", "wide_1.png"), BLUE, size=(800, 300))
    # longname/: wide enough to reach a page-number corner if nothing stopped it
    make_pic(os.path.join(NT, "longname", "scan_" + "w" * 85 + "_1.png"), BLUE)
    make_pic(os.path.join(NT, "accent", "café_1.png"), BLUE)
    make_pic(os.path.join(NT, "tree", "alpha", "a_1.png"), BLUE)
    make_pic(os.path.join(NT, "tree", "beta", "b_1.png"), ORANGE)
    make_pic(os.path.join(NT, "flat", "pic_1.png"), BLUE)


# ---------------------------------------------------------------------------
# What the labels say
# ---------------------------------------------------------------------------
def t_label_text():
    print("T1: the text of a label")
    sys.path.insert(0, REPO)
    import generate_pdf as g
    label_text = getattr(g, "label_text", lambda *a, **k: None)
    shorten = getattr(g, "shorten_middle", lambda *a, **k: None)
    summary = getattr(g, "summary_text", lambda *a, **k: None)
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    for got, want, what in (
        (label_text(os.path.join("some", "dir", "IMG_1234.HEIC"), False),
         "IMG_1234.HEIC", "the file's own name, folders dropped"),
        (label_text("IMG_1234.HEIC", True), "IMG_1234", "ending hidden on request"),
        (label_text("notes.final.png", True), "notes.final",
         "only the last ending is hidden"),
        (shorten("short.png", 20), "short.png", "short names are left alone"),
        (shorten(alphabet, 11), "abcd...wxyz", "long names keep both ends"),
        (shorten(alphabet, 10), "abcd...xyz", "odd space goes to the front"),
        (summary(["a.png", "b.png", "c.png"]), "a.png | b.png | c.png",
         "summary lists the page's files in order"),
        (summary(["IMG_1234.HEIC"], number=42, prefix="beach"),
         "beach - 0042 | IMG_1234.HEIC", "page identifier leads the summary"),
        (summary(["x.png"], number=7), "0007 | x.png",
         "identifier without a folder name is just the number"),
    ):
        check(what, got == want, f"got {got!r}, want {want!r}")


def t_label_font():
    print("T2: a label never shows a missing-glyph box")
    sys.path.insert(0, REPO)
    import generate_pdf as g
    pick = getattr(g, "label_font_for", None)
    if pick is None:
        check("label_font_for exists", False, "not implemented")
        return

    def has_glyph(font, ch):
        return bytes(font.getmask(ch)) != bytes(font.getmask("\uffff"))

    for text in ("plain_name_01.png", "café_ñandú.jpg",
                 "写真_01.jpg"):
        font, shown = pick(text, 20)
        ok = len(shown) == len(text) and all(
            ch.isspace() or has_glyph(font, ch) for ch in shown)
        check(f"{text!r}: every shown character has a real glyph", ok,
              f"shown as {shown!r}")
        if text.isascii():
            check("plain ASCII names are shown exactly", shown == text, shown)
        else:
            check("unshowable characters can only ever become '?'",
                  all(s == t or s == "?" for s, t in zip(shown, text)), shown)


# ---------------------------------------------------------------------------
# Where the labels go - one picture per page
# ---------------------------------------------------------------------------
def t_plain_caption_below():
    print("T3: picture fills the page -> a strip is added under it")
    r, pages = build("plain_off", "one", [])
    check("without --names the page is still exactly the picture",
          r.returncode == 0 and pages and pages[0].size == PORTRAIT,
          f"rc={r.returncode} size={pages[0].size if pages else None}")
    r, pages = build("plain_below", "one", ["--names", "caption"])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    if not pages:
        return
    page = pages[0]
    w, h = page.size
    check("same width, a little taller (a strip, not a second page)",
          w == 600 and 800 < h <= 880 and len(pages) == 1, f"size={page.size}")
    check("the picture's pixels are untouched, at the top",
          solid(page, (0, 0, 600, 800), BLUE))
    ink = ink_box(page, keep_out=[(0, 0, 600, 800)])
    check("the name is printed in the strip below",
          ink is not None and ink[1] >= 800 and ink[3] <= h, f"ink={ink}")
    check("centred under the picture",
          ink is not None and abs(centre_x(ink) - 300) <= 3, f"ink={ink}")


def t_plain_caption_above():
    print("T4: --names-position above puts the strip on top (and implies --names)")
    r, pages = build("plain_above", "one", ["--names-position", "above"])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    if not pages:
        return
    page = pages[0]
    w, h = page.size
    check("page grew", w == 600 and 800 < h <= 880, f"size={page.size}")
    check("the picture's pixels are untouched, at the bottom",
          solid(page, (0, h - 800, 600, h), BLUE))
    ink = ink_box(page, keep_out=[(0, h - 800, 600, h)])
    check("the name is printed in the strip above",
          ink is not None and ink[3] <= h - 800, f"ink={ink}")


def t_name_lengths():
    print("T5: long names shrink or shorten to fit - never spill, never vanish")
    r, pages = build("lengths", "lengths", ["--names", "caption"])
    check("exits 0 with 3 pages", r.returncode == 0 and len(pages) == 3,
          (r.stdout + r.stderr)[-400:])
    if len(pages) != 3:
        return
    inks = [ink_box(p, keep_out=[(0, 0, 600, 800)]) for p in pages]
    check("every page has its label", all(inks), str(inks))
    if all(inks):
        check("a longer name makes a wider label", width(inks[1]) > width(inks[0]),
              f"{width(inks[0])} vs {width(inks[1])}")
        check("a 146-character name still fits inside the page width",
              inks[2][0] >= 4 and inks[2][2] <= 596, f"ink={inks[2]}")
        check("...and is still clearly there (not shrunk to nothing)",
              width(inks[2]) > width(inks[0]), f"{width(inks[2])}")
        check("pictures untouched on all three pages",
              all(solid(p, (0, 0, 600, 800), c)
                  for p, c in zip(pages, (BLUE, ORANGE, GREEN))))


def t_hide_extension():
    print("T6: --names-hide-ext drops the ending")
    strips = {}
    for label, extra in (("shown", ["--names", "caption"]),
                         ("hidden", ["--names-hide-ext"])):
        for src in ("ext_png", "ext_bmp"):
            r, pages = build(f"{src}_{label}", src, extra)
            ok = r.returncode == 0 and pages and pages[0].size[1] > 800
            strips[src, label] = (pages[0].crop((0, 800) + pages[0].size).tobytes()
                                  if ok else None)
    check("all four runs made a labelled page", all(strips.values()),
          str({k: v is not None for k, v in strips.items()}))
    if all(strips.values()):
        check("endings shown: same_1.png and same_1.bmp read differently",
              strips["ext_png", "shown"] != strips["ext_bmp", "shown"])
        check("endings hidden: both read exactly the same ('same_1')",
              strips["ext_png", "hidden"] == strips["ext_bmp", "hidden"])


def t_margins_use_the_margin():
    print("T7: with note margins the label goes in the margin - picture unmoved")
    base = ["--page", "letter", "--margin", "1"]
    r0, p0 = build("margin_off", "one", base)
    r1, p1 = build("margin_on", "one", base + ["--names", "caption"])
    check("both runs exit 0", r0.returncode == 0 and r1.returncode == 0,
          (r1.stdout + r1.stderr)[-400:])
    if not (p0 and p1):
        return
    before, after = picture_box(p0[0], BLUE), picture_box(p1[0], BLUE)
    check("same page size", p0[0].size == p1[0].size, f"{p0[0].size} {p1[0].size}")
    check("picture is exactly where and as big as it was", before == after,
          f"{before} -> {after}")
    ink = ink_box(p1[0], keep_out=[after])
    check("label sits below the picture, on the page",
          ink is not None and ink[1] >= after[3] and ink[3] <= p1[0].size[1],
          f"ink={ink} picture={after}")
    check("centred on the picture",
          ink is not None and abs(centre_x(ink) - centre_x(after)) <= 3,
          f"ink={ink} picture={after}")
    check("the label never touches the picture", not overlaps(ink, after))


def t_no_room_makes_room():
    print("T8: fixed page with no blank room -> the picture gives way, never the rule")
    base = ["--page", "letter"]  # a 600x800 picture touches top and bottom
    r0, p0 = build("noroom_off", "one", base)
    r1, p1 = build("noroom_on", "one", base + ["--names", "caption"])
    check("both runs exit 0", r0.returncode == 0 and r1.returncode == 0,
          (r1.stdout + r1.stderr)[-400:])
    if not (p0 and p1):
        return
    before, after = picture_box(p0[0], BLUE), picture_box(p1[0], BLUE)
    check("paper size is unchanged", p0[0].size == p1[0].size)
    check("without labels the picture reached the bottom edge",
          before is not None and before[3] == p0[0].size[1], f"{before}")
    check("with labels it is slightly smaller and ends higher",
          after is not None and after[3] < before[3]
          and (after[3] - after[1]) < (before[3] - before[1]), f"{before} -> {after}")
    ink = ink_box(p1[0], keep_out=[after])
    check("label fits between picture and paper edge",
          ink is not None and ink[1] >= after[3] and ink[3] <= p1[0].size[1],
          f"ink={ink} picture={after}")
    check("the label never touches the picture", not overlaps(ink, after))


# ---------------------------------------------------------------------------
# Three per page, and the summary style
# ---------------------------------------------------------------------------
def three_up(name, extra):
    r, pages = build(name, "three", ["--per-page", "3"] + extra)
    page = pages[0] if len(pages) == 1 else None
    tiles = [picture_box(page, c) for c in (BLUE, ORANGE, GREEN)] if page else []
    return r, page, tiles


def t_three_up_captions():
    print("T9: three per page -> each name under its own picture")
    r, page, tiles = three_up("three_caption", ["--names", "caption"])
    check("exits 0 with one page and three pictures",
          r.returncode == 0 and page is not None and all(tiles),
          (r.stdout + r.stderr)[-400:])
    if not (page and all(tiles)):
        return
    w, h = page.size
    for i, tile in enumerate(tiles):
        column = (i * w // 3, 0, (i + 1) * w // 3, h)
        others = [t for t in tiles if t is not tile]
        blank = [(0, 0, column[0], h), (column[2], 0, w, h)]  # hide other columns
        ink = ink_box(page, keep_out=tiles + blank)
        check(f"picture {i + 1}: label below it, centred on it",
              ink is not None and ink[1] >= tile[3]
              and abs(centre_x(ink) - centre_x(tile)) <= 4,
              f"ink={ink} tile={tile}")
        check(f"picture {i + 1}: label touches no picture",
              ink is not None and not any(overlaps(ink, t) for t in [tile] + others))


def t_three_up_summary():
    print("T10: summary style -> one line per page, below all three pictures")
    r, page, tiles = three_up("three_summary", ["--names", "summary"])
    check("exits 0 with one page and three pictures",
          r.returncode == 0 and page is not None and all(tiles),
          (r.stdout + r.stderr)[-400:])
    if not (page and all(tiles)):
        return
    w, h = page.size
    ink = ink_box(page, keep_out=tiles)
    lowest = max(t[3] for t in tiles)
    check("the line is below every picture and on the page",
          ink is not None and ink[1] >= lowest and ink[3] <= h,
          f"ink={ink} lowest picture edge={lowest}")
    check("one line, centred on the page (not on any one picture)",
          ink is not None and abs(centre_x(ink) - w / 2) <= 4
          and (ink[3] - ink[1]) < 0.05 * h, f"ink={ink} page={page.size}")
    check("it touches no picture",
          ink is not None and not any(overlaps(ink, t) for t in tiles))
    r2, page2, tiles2 = three_up("three_summary_id", ["--names-id"])
    ink2 = ink_box(page2, keep_out=tiles2) if page2 else None
    check("--names-id (implies summary) makes the line longer: the identifier leads it",
          r2.returncode == 0 and ink2 is not None and width(ink2) > width(ink),
          f"{width(ink)} -> {width(ink2)} {r2.stderr[-200:]}")


def t_caption_hugs_summary_sits_at_foot():
    print("T11: caption hugs its picture; summary keeps to the foot of the page")
    base = ["--page", "letter", "--margin", "1"]
    rc, pc = build("wide_caption", "wide", base + ["--names", "caption"])
    rs, ps = build("wide_summary", "wide", base + ["--names", "summary"])
    check("both runs exit 0", rc.returncode == 0 and rs.returncode == 0,
          (rc.stderr + rs.stderr)[-400:])
    if not (pc and ps):
        return
    pic_c, pic_s = picture_box(pc[0], BLUE), picture_box(ps[0], BLUE)
    ink_c = ink_box(pc[0], keep_out=[pic_c])
    ink_s = ink_box(ps[0], keep_out=[pic_s])
    h = pc[0].size[1]
    check("picture is in the same place either way", pic_c == pic_s)
    check("caption starts right under the picture",
          ink_c is not None and 0 <= ink_c[1] - pic_c[3] <= 0.03 * h,
          f"gap={ink_c[1] - pic_c[3] if ink_c else None}")
    check("summary is far below it, in the bottom margin",
          ink_s is not None and ink_s[1] - pic_s[3] > 0.2 * h
          and ink_s[1] >= h - h * (1 / 11) - 2, f"ink={ink_s} page height={h}")


def t_names_id_needs_summary():
    print("T12: --names-id only makes sense for the summary style")
    r, _ = build("bad_combo", "one", ["--names", "caption", "--names-id"])
    check("caption + --names-id is refused with a reason",
          r.returncode != 0 and "summary" in r.stderr.lower()
          and "Traceback" not in r.stderr, f"rc={r.returncode} {r.stderr[-300:]}")


def t_page_numbers_left_alone():
    print("T13: a long label keeps clear of the page number")
    base = ["--page", "letter", "--margin", "0.5"]
    rn, pn = build("num_only", "longname", base + ["--number-pages"])
    rb, pb = build("num_and_names", "longname",
                   base + ["--number-pages", "--names", "caption"])
    check("both runs exit 0", rn.returncode == 0 and rb.returncode == 0,
          (rb.stdout + rb.stderr)[-400:])
    if not (pn and pb):
        return
    pic = picture_box(pb[0], BLUE)
    number = ink_box(pn[0], keep_out=[picture_box(pn[0], BLUE)])
    check("the number stamp is pixel-for-pixel what it was without labels",
          number is not None
          and pn[0].crop(number).tobytes() == pb[0].crop(number).tobytes(),
          f"number={number}")
    label = ink_box(pb[0], keep_out=[pic, number])
    grown = (number[0] - 2, number[1] - 2, number[2] + 2, number[3] + 2) if number else None
    check("the label is there, and stops short of the number",
          label is not None and not overlaps(label, grown),
          f"label={label} number={number}")
    check("...and still never touches the picture", not overlaps(label, pic))


def t_other_paths():
    print("T14: the same labels in batch mode, the fallback engine, odd names")
    outdir = os.path.join(NT, "tree_out")
    r = run_engine(["--recursive", "--src", os.path.join(NT, "tree"),
                    "--out", outdir, "--names-id"])
    sizes = [pages_of(os.path.join(outdir, n))[0].size
             for n in ("alpha.pdf", "beta.pdf")
             if os.path.isfile(os.path.join(outdir, n))]
    check("--recursive: every folder's pages carry the summary strip",
          r.returncode == 0 and len(sizes) == 2
          and all(s[0] == 600 and s[1] > 800 for s in sizes),
          f"rc={r.returncode} sizes={sizes} {r.stderr[-200:]}")

    r, pages = build("pillow_names", "one", ["--engine", "pillow", "--names", "caption"])
    grew = bool(pages) and pages[0].size[0] == 600 and pages[0].size[1] > 800
    dark = False
    if grew:  # this engine stores JPEG, so look for clearly dark text pixels
        strip = pages[0].crop((0, 806, 600, pages[0].size[1])).convert("L")
        dark = strip.getextrema()[0] < 140
    check("--engine pillow: strip added, with text in it", grew and dark,
          f"rc={r.returncode} size={pages[0].size if pages else None}")

    r, pages = build("accent", "accent", ["--names", "caption"])
    ink = ink_box(pages[0], keep_out=[(0, 0, 600, 800)]) if pages else None
    check("a name with an accented letter is labelled without fuss",
          r.returncode == 0 and ink is not None and "Traceback" not in r.stderr,
          f"rc={r.returncode} {r.stderr[-300:]}")


# ---------------------------------------------------------------------------
# Launcher: the gate and its nested menu
# ---------------------------------------------------------------------------
def launcher_page(answers):
    flat = os.path.join(NT, "flat")
    out = flat + ".pdf"
    if os.path.exists(out):
        os.remove(out)
    r = run_launcher(["make", flat], answers)
    pages = pages_of(out)
    return r, (pages[0] if pages else None)


def t_launcher_menu():
    print("L1: the launcher asks first, and 'No' is one keypress (Return)")
    # pictures/page, margin, size, numbers, FILE NAMES, split, another folder
    r, page = launcher_page("\n" * 7)
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("the question is asked", "file names" in r.stdout.lower(), r.stdout[-900:])
    check("plain Return means no labels: page is exactly the picture",
          page is not None and page.size == PORTRAIT,
          f"size={page.size if page else None}")
    check("no sub-questions after 'No'", "Caption" not in r.stdout, r.stdout[-900:])

    print("L2: 'Yes' opens the nested menu; Return all the way = caption below")
    r, page = launcher_page("\n\n\n\n" + "2\n\n\n\n" + "\n\n")
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("style, place and ending are each offered",
          all(k in r.stdout for k in ("Caption", "Summary", "page identifier",
                                      "Below", "Above", "ending")), r.stdout[-1500:])
    check("the page got its strip, picture untouched at the top",
          page is not None and page.size[0] == 600 and page.size[1] > 800
          and solid(page, (0, 0, 600, 800), BLUE),
          f"size={page.size if page else None}")
    check("launcher output stays pure ASCII",
          all(ord(ch) < 128 for ch in r.stdout),
          repr([ch for ch in r.stdout if ord(ch) >= 128][:5]))

    print("L3: the nested choices reach the engine")
    # style 3 = summary with page identifier, place 2 = above, ending 2 = hidden
    r, page = launcher_page("\n\n\n\n" + "2\n3\n2\n2\n" + "\n\n")
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("the engine reports: summary, page identifier, above, ending hidden",
          all(k in r.stdout for k in ("summary", "page id", "above", "no ending")),
          r.stdout[-700:])
    check("strip is on top this time",
          page is not None and page.size[1] > 800
          and solid(page, (0, page.size[1] - 800, 600, page.size[1]), BLUE),
          f"size={page.size if page else None}")


def main():
    setup()
    t_label_text()
    t_label_font()
    t_plain_caption_below()
    t_plain_caption_above()
    t_name_lengths()
    t_hide_extension()
    t_margins_use_the_margin()
    t_no_room_makes_room()
    t_three_up_captions()
    t_three_up_summary()
    t_caption_hugs_summary_sits_at_foot()
    t_names_id_needs_summary()
    t_page_numbers_left_alone()
    t_other_paths()
    t_launcher_menu()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    if FAIL:
        print(f"fixtures kept for inspection: {WORK}")
    else:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
