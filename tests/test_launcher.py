#!/usr/bin/env python3
"""End-to-end tests for launcher.py driven through scripted stdin.

Runs the repo's launcher.py with the project .venv's Python (so its
first-run setup is a no-op), feeding answers on stdin exactly as a user
would type them, and asserts on output text and produced PDFs. All
fixtures live in a temporary folder; nothing inside the repo is touched.

Run with any Python 3:  python3 tests/test_launcher.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
# the project .venv - so the tests must drive it with that interpreter.
VENVPY = venv_python() if os.path.exists(venv_python()) else sys.executable
WORK = tempfile.mkdtemp(prefix="pdfmaker-test-")
LT = os.path.join(WORK, "lt")

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


def setup():
    # flatA / flatB: plain folders of pictures (no subfolders)
    for name, colors in (("flatA", ("red", "green")), ("flatB", ("blue", "black"))):
        for i, c in enumerate(colors, 1):
            make_png(os.path.join(LT, name, f"pic_{i}.png"), c)
    # tree: a picture directly inside AND in nested subfolders
    make_png(os.path.join(LT, "tree", "top_1.png"), "red")
    make_png(os.path.join(LT, "tree", "alpha", "a_1.png"), "green")
    make_png(os.path.join(LT, "tree", "alpha", "a_2.png"), "blue")
    make_png(os.path.join(LT, "tree", "beta", "b_1.png"), "white")
    # onlysubs: no pictures at the top, only inside subfolders
    make_png(os.path.join(LT, "onlysubs", "one", "x_1.png"), "red")
    make_png(os.path.join(LT, "onlysubs", "two", "y_1.png"), "blue")


def run_launcher(argv, answers, timeout=180):
    return subprocess.run([VENVPY, LAUNCHER] + argv,
                          input=answers, text=True, capture_output=True,
                          timeout=timeout)


# ---------------------------------------------------------------------------
# T1 - an ASCII frog greets the user at startup (make and combine alike)
# ---------------------------------------------------------------------------
def t1_frog():
    print("T1: frog greeting")
    r = run_launcher(["make", os.path.join(LT, "flatA")], "\n\n\n\n\n")
    out = r.stdout + r.stderr
    check("launcher exits 0", r.returncode == 0, out[-400:])
    check("PDF was made", os.path.isfile(os.path.join(LT, "flatA.pdf")))
    check("frog art shown", "@..@" in r.stdout, r.stdout[:400])
    check("frog says ribbit", "ribbit" in r.stdout.lower())
    check("art is pure ASCII", all(ord(ch) < 128 for ch in r.stdout))
    check("no recursion question for a flat folder",
          "one PDF for every folder" not in r.stdout)


# ---------------------------------------------------------------------------
# T2 - after finishing, the launcher offers to do another folder (y/n)
# ---------------------------------------------------------------------------
def t2_do_another():
    print("T2: do-another loop")
    for p in ("flatA.pdf", "flatB.pdf"):
        try:
            os.remove(os.path.join(LT, p))
        except FileNotFoundError:
            pass
    # Round 1: flatA + default answers; say YES; round 2: flatB; say NO.
    answers = (os.path.join(LT, "flatA") + "\n" + "\n" * 5 + "y\n"
               + os.path.join(LT, "flatB") + "\n" + "\n" * 5 + "n\n")
    r = run_launcher(["make"], answers)
    check("launcher exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("asks to do another folder", "another folder" in r.stdout.lower(),
          r.stdout[-400:])
    check("round 1 PDF made", os.path.isfile(os.path.join(LT, "flatA.pdf")))
    check("round 2 PDF made after 'y'",
          os.path.isfile(os.path.join(LT, "flatB.pdf")))
    check("frog greets only once", r.stdout.count("@..@") == 1)

    # Saying nothing (EOF / plain Return) means no second round.
    for p in ("flatA.pdf", "flatB.pdf"):
        try:
            os.remove(os.path.join(LT, p))
        except FileNotFoundError:
            pass
    r = run_launcher(["make", os.path.join(LT, "flatA")], "\n" * 6)
    check("default answer stops the loop", r.returncode == 0
          and os.path.isfile(os.path.join(LT, "flatA.pdf"))
          and not os.path.isfile(os.path.join(LT, "flatB.pdf")))

    # A mistyped folder re-prompts instead of quitting the whole app.
    answers = ("/nowhere/definitely-missing\n" + os.path.join(LT, "flatB")
               + "\n" + "\n" * 5 + "n\n")
    r = run_launcher(["make"], answers)
    check("bad folder gets a second chance", r.returncode == 0
          and os.path.isfile(os.path.join(LT, "flatB.pdf")),
          (r.stdout + r.stderr)[-400:])


# ---------------------------------------------------------------------------
# T3 - a folder with picture subfolders triggers the one-PDF-per-folder offer
# ---------------------------------------------------------------------------
def t3_recursion_question():
    print("T3: recursion question for a folder of folders")
    tree = os.path.join(LT, "tree")
    outdir = tree + " PDFs"
    # tree has pictures at the top AND in subfolders -> ask, default single.
    # Answer 2 (per folder), then the usual 5 defaults.
    r = run_launcher(["make", tree], "2\n" + "\n" * 5)
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("question offered", "one PDF for every folder" in r.stdout,
          r.stdout[-600:])
    got = sorted(os.listdir(outdir)) if os.path.isdir(outdir) else None
    check("one PDF per folder produced",
          got == ["alpha.pdf", "beta.pdf", "tree.pdf"], str(got))
    check("done message points at the folder", "PDFs" in r.stdout)

    # Same tree, pressing Return: default is the old single-PDF behaviour.
    shutil.rmtree(outdir, ignore_errors=True)
    r = run_launcher(["make", tree], "\n" * 6)
    check("default keeps one PDF (pictures at top level)",
          r.returncode == 0 and os.path.isfile(tree + ".pdf")
          and not os.path.isdir(outdir), (r.stdout + r.stderr)[-300:])


# ---------------------------------------------------------------------------
# T4 - no pictures at the top, subfolders full of them: default flips to yes
# ---------------------------------------------------------------------------
def t4_adaptive_default():
    print("T4: default is per-folder when the top folder itself has no pictures")
    top = os.path.join(LT, "onlysubs")
    outdir = top + " PDFs"
    r = run_launcher(["make", top], "\n" * 6)
    check("exits 0", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    got = sorted(os.listdir(outdir)) if os.path.isdir(outdir) else None
    check("plain Return makes one PDF per subfolder",
          got == ["one.pdf", "two.pdf"], str(got))
    check("explains why (no pictures at the top)",
          "no pictures directly" in r.stdout.lower(), r.stdout[-600:])


def main():
    setup()
    t1_frog()
    t2_do_another()
    t3_recursion_question()
    t4_adaptive_default()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    if FAIL:
        print(f"fixtures kept for inspection: {WORK}")
    else:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
