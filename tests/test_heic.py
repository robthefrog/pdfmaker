#!/usr/bin/env python3
"""Tests for HEIC/HEIF (iPhone photo) support in generate_pdf.py and launcher.py.

Every .heic used here is SYNTHETIC: four-colour "quadrant cards" written at
test time into a temporary folder (with pillow-heif when it is importable,
otherwise with macOS's built-in `sips`). No real photos are involved and
nothing inside the repo is touched. Because each corner of a card has its
own colour, a page that comes out sideways or upside-down is caught from
its pixels, not guessed from its size.

A machine where the HEIC plugin could not be installed is simulated with a
PYTHONPATH folder holding a stand-in `pillow_heif` that refuses to import,
and the launcher's download step with a stand-in `pip` that only records
how it was called - so these tests never touch the network or the real .venv.

Run with any Python 3:  python3 tests/test_heic.py
"""
import json
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

try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # lets Pillow write the test pictures
    HAVE_PLUGIN = True
except Exception:
    HAVE_PLUGIN = False
HAVE_SIPS = sys.platform == "darwin" and shutil.which("sips") is not None

# The launcher only skips its venv setup when it is already running inside
# the project .venv - so the tests must drive it with that interpreter.
VENVPY = venv_python() if os.path.exists(venv_python()) else sys.executable
WORK = tempfile.mkdtemp(prefix="pdfmaker-test-")
HT = os.path.join(WORK, "ht")

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
# Synthetic pictures
# ---------------------------------------------------------------------------
QUADRANTS = {"R": (220, 30, 30), "G": (30, 180, 30),
             "B": (30, 30, 220), "Y": (230, 210, 30)}


def card(size, grain=0):
    """Quadrant card: top-left Red, top-right Green, bottom-left Blue,
    bottom-right Yellow - so reading the corners gives "RGBY" when upright.
    grain > 0 adds camera-like noise, which (like a real photo) a lossless
    PNG can't squeeze but a JPEG can."""
    from PIL import Image, ImageChops
    w, h = size
    im = Image.new("RGB", size)
    im.paste(QUADRANTS["R"], (0, 0, w // 2, h // 2))
    im.paste(QUADRANTS["G"], (w // 2, 0, w, h // 2))
    im.paste(QUADRANTS["B"], (0, h // 2, w // 2, h))
    im.paste(QUADRANTS["Y"], (w // 2, h // 2, w, h))
    if grain:
        noise = Image.effect_noise(size, grain).convert("RGB")
        im = ImageChops.add(im, noise, 1, -128)
    return im


def colour_name(rgb):
    """Nearest quadrant colour (HEVC and JPEG are lossy, so never exact)."""
    r, g, b = rgb[:3]
    best = min(QUADRANTS, key=lambda k: sum(
        (a - c) ** 2 for a, c in zip((r, g, b), QUADRANTS[k])))
    dist = sum((a - c) ** 2 for a, c in zip((r, g, b), QUADRANTS[best]))
    return best if dist < 60 ** 2 else "?"


def corners(im):
    """The four quadrant colours read TL, TR, BL, BR - e.g. "RGBY".
    Each quadrant is averaged (a 2x2 box shrink), so grain and compression
    artefacts can't flip a reading."""
    from PIL import Image
    tiny = im.convert("RGB").resize((2, 2), Image.BOX)
    return "".join(colour_name(tiny.getpixel(p))
                   for p in ((0, 0), (1, 0), (0, 1), (1, 1)))


def make_png(path, color, size=(60, 80)):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path)


def exif_bytes(orientation):
    from PIL import Image
    ex = Image.Exif()
    ex[0x0112] = orientation
    return ex.tobytes()


def make_heic_sips(path, size, orientation=None, grain=0):
    """Apple's own encoder: tiles big pictures into a 512px grid and stores a
    rotation as irot + EXIF, exactly like a real iPhone photo."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if orientation:
        src = path + ".src.jpg"
        card(size, grain).save(src, quality=95, exif=exif_bytes(orientation))
    else:
        src = path + ".src.png"
        card(size, grain).save(src)
    r = subprocess.run(["sips", "-s", "format", "heic", src, "--out", path],
                       capture_output=True, text=True)
    os.remove(src)
    if r.returncode != 0 or not os.path.isfile(path):
        raise RuntimeError(f"sips could not write {path}: {r.stderr[-200:]}")


def make_heic(path, size=(160, 120), orientation=None, grain=0):
    """Write a synthetic HEIC card. `orientation` is an EXIF Orientation value
    (6 = "turn me 90 degrees clockwise", what an iPhone held upright stores)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if HAVE_PLUGIN:
        extra = {"exif": exif_bytes(orientation)} if orientation else {}
        card(size, grain).save(path, format="HEIF", quality=90, **extra)
    else:
        make_heic_sips(path, size, orientation, grain)


# ---------------------------------------------------------------------------
# Running the tools, optionally on a simulated "HEIC can't be installed" machine
# ---------------------------------------------------------------------------
def make_stub_dir(name, *, block_plugin, fake_pip):
    """A PYTHONPATH folder that shadows site-packages for one subprocess.

    block_plugin: a `pillow_heif` that raises ImportError, i.e. a machine
                  where the plugin is absent or its wheel doesn't work.
    fake_pip:     a `pip` that appends its arguments to the log file named in
                  PDFMAKER_TEST_PIP_LOG and exits with PDFMAKER_TEST_PIP_EXIT,
                  installing nothing.
    """
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    if block_plugin:
        with open(os.path.join(d, "pillow_heif.py"), "w") as f:
            f.write('raise ImportError("simulated: pillow-heif is not installed")\n')
    if fake_pip:
        os.makedirs(os.path.join(d, "pip"), exist_ok=True)
        with open(os.path.join(d, "pip", "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(d, "pip", "__main__.py"), "w") as f:
            f.write("import json, os, sys\n"
                    'with open(os.environ["PDFMAKER_TEST_PIP_LOG"], "a") as f:\n'
                    '    f.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                    'sys.exit(int(os.environ.get("PDFMAKER_TEST_PIP_EXIT", "1")))\n')
    return d


def env_with(stub_dir, pip_log=None, pip_exit=1):
    env = dict(os.environ)
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = stub_dir + (os.pathsep + old if old else "")
    if pip_log:
        env["PDFMAKER_TEST_PIP_LOG"] = pip_log
        env["PDFMAKER_TEST_PIP_EXIT"] = str(pip_exit)
    return env


def pip_calls(pip_log):
    if not os.path.isfile(pip_log):
        return []
    with open(pip_log) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_engine(args, env=None):
    return subprocess.run([VENVPY, ENGINE] + args, env=env,
                          capture_output=True, text=True, timeout=300)


def run_launcher(argv, answers, env=None, timeout=180):
    return subprocess.run([VENVPY, LAUNCHER] + argv, env=env,
                          input=answers, text=True, capture_output=True,
                          timeout=timeout)


def pdf_pages(path):
    from pypdf import PdfReader
    return len(PdfReader(path).pages) if os.path.isfile(path) else None


def page_image(pdf_path, index=0):
    from pypdf import PdfReader
    if not os.path.isfile(pdf_path):
        return None
    imgs = PdfReader(pdf_path).pages[index].images
    return imgs[0].image.convert("RGB") if imgs else None


def listing(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else None


def setup():
    # mixed: a PNG, an iPhone-style upper-case .HEIC and a .heif, in that order
    make_png(os.path.join(HT, "mixed", "a_1.png"), "white")
    make_heic(os.path.join(HT, "mixed", "IMG_2.HEIC"))
    make_heic(os.path.join(HT, "mixed", "pic_3.heif"))
    # turned: one landscape-stored card flagged "rotate 90 degrees clockwise"
    make_heic(os.path.join(HT, "turned", "IMG_1.HEIC"), orientation=6)
    # tree: a PNG-only folder next to a HEIC-only folder
    make_png(os.path.join(HT, "tree", "drawings", "d_1.png"), "green")
    make_heic(os.path.join(HT, "tree", "phone", "IMG_1.HEIC"))
    make_heic(os.path.join(HT, "tree", "phone", "IMG_2.HEIC"))
    # onlyheic: nothing but HEIC; four: enough HEIC to spill onto a 2nd 3-up page
    make_heic(os.path.join(HT, "onlyheic", "IMG_1.HEIC"))
    for i in range(1, 5):
        make_heic(os.path.join(HT, "four", f"IMG_{i}.HEIC"))
    # broken: a good PNG beside a .heic that is not a picture at all
    make_png(os.path.join(HT, "broken", "ok_1.png"), "blue")
    with open(os.path.join(HT, "broken", "bad_2.heic"), "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypheic this is not really a heic file")
    # flat: no HEIC anywhere
    make_png(os.path.join(HT, "flat", "p_1.png"), "red")
    make_png(os.path.join(HT, "flat", "p_2.png"), "blue")
    # phonetree: ONLY HEIC, and only inside subfolders
    make_heic(os.path.join(HT, "phonetree", "monday", "IMG_1.HEIC"))
    make_heic(os.path.join(HT, "phonetree", "tuesday", "IMG_1.HEIC"))


# ---------------------------------------------------------------------------
# Engine, HEIC readable
# ---------------------------------------------------------------------------
def t_heic_pages_in_order():
    print("H1: HEIC and HEIF pictures become pages, in filename order")
    out = os.path.join(HT, "mixed.pdf")
    r = run_engine(["--src", os.path.join(HT, "mixed"), "--out", out])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("all 3 pictures became pages (.png + .HEIC + .heif)",
          pdf_pages(out) == 3, f"pages={pdf_pages(out)} {r.stderr[-300:]}")
    check("nothing reported as ignored", "ignoring" not in r.stderr, r.stderr[-300:])
    if pdf_pages(out) == 3:
        for idx, name in ((1, "IMG_2.HEIC"), (2, "pic_3.heif")):
            got = page_image(out, idx)
            check(f"page {idx + 1} really shows {name} (160x120 card, RGBY)",
                  got is not None and got.size == (160, 120)
                  and corners(got) == "RGBY",
                  f"size={getattr(got, 'size', None)} "
                  f"corners={corners(got) if got else None}")


def t_rotated_heic_is_upright():
    print("H2: a rotated iPhone-style HEIC lands upright on every build path")
    # Stored 160x120 as RGBY and flagged "turn 90 degrees clockwise": upright
    # is 120x160 with the stored left column on top -> corners read BRYG.
    for label, extra in (("plain img2pdf", []),
                         ("pillow engine", ["--engine", "pillow"]),
                         ("composed JPEG", ["--quality", "90"])):
        out = os.path.join(HT, "turned_" + label.replace(" ", "_") + ".pdf")
        r = run_engine(["--src", os.path.join(HT, "turned"), "--out", out] + extra)
        got = page_image(out) if r.returncode == 0 else None
        check(f"{label}: portrait 120x160 with corners BRYG",
              got is not None and got.size == (120, 160)
              and corners(got) == "BRYG",
              f"rc={r.returncode} size={getattr(got, 'size', None)} "
              f"corners={corners(got) if got else None} {r.stderr[-200:]}")


def t_layout_modes_accept_heic():
    print("H3: margins and 3-per-page layouts accept HEIC too")
    src = os.path.join(HT, "mixed")
    out = os.path.join(HT, "mixed_margin.pdf")
    r = run_engine(["--src", src, "--out", out, "--page", "letter",
                    "--margin", "0.5", "--quality", "70"])
    check("letter + margin: exits 0 with 3 pages",
          r.returncode == 0 and pdf_pages(out) == 3,
          f"rc={r.returncode} pages={pdf_pages(out)} {r.stderr[-300:]}")
    # Four HEIC cards, three to a page -> 3 + 1 = exactly 2 pages.
    out = os.path.join(HT, "four_3up.pdf")
    r = run_engine(["--src", os.path.join(HT, "four"), "--out", out,
                    "--per-page", "3"])
    check("3-per-page: 4 HEIC pictures fill 2 landscape pages",
          r.returncode == 0 and pdf_pages(out) == 2,
          f"rc={r.returncode} pages={pdf_pages(out)} {r.stderr[-300:]}")


def t_recursive_heic_only_folder():
    print("H4: --recursive gives a HEIC-only folder its own PDF")
    outdir = os.path.join(HT, "tree_out")
    r = run_engine(["--recursive", "--src", os.path.join(HT, "tree"),
                    "--out", outdir])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("both folders produced a PDF",
          listing(outdir) == ["drawings.pdf", "phone.pdf"], str(listing(outdir)))
    check("phone.pdf holds its 2 HEIC pictures",
          pdf_pages(os.path.join(outdir, "phone.pdf")) == 2)


def t_corrupt_heic_is_skipped():
    print("H5: a corrupt .heic is skipped by name; the rest still builds")
    out = os.path.join(HT, "broken.pdf")
    r = run_engine(["--src", os.path.join(HT, "broken"), "--out", out])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("the good picture still made a 1-page PDF", pdf_pages(out) == 1)
    check("WARNING names the bad file",
          "WARNING" in r.stderr and "bad_2.heic" in r.stderr, r.stderr[-400:])
    check("no traceback", "Traceback" not in r.stderr, r.stderr[-400:])


def t_photo_heic_stays_sanely_sized():
    print("H7: a grainy, photo-like HEIC doesn't balloon the PDF")
    import io
    size = (800, 600)
    src = os.path.join(HT, "grainy")
    make_heic(os.path.join(src, "IMG_1.HEIC"), size, grain=25)
    # Yardstick: the same grainy card stored losslessly. A page embedded as
    # a PNG costs about this much - several times the HEIC it came from.
    buf = io.BytesIO()
    card(size, grain=25).save(buf, format="PNG")
    lossless = len(buf.getvalue())
    out = os.path.join(HT, "grainy.pdf")
    r = run_engine(["--src", src, "--out", out])
    got = page_image(out) if r.returncode == 0 else None
    check("page is the full-size upright card",
          got is not None and got.size == size and corners(got) == "RGBY",
          f"rc={r.returncode} size={getattr(got, 'size', None)} {r.stderr[-200:]}")
    pdf_bytes = os.path.getsize(out) if os.path.isfile(out) else None
    check("PDF is under half the lossless-PNG cost of that page",
          pdf_bytes is not None and pdf_bytes < lossless / 2,
          f"pdf={pdf_bytes} bytes vs lossless page={lossless} bytes")


def t_colour_profile_survives():
    print("H9: a HEIC's colour profile (iPhones tag Display P3) reaches the PDF")
    if not HAVE_PLUGIN:
        print("  --  skipped: writing a profile-tagged HEIC needs pillow-heif here")
        return
    from PIL import ImageCms
    from pypdf import PdfReader
    src = os.path.join(HT, "tagged")
    os.makedirs(src, exist_ok=True)
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    card((160, 120)).save(os.path.join(src, "IMG_1.HEIC"), format="HEIF",
                          quality=90, icc_profile=icc)
    # Without its profile a wide-gamut photo is shown as if it were plain
    # sRGB - visibly washed out - so the page must stay ICC-tagged on the
    # default path and on the numbered one alike.
    for label, extra in (("plain", []), ("with page numbers", ["--number-pages"])):
        out = os.path.join(HT, "tagged_" + label.replace(" ", "_") + ".pdf")
        r = run_engine(["--src", src, "--out", out] + extra)
        space = None
        if r.returncode == 0:
            xobjects = PdfReader(out).pages[0]["/Resources"]["/XObject"]
            cs = xobjects[list(xobjects)[0]]["/ColorSpace"]
            space = cs[0] if isinstance(cs, list) else cs
        check(f"{label}: page image is ICC-tagged, not bare DeviceRGB",
              space == "/ICCBased", f"rc={r.returncode} colourspace={space}")


def t_apple_tiled_heic():
    print("H6: an Apple-encoded, tiled + rotated HEIC (iPhone layout) reads upright")
    if not HAVE_SIPS:
        print("  --  skipped: needs macOS `sips` to write an Apple-encoded file")
        return
    # 1100x800 is bigger than one 512px tile, so Apple writes a 'grid' item
    # of tiles plus irot + EXIF - the same layout a real iPhone photo has.
    src = os.path.join(HT, "apple")
    make_heic_sips(os.path.join(src, "IMG_1.HEIC"), (1100, 800), orientation=6)
    out = os.path.join(HT, "apple.pdf")
    r = run_engine(["--src", src, "--out", out])
    got = page_image(out) if r.returncode == 0 else None
    check("decodes to an upright 800x1100 page with corners BRYG",
          got is not None and got.size == (800, 1100) and corners(got) == "BRYG",
          f"rc={r.returncode} size={getattr(got, 'size', None)} "
          f"corners={corners(got) if got else None} {r.stderr[-300:]}")


# ---------------------------------------------------------------------------
# Engine, HEIC plugin unavailable (simulated)
# ---------------------------------------------------------------------------
def t_engine_without_plugin():
    print("H8: without the HEIC plugin the engine says so and carries on")
    env = env_with(make_stub_dir("stub_noplugin", block_plugin=True, fake_pip=False))

    out = os.path.join(HT, "mixed_noplugin.pdf")
    r = run_engine(["--src", os.path.join(HT, "mixed"), "--out", out], env=env)
    check("mixed folder: exits 0 and builds from the PNG alone",
          r.returncode == 0 and pdf_pages(out) == 1,
          f"rc={r.returncode} pages={pdf_pages(out)} {r.stderr[-300:]}")
    check("says how many HEIC files it left out, and what would fix it",
          "2 HEIC" in r.stderr and "pillow-heif" in r.stderr, r.stderr[-400:])
    check("no traceback", "Traceback" not in r.stderr, r.stderr[-400:])

    out = os.path.join(HT, "onlyheic_noplugin.pdf")
    r = run_engine(["--src", os.path.join(HT, "onlyheic"), "--out", out], env=env)
    check("HEIC-only folder: fails cleanly, and the reason mentions HEIC",
          r.returncode != 0 and "HEIC" in r.stderr and not os.path.exists(out)
          and "Traceback" not in r.stderr, f"rc={r.returncode} {r.stderr[-400:]}")

    outdir = os.path.join(HT, "tree_noplugin")
    r = run_engine(["--recursive", "--src", os.path.join(HT, "tree"),
                    "--out", outdir], env=env)
    check("--recursive: the readable folder still gets its PDF",
          r.returncode == 0 and listing(outdir) == ["drawings.pdf"],
          f"rc={r.returncode} {listing(outdir)} {r.stderr[-300:]}")
    check("--recursive: the HEIC-only folder is reported, not silently dropped",
          "2 HEIC" in r.stderr, r.stderr[-400:])


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------
def t_launcher_adds_support_on_demand():
    print("L1: HEIC in the folder + plugin missing -> one wheels-only install try")
    stub = make_stub_dir("stub_noplugin_fakepip", block_plugin=True, fake_pip=True)
    # pip failing (offline) and pip "succeeding" with a plugin that still
    # won't import (broken wheel) must both end the same, honest way.
    for pip_exit in (1, 0):
        log = os.path.join(WORK, f"pip_log_exit{pip_exit}.txt")
        out = os.path.join(HT, "mixed.pdf")
        if os.path.exists(out):
            os.remove(out)
        r = run_launcher(["make", os.path.join(HT, "mixed")], "\n" * 6,
                         env=env_with(stub, log, pip_exit))
        calls = pip_calls(log)
        tag = f"pip exit {pip_exit}"
        check(f"{tag}: launcher still exits 0", r.returncode == 0,
              (r.stdout + r.stderr)[-400:])
        check(f"{tag}: exactly one install attempt", len(calls) == 1, str(calls))
        if len(calls) == 1:
            check(f"{tag}: it installs pillow-heif",
                  "install" in calls[0] and "pillow-heif" in calls[0], str(calls[0]))
            check(f"{tag}: wheels only - never tries to compile",
                  "--only-binary" in calls[0], str(calls[0]))
        check(f"{tag}: PDF still made from the readable picture",
              pdf_pages(out) == 1, f"pages={pdf_pages(out)}")
        check(f"{tag}: tells the user HEIC support couldn't be added",
              "couldn't add" in r.stdout.lower() and "HEIC" in r.stdout,
              r.stdout[-700:])
        check(f"{tag}: launcher output stays pure ASCII",
              all(ord(ch) < 128 for ch in r.stdout),
              repr([ch for ch in r.stdout if ord(ch) >= 128][:5]))


def t_launcher_leaves_pip_alone_without_heic():
    print("L2: no HEIC in the folder -> no install attempt, no delay")
    stub = make_stub_dir("stub_noplugin_fakepip", block_plugin=True, fake_pip=True)
    log = os.path.join(WORK, "pip_log_flat.txt")
    r = run_launcher(["make", os.path.join(HT, "flat")], "\n" * 6,
                     env=env_with(stub, log))
    check("exits 0 and makes the PDF", r.returncode == 0
          and pdf_pages(os.path.join(HT, "flat.pdf")) == 2,
          (r.stdout + r.stderr)[-400:])
    check("pip was never run", pip_calls(log) == [], str(pip_calls(log)))
    check("HEIC is never mentioned", "HEIC" not in r.stdout, r.stdout[-400:])


def t_launcher_finds_heic_in_subfolders():
    print("L3: HEIC only inside subfolders still triggers the install try")
    stub = make_stub_dir("stub_noplugin_fakepip", block_plugin=True, fake_pip=True)
    log = os.path.join(WORK, "pip_log_tree.txt")
    r = run_launcher(["make", os.path.join(HT, "phonetree")], "\n" * 7,
                     env=env_with(stub, log))
    check("one install attempt for a tree of HEIC subfolders",
          len(pip_calls(log)) == 1, str(pip_calls(log)))
    check("no traceback", "Traceback" not in r.stderr, r.stderr[-400:])


def t_launcher_counts_heic_as_pictures():
    print("L4: with HEIC readable, HEIC-only subfolders count as picture folders")
    stub = make_stub_dir("stub_fakepip_only", block_plugin=False, fake_pip=True)
    log = os.path.join(WORK, "pip_log_ready.txt")
    top = os.path.join(HT, "phonetree")
    outdir = top + " PDFs"
    shutil.rmtree(outdir, ignore_errors=True)
    # Nothing directly in phonetree, so plain Return means one PDF per folder.
    r = run_launcher(["make", top], "\n" * 7, env=env_with(stub, log))
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-500:])
    check("offers one PDF per folder", "one PDF for every folder" in r.stdout,
          r.stdout[-700:])
    check("each HEIC-only subfolder became a PDF",
          listing(outdir) == ["monday.pdf", "tuesday.pdf"], str(listing(outdir)))
    check("plugin already there -> pip was never run",
          pip_calls(log) == [], str(pip_calls(log)))


def main():
    if not (HAVE_PLUGIN or HAVE_SIPS):
        print("SKIPPED: can't create HEIC test pictures here - that needs the "
              "pillow-heif package\n(python -m pip install pillow-heif) or, on "
              "a Mac, the built-in `sips` tool.")
        shutil.rmtree(WORK, ignore_errors=True)
        sys.exit(0)
    print(f"HEIC test pictures written with: "
          f"{'pillow-heif' if HAVE_PLUGIN else 'macOS sips'}")
    setup()
    t_heic_pages_in_order()
    t_rotated_heic_is_upright()
    t_layout_modes_accept_heic()
    t_recursive_heic_only_folder()
    t_corrupt_heic_is_skipped()
    t_apple_tiled_heic()
    t_photo_heic_stays_sanely_sized()
    t_colour_profile_survives()
    t_engine_without_plugin()
    t_launcher_adds_support_on_demand()
    t_launcher_leaves_pip_alone_without_heic()
    t_launcher_finds_heic_in_subfolders()
    t_launcher_counts_heic_as_pictures()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    if FAIL:
        print(f"fixtures kept for inspection: {WORK}")
    else:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
