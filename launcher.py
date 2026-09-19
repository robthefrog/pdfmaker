#!/usr/bin/env python3
"""Interactive launcher shared by the macOS and Windows double-click wrappers.

The .command (macOS) and .bat (Windows) files are thin shims: they check that
Python 3 exists and then hand over to this script, which does everything else —
creates the private .venv on first run (installing img2pdf, Pillow and pypdf,
plus pillow-heif for iPhone HEIC photos wherever a prebuilt wheel exists),
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
# Optional extra: pillow-heif teaches Pillow to read iPhone HEIC/HEIF photos.
# It is a compiled component as well, so the same rule applies - prebuilt
# wheels only (they exist for Windows x64/ARM and for Intel and Apple-silicon
# Macs) - and it must never be able to fail the setup: without it HEIC
# pictures are simply reported and left out, exactly as before it existed.
HEIC_PACKAGE = "pillow-heif"
HEIC_IMPORT_CHECK = "import pillow_heif"
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


def heic_ready(python_exe: str) -> bool:
    """True when the HEIC plugin really imports (a wheel that installed but
    can't load on this machine counts as missing)."""
    r = subprocess.run([python_exe, "-c", HEIC_IMPORT_CHECK],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0


def install_heic_plugin(python_exe: str, silent: bool = False) -> bool:
    """One wheels-only try at installing the HEIC plugin.

    Short network limits keep an offline machine from hanging here. The
    answer comes from importing the plugin afterwards, not from pip's exit
    code, so the caller can tell the user the plain truth either way.
    silent hides pip's own error text, for when a failure doesn't matter yet.
    """
    hush = subprocess.DEVNULL if silent else None
    subprocess.run([python_exe, "-m", "pip", "install", "--quiet",
                    "--disable-pip-version-check", "--retries", "1",
                    "--timeout", "15", "--only-binary", ":all:", HEIC_PACKAGE],
                   stdout=hush, stderr=hush)
    return heic_ready(python_exe)


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
        # The "setup v3" tag identifies this launcher version in screenshots
        # of failed first runs, where nothing else distinguishes releases.
        print("Setting things up for the first time (about a minute)... [setup v3]")
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
        # A bonus, never a requirement: if this fails, setup still succeeds
        # (silently - a pip error right before "All set!" would only alarm)
        # and it is tried again, out loud, when a folder really has HEICs.
        install_heic_plugin(vp, silent=True)
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
# Mirrors generate_pdf.py: same extensions, same skip rules for hidden
# files/folders and zip artefacts. HEIC/HEIF only count as pictures once the
# plugin that reads them is in place - see picture_exts_for().
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
HEIC_EXTS = (".heic", ".heif")
SKIP_DIR_NAMES = {"__MACOSX", "__pycache__"}


def tree_has_heic(folder: str) -> bool:
    """True if the folder, or any folder inside it, holds a HEIC/HEIF file."""
    for _, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in SKIP_DIR_NAMES]
        if any(not f.startswith(".") and f.lower().endswith(HEIC_EXTS)
               for f in filenames):
            return True
    return False


def picture_exts_for(folder: str) -> tuple:
    """The picture types this run can use - HEIC included when it's readable.

    Costs nothing unless the folder really holds HEIC files. Then, if the
    plugin is missing (an environment made before HEIC support existed, or
    whose first-run download of it failed), it is fetched on the spot - so
    nobody has to reinstall anything, and a failure while offline simply
    gets another chance the next time HEIC pictures turn up.
    """
    if not tree_has_heic(folder):
        return IMAGE_EXTS
    if heic_ready(sys.executable):
        return IMAGE_EXTS + HEIC_EXTS
    print("This folder has iPhone photos in it (HEIC files). Adding support for")
    print("them - a small one-time download, just a moment...")
    sys.stdout.flush()  # keep this ahead of anything pip prints when piped
    if install_heic_plugin(sys.executable):
        print("Done - your HEIC photos will be included.")
        print()
        return IMAGE_EXTS + HEIC_EXTS
    print()
    print("I couldn't add HEIC support on this computer, so those photos will be")
    print("left out of the PDF. Check your internet connection and try again, or")
    print("turn them into JPG pictures first (see 'READ ME FIRST', section 6).")
    print()
    return IMAGE_EXTS


def folder_holds_pictures(folder: str, exts: tuple = IMAGE_EXTS) -> bool:
    try:
        entries = os.listdir(folder)
    except OSError:
        return False
    return any(not e.startswith(".") and e.lower().endswith(exts)
               and os.path.isfile(os.path.join(folder, e)) for e in entries)


def subfolders_hold_pictures(folder: str, exts: tuple = IMAGE_EXTS) -> bool:
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in SKIP_DIR_NAMES]
        if dirpath != folder and any(
                not f.startswith(".") and f.lower().endswith(exts)
                for f in filenames):
            return True
    return False


def ask_per_folder(folder: str, exts: tuple = IMAGE_EXTS) -> bool:
    """Offer one-PDF-per-folder when the chosen folder is a folder of folders.

    Silent (False) when there are no picture subfolders. The default answer
    follows the pictures: folders that also hold their own pictures default
    to the classic single PDF; folders that are ONLY organisers default to
    one PDF per folder, because a single PDF would come out empty.
    `exts` is what counts as a picture for this run (see picture_exts_for).
    """
    if not subfolders_hold_pictures(folder, exts):
        return False
    print("This folder has more folders inside it that contain pictures.")
    print("Do you want one PDF for every folder, each named after its folder?")
    if folder_holds_pictures(folder, exts):
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
# The file-name menu (only reached after a "Yes" to the gating question)
# ---------------------------------------------------------------------------
def ask_file_names() -> list[str]:
    """The nested choices for file-name labels, as generate_pdf.py options.

    Style first, then where it goes, then whether the file ending shows.
    There is deliberately no choice that prints over a picture: when a layout
    has no blank room, the engine makes room instead.
    """
    opts: list[str] = []
    print("How should the file names be shown?")
    print("   1) Caption - each name right next to its own picture   (default)")
    print("   2) Summary - one line per page, listing the file name(s) on that page")
    print("   3) Summary with page identifier - the same line, starting with the")
    print("      folder name and page number, like:  beach - 0042 | IMG_1234.HEIC")
    style = ask("Choose 1, 2 or 3 [1]: ").strip()
    if style == "2":
        opts += ["--names", "summary"]
    elif style == "3":
        opts += ["--names", "summary", "--names-id"]
    else:
        opts += ["--names", "caption"]
    print()

    print("Where should they go?")
    print("   1) Below - under each picture; a summary goes at the foot of the page   (default)")
    print("   2) Above - just above each picture; a summary goes at the head of the page")
    if ask("Choose 1 or 2 [1]: ").strip() == "2":
        opts += ["--names-position", "above"]
    print()

    print("Show the file ending too (like .jpg or .HEIC)?")
    print("   1) Yes - IMG_1234.HEIC   (default)")
    print("   2) No  - IMG_1234")
    if ask("Choose 1 or 2 [1]: ").strip() == "2":
        opts += ["--names-hide-ext"]
    return opts


# ---------------------------------------------------------------------------
# The two flows
# ---------------------------------------------------------------------------
def make_flow(argv_folder: str | None) -> None:
    banner("PDF Maker")
    folder = choose_folder(argv_folder, "pictures should I turn into a PDF")
    per_folder = ask_per_folder(folder, picture_exts_for(folder))

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
        print("Put the folder's name in front of each number (like 'beach - 0042')?")
        print("Handy when every folder gets its own PDF.")
        named = ask("y or n [n]: ").strip().lower()
        if named in ("y", "yes"):
            opts += ["--number-folder"]
    print()

    print("Do you want file names shown on the pages, so you can tell which file")
    print("each picture came from? They are printed in the blank paper beside the")
    print("pictures - never on top of a picture.")
    print("   1) No    (default)")
    print("   2) Yes")
    if ask("Choose 1 or 2 [1]: ").strip() == "2":
        print()
        opts += ask_file_names()
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
