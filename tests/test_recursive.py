#!/usr/bin/env python3
"""Tests for generate_pdf.py: --recursive batch mode and junk-file handling.

Runs the engine as a CLI (the way the launcher does) against fixture trees
in a temporary folder and asserts on produced files, page counts, exit codes
and warning text. Nothing inside the repo is touched.

Run with any Python 3:  python3 tests/test_recursive.py
(If Pillow/pypdf aren't importable it re-runs itself with the project's own
.venv, so double-clicking a launcher once is enough to set up for testing.)
"""
import os
import shutil
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

VENVPY = sys.executable
WORK = tempfile.mkdtemp(prefix="pdfmaker-test-")
RT = os.path.join(WORK, "rt")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def make_png(path, color, size=(60, 80)):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path)


def pdf_pages(path):
    from pypdf import PdfReader
    return len(PdfReader(path).pages)


def run_engine(args):
    return subprocess.run([VENVPY, ENGINE] + args,
                          capture_output=True, text=True, timeout=300)


def listing(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else None


def setup():
    # tree: 2 direct images, alpha (3), alpha/nested (1), beta (1),
    #       empty folder, hidden folder, __MACOSX junk, a stray txt file.
    make_png(os.path.join(RT, "tree", "top_1.png"), "red")
    make_png(os.path.join(RT, "tree", "top_2.png"), "blue")
    for i, c in enumerate(("red", "green", "blue"), 1):
        make_png(os.path.join(RT, "tree", "alpha", f"a_{i}.png"), c)
    make_png(os.path.join(RT, "tree", "alpha", "nested", "n_1.png"), "white")
    make_png(os.path.join(RT, "tree", "beta", "b_1.png"), "black")
    os.makedirs(os.path.join(RT, "tree", "empty"))
    make_png(os.path.join(RT, "tree", ".hidden", "h_1.png"), "red")
    make_png(os.path.join(RT, "tree", "__MACOSX", "j_1.png"), "red")
    with open(os.path.join(RT, "tree", "notes.txt"), "w") as f:
        f.write("not a picture")
    # clash: two different subfolders both named "photos"
    make_png(os.path.join(RT, "clash", "photos", "p_1.png"), "red")
    make_png(os.path.join(RT, "clash", "2023", "photos", "q_1.png"), "blue")
    # badmix: one folder of only-corrupt files, one good folder
    bad = os.path.join(RT, "badmix", "broken", "fake_1.jpg")
    os.makedirs(os.path.dirname(bad))
    with open(bad, "wb") as f:
        f.write(b"this is not a jpeg at all")
    make_png(os.path.join(RT, "badmix", "good", "g_1.png"), "green")
    # allbad: every folder unreadable
    ab = os.path.join(RT, "allbad", "broken", "fake_1.jpg")
    os.makedirs(os.path.dirname(ab))
    with open(ab, "wb") as f:
        f.write(b"still not a jpeg")


def t_flat_regression():
    print("R0: non-recursive behaviour unchanged")
    out = os.path.join(RT, "alpha_only.pdf")
    r = run_engine(["--src", os.path.join(RT, "tree", "alpha"), "--out", out])
    check("plain run exits 0", r.returncode == 0, r.stderr[-300:])
    check("plain run: 3 pages, subfolder NOT included", pdf_pages(out) == 3)


def t_recursive_default_outdir():
    print("R1: --recursive makes one PDF per folder in '<src> PDFs'")
    outdir = os.path.join(RT, "tree PDFs")
    r = run_engine(["--recursive", "--src", os.path.join(RT, "tree")])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("default output folder created", os.path.isdir(outdir),
          str(listing(RT)))
    got = listing(outdir)
    check("one PDF per folder, named after it",
          got == ["alpha.pdf", "beta.pdf", "nested.pdf", "tree.pdf"], str(got))
    if got == ["alpha.pdf", "beta.pdf", "nested.pdf", "tree.pdf"]:
        check("tree.pdf has the 2 direct pictures only",
              pdf_pages(os.path.join(outdir, "tree.pdf")) == 2)
        check("alpha.pdf has 3 pages (nested excluded)",
              pdf_pages(os.path.join(outdir, "alpha.pdf")) == 3)
        check("nested.pdf has 1 page",
              pdf_pages(os.path.join(outdir, "nested.pdf")) == 1)
        check("beta.pdf has 1 page",
              pdf_pages(os.path.join(outdir, "beta.pdf")) == 1)
    check("mentions how many folders it found",
          "folders" in r.stdout.lower(), r.stdout[:300])
    # Re-run: the output dir sits next to (not inside) the tree, so a second
    # pass must find the same 4 folders, not PDFs of its own output.
    r2 = run_engine(["--recursive", "--src", os.path.join(RT, "tree")])
    check("re-run is stable (output not re-scanned)",
          r2.returncode == 0 and listing(outdir)
          == ["alpha.pdf", "beta.pdf", "nested.pdf", "tree.pdf"])


def t_recursive_custom_outdir():
    print("R2: --recursive honours --out as the output folder")
    outdir = os.path.join(RT, "custom_out")
    r = run_engine(["--recursive", "--src", os.path.join(RT, "tree"),
                    "--out", outdir])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check("PDFs land in the given folder",
          listing(outdir) == ["alpha.pdf", "beta.pdf", "nested.pdf", "tree.pdf"],
          str(listing(outdir)))


def t_name_clash():
    print("R3: same-named folders get tell-apart names")
    outdir = os.path.join(RT, "clash PDFs")
    r = run_engine(["--recursive", "--src", os.path.join(RT, "clash")])
    got = listing(outdir)
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check("clashing 'photos' folders disambiguated by their path",
          got is not None and len(got) == 2 and len(set(got)) == 2
          and any("2023" in g for g in got), str(got))


def t_options_thread_through():
    print("R4: normal options apply to every folder's PDF")
    outdir = os.path.join(RT, "opts_out")
    r = run_engine(["--recursive", "--src", os.path.join(RT, "tree"),
                    "--out", outdir, "--number-pages", "--parts", "2"])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    got = listing(outdir)
    # alpha (3 imgs) and tree (2 imgs) can split in two; beta and nested
    # have a single image, so their "split" collapses to one whole PDF.
    expect = ["alpha_part1_of_2.pdf", "alpha_part2_of_2.pdf", "beta.pdf",
              "nested.pdf", "tree_part1_of_2.pdf", "tree_part2_of_2.pdf"]
    check("--parts applies per folder, clamped to the picture count",
          got == expect, str(got))
    if got == expect:
        from pypdf import PdfReader
        # --number-pages restarts at 0001 in each folder: compare the first
        # page of beta.pdf against a freshly stamped reference of the same
        # source picture.
        sys.path.insert(0, REPO)
        from PIL import Image
        import generate_pdf as g
        ref = Image.new("RGB", (60, 80), "black")
        g.stamp_page_number(ref, 1, "bottom-right")
        page = PdfReader(os.path.join(outdir, "beta.pdf")).pages[0]
        imgs = page.images
        same = False
        if imgs:
            got_im = imgs[0].image.convert("RGB")
            same = got_im.size == ref.size and got_im.tobytes() == ref.tobytes()
        check("each folder's numbering restarts at 0001", same)


def t_bad_folder_resilience():
    print("R5: one unreadable folder never sinks the batch")
    outdir = os.path.join(RT, "badmix PDFs")
    r = run_engine(["--recursive", "--src", os.path.join(RT, "badmix")])
    check("exits 0 despite a hopeless folder", r.returncode == 0,
          (r.stdout + r.stderr)[-400:])
    check("good folder still produced its PDF",
          listing(outdir) == ["good.pdf"], str(listing(outdir)))
    check("warning names the unreadable file", "fake_1.jpg" in r.stderr,
          r.stderr[-400:])

    r = run_engine(["--recursive", "--src", os.path.join(RT, "allbad")])
    check("all folders unreadable -> error exit", r.returncode != 0)

    r = run_engine(["--recursive", "--src", os.path.join(RT, "tree", "empty")])
    check("no folders with pictures -> clear error", r.returncode != 0
          and "no folders" in (r.stdout + r.stderr).lower(),
          (r.stdout + r.stderr)[-300:])


def t_junk_files_ignored():
    print("J1: non-picture junk in a folder is ignored without drama")
    d = os.path.join(RT, "messy")
    make_png(os.path.join(d, "photo_1.png"), "red")
    make_png(os.path.join(d, "photo_2.png"), "blue")
    # The junk an unorganized folder actually accumulates:
    for name, data in (
        (".DS_Store", b"\x00\x00\x00\x01Bud1"),        # Finder metadata
        ("Thumbs.db", b"\xd0\xcf\x11\xe0junk"),        # Windows thumbnails
        ("desktop.ini", b"[.ShellClassInfo]"),          # Windows folder config
        ("._photo_1.jpg", b"\x00\x05\x16\x07junk"),    # AppleDouble fork: fake .jpg!
        (".hidden_pic.png", b"\x89PNGnot really"),      # hidden dotfile w/ image ext
        ("holiday_video.mp4", b"\x00\x00\x00 ftypmp4"),  # phone video
        ("notes.docx", b"PK\x03\x04word"),              # office doc
        ("list.txt", b"buy milk"),
    ):
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    os.makedirs(os.path.join(d, "album.jpg"))           # a FOLDER named like a pic
    out = os.path.join(RT, "messy.pdf")
    r = run_engine(["--src", d, "--out", out])
    check("messy folder exits 0", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check("only the 2 real pictures made it in", pdf_pages(out) == 2)
    check("no WARNING noise for junk files", "WARNING" not in r.stderr,
          r.stderr[-400:])
    check("junk is not even counted",
          "from 2 images" in r.stdout, r.stdout[:300])


def t_junk_only_folder_recursive():
    print("J2: a folder holding only junk 'pictures' is not a picture folder")
    make_png(os.path.join(RT, "junktree", "real", "r_1.png"), "green")
    jd = os.path.join(RT, "junktree", "forks")
    os.makedirs(jd)
    with open(os.path.join(jd, "._IMG_0001.jpg"), "wb") as f:
        f.write(b"\x00\x05\x16\x07resource fork")
    outdir = os.path.join(RT, "junktree PDFs")
    r = run_engine(["--recursive", "--src", os.path.join(RT, "junktree")])
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check("only the real folder becomes a PDF",
          listing(outdir) == ["real.pdf"], str(listing(outdir)))
    check("junk-only folder not counted as found",
          "found 1 folder" in r.stdout, r.stdout[:300])


def main():
    setup()
    t_flat_regression()
    t_recursive_default_outdir()
    t_recursive_custom_outdir()
    t_name_clash()
    t_options_thread_through()
    t_bad_folder_resilience()
    t_junk_files_ignored()
    t_junk_only_folder_recursive()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    if FAIL:
        print(f"fixtures kept for inspection: {WORK}")
    else:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
