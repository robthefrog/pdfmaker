#!/usr/bin/env python3
"""Interactive launcher shared by the macOS and Windows double-click wrappers.

The .command (macOS) and .bat (Windows) files are thin shims: they check that
Python 3 exists and then hand over to this script, which does everything else —
creates the private .venv on first run (installing img2pdf, Pillow and pypdf),
re-runs itself inside it, asks the plain-English questions, runs the right
engine (generate_pdf.py or combine_pdfs.py), and reveals the finished PDF in
Finder / File Explorer.

Usage:
    python launcher.py make [folder]       # pictures -> PDF
    python launcher.py combine [folder]    # merge a folder of PDFs

A folder given on the command line (e.g. dragged onto the .bat icon) skips the
folder question. All output is plain ASCII so it renders in any console.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORT_CHECK = "import img2pdf, PIL, pypdf"
PIP_PACKAGES = ("img2pdf", "Pillow", "pypdf")
# Newer img2pdf releases depend on pikepdf, a compiled component whose
# prebuilt wheels don't cover every machine (e.g. Intel Macs on macOS
# older than 15). Compiling it needs the qpdf C++ library, which normal
# users won't have, so the install must never attempt that. img2pdf 0.3.6
# is the newest release with no pikepdf dependency: pure Python, installs
# on any platform, and supports everything generate_pdf.py uses.
PIP_NO_COMPILE = ("--only-binary", "pikepdf")
PIP_PACKAGES_FALLBACK = ("img2pdf==0.3.6", "Pillow", "pypdf")
INTERACTIVE = sys.stdin.isatty()


# ---------------------------------------------------------------------------
# First-run setup: a private, self-contained environment
# ---------------------------------------------------------------------------
def venv_python() -> str:
    if os.name == "nt":
        return os.path.join(HERE, ".venv", "Scripts", "python.exe")
    return os.path.join(HERE, ".venv", "bin", "python")


def running_in_project_venv() -> bool:
    # Compare sys.prefix, not executables: .venv/bin/python is a symlink back
    # to the base interpreter on macOS, so samefile() would match wrongly.
    venv_dir = os.path.join(HERE, ".venv")
    return os.path.realpath(sys.prefix) == os.path.realpath(venv_dir)


def deps_ok(python_exe: str) -> bool:
    r = subprocess.run([python_exe, "-c", IMPORT_CHECK],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0


def fail(message: str) -> None:
    print()
    print(message)
    pause()
    sys.exit(1)


def ensure_environment() -> None:
    """Create/repair the .venv if needed, then re-run this script inside it."""
    if running_in_project_venv():
        return
    vp = venv_python()
    if not (os.path.exists(vp) and deps_ok(vp)):
        # The "setup v2" tag identifies this launcher version in screenshots
        # of failed first runs, where nothing else distinguishes releases.
        print("Setting things up for the first time (about a minute)... [setup v2]")
        r = subprocess.run([sys.executable, "-m", "venv",
                            os.path.join(HERE, ".venv")])
        if r.returncode != 0 or not os.path.exists(vp):
            fail("Setup failed creating the environment.")
        subprocess.run([vp, "-m", "pip", "install", "--quiet",
                        "--upgrade", "pip"])
        # With pikepdf restricted to prebuilt wheels, pip picks the newest
        # img2pdf that works on this machine (falling back to 0.3.6 where no
        # pikepdf wheel fits) instead of failing on a doomed compile.
        r = subprocess.run([vp, "-m", "pip", "install", "--quiet",
                            *PIP_NO_COMPILE, *PIP_PACKAGES])
        if r.returncode != 0:
            r = subprocess.run([vp, "-m", "pip", "install", "--quiet",
                                *PIP_PACKAGES_FALLBACK])
        if r.returncode != 0:
            fail("Couldn't download the needed components. Please check your\n"
                 "internet connection and try again.")
        print("All set!")
        print()
    raise SystemExit(
        subprocess.run([vp, os.path.abspath(__file__)] + sys.argv[1:]).returncode)


# ---------------------------------------------------------------------------
# Small console helpers
# ---------------------------------------------------------------------------
def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""


def pause() -> None:
    if not INTERACTIVE:
        return
    try:
        input("Press Return to close this window.")
    except (EOFError, KeyboardInterrupt):
        pass


# Plain ASCII so it renders in any console (old Windows code pages included).
FROG = r"""
  @..@
 (----)      Ribbit! Welcome to PDF Maker.
( >__< )
^^ ~~ ^^
"""


def greet() -> None:
    print(FROG)


def banner(title: str) -> None:
    print("============================================")
    print("   " + title)
    print("============================================")
    print()


# ---------------------------------------------------------------------------
# Folder handling (dragged-in paths, defaults, trailing-space recovery)
# ---------------------------------------------------------------------------
def clean_dropped_path(raw: str) -> str:
    """Tidy a dragged-in or pasted path into a plain filesystem path."""
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]  # surrounding quotes (Windows drag-and-drop adds these)
    if os.name != "nt":
        # macOS Terminal escapes spaces and specials when you drag a folder in.
        s = re.sub(r"\\(.)", r"\1", s)
    while len(s) > 1 and s[-1] in "/\\" and not s.endswith(":\\"):
        s = s[:-1]
    return s


def recover_trailing_space(folder: str) -> str:
    """Recover a folder whose name ends in whitespace that input() trimmed off.

    If the path as given isn't a real folder, look in its parent for a folder
    whose name matches once trailing whitespace is ignored, and use that.
    """
    if not folder or os.path.isdir(folder):
        return folder
    parent = os.path.dirname(folder) or "."
    base = os.path.basename(folder).rstrip()
    if os.path.isdir(parent):
        for entry in sorted(os.listdir(parent)):
            full = os.path.join(parent, entry)
            if os.path.isdir(full) and entry.rstrip() == base:
                return full
    return folder


def choose_folder(argv_folder: str | None, what: str) -> str:
    if argv_folder:
        # A path dragged onto the .command/.bat icon can arrive quoted, escaped,
        # or with a trailing separator — clean it the same way typed input is, so
        # `folder + ".pdf"` can't turn into a stray ".pdf" inside the folder.
        argv_folder = recover_trailing_space(clean_dropped_path(argv_folder))
        if os.path.isdir(argv_folder):
            return argv_folder
    print("Which folder of %s?" % what)
    print("   - DRAG the folder into this window and press Return, or")
    print("   - just press Return to use the 'pictures' folder next to this launcher.")
    print()
    while True:
        folder = clean_dropped_path(ask("Folder: "))
        folder = recover_trailing_space(folder)
        if not folder:
            # Empty also covers EOF (closed stdin), so this loop always ends.
            folder = os.path.join(HERE, "pictures")
            os.makedirs(folder, exist_ok=True)
        if os.path.isdir(folder):
            return folder
        print()
        print("I couldn't find that folder:")
        print("   " + folder)
        print("Please drag the folder in and press Return, or press Return alone for 'pictures'.")


# ---------------------------------------------------------------------------
# Spotting a "folder of folders" (for the one-PDF-per-folder offer)
# ---------------------------------------------------------------------------
# Mirrors generate_pdf.py: same extensions (HEIC needs a plugin, so it doesn't
# count), same skip rules for hidden files/folders and zip artefacts.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
SKIP_DIR_NAMES = {"__MACOSX", "__pycache__"}


def folder_holds_pictures(folder: str) -> bool:
    try:
        entries = os.listdir(folder)
    except OSError:
        return False
    return any(not e.startswith(".") and e.lower().endswith(IMAGE_EXTS)
               and os.path.isfile(os.path.join(folder, e)) for e in entries)


def subfolders_hold_pictures(folder: str) -> bool:
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in SKIP_DIR_NAMES]
        if dirpath != folder and any(
                not f.startswith(".") and f.lower().endswith(IMAGE_EXTS)
                for f in filenames):
            return True
    return False


def ask_per_folder(folder: str) -> bool:
    """Offer one-PDF-per-folder when the chosen folder is a folder of folders.

    Silent (False) when there are no picture subfolders. The default answer
    follows the pictures: folders that also hold their own pictures default
    to the classic single PDF; folders that are ONLY organisers default to
    one PDF per folder, because a single PDF would come out empty.
    """
    if not subfolders_hold_pictures(folder):
        return False
    print("This folder has more folders inside it that contain pictures.")
    print("Do you want one PDF for every folder, each named after its folder?")
    if folder_holds_pictures(folder):
        print("   1) No  - one PDF, just from the pictures directly in this folder   (default)")
        print("   2) Yes - one PDF per folder, saved together in one new folder")
        answer = ask("Choose 1 or 2 [1]: ").strip()
        print()
        return answer == "2"
    print("(There are no pictures directly inside it - only in the folders within.)")
    print("   1) Yes - one PDF per folder, saved together in one new folder   (default)")
    print("   2) No  - just this folder's own pictures (it has none, so this stops)")
    answer = ask("Choose 1 or 2 [1]: ").strip()
    print()
    return answer != "2"


# ---------------------------------------------------------------------------
# Revealing the result
# ---------------------------------------------------------------------------
def reveal_file(path: str) -> None:
    if not INTERACTIVE:
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            subprocess.run(["explorer", "/select," + os.path.normpath(path)])
    except Exception:
        pass


def open_folder(path: str) -> None:
    if not INTERACTIVE:
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        pass


def run_engine(script: str, engine_args: list[str]) -> bool:
    sys.stdout.flush()  # keep our prints ahead of the engine's when piped
    cmd = [sys.executable, os.path.join(HERE, script)] + engine_args
    return subprocess.run(cmd).returncode == 0


# ---------------------------------------------------------------------------
# The two flows
# ---------------------------------------------------------------------------
def make_flow(argv_folder: str | None) -> None:
    banner("PDF Maker")
    folder = choose_folder(argv_folder, "pictures should I turn into a PDF")
    per_folder = ask_per_folder(folder)

    opts: list[str] = []
    if per_folder:
        opts += ["--recursive"]
    print("How many pictures per page?")
    print("   1) One   - one picture per page, filling it        (default)")
    print("   3) Three - three side-by-side on a landscape page  (great for phone screenshots)")
    per_page = ask("Choose 1 or 3 [1]: ").strip()
    print()

    if per_page == "3":
        opts += ["--per-page", "3"]
        print("How much space around and between the three pictures?")
        print("   1) Half a centimetre   (default)")
        print("   2) One centimetre      - a bit more breathing room")
        print("   3) None                - the pictures sit edge to edge")
        gap = ask("Choose 1, 2 or 3 [1]: ").strip()
        if gap == "2":
            opts += ["--gap", "1.0"]
        elif gap == "3":
            opts += ["--gap", "0"]
        print()
    else:
        print("How much blank margin do you want for handwriting notes?")
        print("   1) None  - the picture fills the whole page   (default)")
        print("   2) Some  - a half-inch border on Letter paper")
        print("   3) Lots  - a one-inch border on Letter paper")
        notes = ask("Choose 1, 2 or 3 [1]: ").strip()
        if notes == "2":
            opts += ["--page", "letter", "--margin", "0.5"]
        elif notes == "3":
            opts += ["--page", "letter", "--margin", "1.0"]
        print()

    print("Do you want a smaller PDF file (easier to email or upload)?")
    print("   1) No       - best quality, largest file   (default)")
    print("   2) Smaller  - good quality, much smaller file")
    print("   3) Smallest - still readable, tiny file")
    size = ask("Choose 1, 2 or 3 [1]: ").strip()
    if size == "2":
        opts += ["--max-height", "1400", "--quality", "70"]
    elif size == "3":
        opts += ["--max-height", "1000", "--quality", "55"]
    print()

    print("Do you want a page number stamped on every page (0001, 0002, ...)?")
    print("It is printed in a corner, on top of the picture, in a soft grey.")
    print("   1) No                 (default)")
    print("   2) Yes - bottom right")
    print("   3) Yes - bottom left")
    print("   4) Yes - top right")
    print("   5) Yes - top left")
    numbers = ask("Choose 1-5 [1]: ").strip()
    if numbers == "2":
        opts += ["--number-pages"]
    elif numbers == "3":
        opts += ["--number-corner", "bottom-left"]
    elif numbers == "4":
        opts += ["--number-corner", "top-right"]
    elif numbers == "5":
        opts += ["--number-corner", "top-left"]
    if numbers in ("2", "3", "4", "5"):
        print()
        print("Put the folder's name in front of each number (like 'beach 0042')?")
        print("Handy when every folder gets its own PDF.")
        named = ask("y or n [n]: ").strip().lower()
        if named in ("y", "yes"):
            opts += ["--number-folder"]
    print()

    print("How many PDF files do you want? Splitting divides the pictures evenly")
    print("(keeping their order) - handy when one file is too big to email or print.")
    print("   1 = one PDF    (default)")
    print("   2 = two PDFs")
    print("   4 = four PDFs")
    split = ask("Type 1, 2 or 4 [1]: ").strip()
    parts = 1
    if split == "2":
        opts += ["--parts", "2"]
        parts = 2
    elif split == "4":
        opts += ["--parts", "4"]
        parts = 4
    print()

    out = folder + (" PDFs" if per_folder else ".pdf")
    if per_folder:
        print("Making one PDF for every folder of pictures inside:")
    else:
        print("Making your PDF from the pictures in:")
    print("   " + folder)
    print()
    if run_engine("generate_pdf.py", ["--src", folder, "--out", out] + opts):
        print()
        if per_folder:
            print("Done!  Your PDFs are saved together here:")
            print("   " + out)
            open_folder(out)
        elif parts > 1:
            print("Done!  Your %d PDF files are saved next to the pictures folder" % parts)
            print("(their names end in _partX_of_%d.pdf - see the list just above)." % parts)
            open_folder(os.path.dirname(out) or ".")
        else:
            print("Done!  Your PDF is here:")
            print("   " + out)
            reveal_file(out)
    else:
        print()
        print("Something went wrong - please read the message just above for the reason.")
        print("(A common cause is a folder with no .jpg/.png pictures in it.)")


def combine_flow(argv_folder: str | None) -> None:
    banner("Combine PDFs")
    folder = choose_folder(argv_folder, "PDFs should I combine into one")

    opts: list[str] = []
    print("In what order should I combine the PDFs?")
    print("   1) By name  - by the number in each filename (part1, part2, ...)  (default)")
    print("   2) By date  - oldest file first (handy when names have no order)")
    order = ask("Choose 1 or 2 [1]: ").strip()
    print()
    if order == "2":
        opts += ["--order", "date"]

    out = folder + "-combined.pdf"
    print("Combining the PDFs in:")
    print("   " + folder)
    print()
    if run_engine("combine_pdfs.py", ["--src", folder, "--out", out] + opts):
        print()
        print("Done!  Your combined PDF is here:")
        print("   " + out)
        reveal_file(out)
    else:
        print()
        print("Something went wrong - please read the message just above for the reason.")
        print("(A common cause is a folder with no .pdf files in it.)")


def another_round() -> bool:
    """Offer to run again so several folders don't need several launches."""
    print()
    answer = ask("Do another folder? (y/n) [n]: ").strip().lower()
    return answer in ("y", "yes")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "make"
    if mode not in ("make", "combine"):
        sys.exit("usage: python launcher.py [make|combine] [folder]")
    ensure_environment()
    greet()
    argv_folder = sys.argv[2] if len(sys.argv) > 2 else None
    flow = combine_flow if mode == "combine" else make_flow
    while True:
        flow(argv_folder)
        argv_folder = None  # every further round asks for (or takes a drag of) a folder
        if not another_round():
            break
    print()
    pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
