# 📄 PDF Maker

Turn a folder of pictures into one PDF — one picture per page, or three
side-by-side on a landscape page, in order. Mostly you just double-click a file.
Works on **Mac** and **Windows**.

> 📦 If you received this as a **.zip**, double-click it first so it becomes a
> **PDF Maker** folder, then open that folder. Don't run it from inside the zip.

## What's in this folder

| Item | What it is |
| --- | --- |
| **Make PDF** | The thing you double-click. On a Mac use **Make PDF.command**; on Windows use **Make PDF.bat** (you can also drag a folder onto its icon). |
| **Combine PDFs** | Double-click to merge every PDF in a folder into one. Same idea: **.command** on a Mac, **.bat** on Windows. |
| `pictures` | A folder with 3 sample pictures so you can try it right away. |
| `launcher.py`, `generate_pdf.py`, `combine_pdfs.py` | The engine. You don't open these. |
| **READ ME FIRST.md** | This guide. |

## 1 · One-time setup (about 2 minutes)

PDF Maker needs **Python**, a free program. Install it once:

### On a Mac

1. Go to **https://www.python.org/downloads/macos/**
2. Download the **"macOS 64-bit universal2 installer."**
3. Open it and click **Continue → Agree → Install**.

### On Windows

1. Go to **https://www.python.org/downloads/windows/**
2. Download the latest **"Windows installer (64-bit)."**
3. Open it, and on the first screen **tick "Add python.exe to PATH"** —
   this is the important bit — then click **Install Now**.

> 💡 The **first** time you run PDF Maker it also downloads a couple of small
> components (needs internet, about a minute). After that it works offline.

## 2 · Make a PDF

1. Put your pictures in the `pictures` folder (you can delete the 3 samples).
2. Double-click **Make PDF** (**.command** on a Mac, **.bat** on Windows).
3. When it asks for a folder, just press <kbd>Return</kbd> (or drag a different folder in).
4. It asks a few quick questions — **pictures per page** (one, or three to a
   landscape page), **note margins** / **spacing**, **file size**, and
   **how many PDF files** (all explained below). Press <kbd>Return</kbd> for the
   normal choice each time.
5. Your PDF pops up next to the folder (e.g. `pictures.pdf`).

> 🔒 **The very first time you open it** (especially after downloading the zip),
> your computer may warn you. This is normal for anything not from an app store —
> the file is safe, and you only do this once.
>
> **On a Mac** — *"cannot be opened because it is from an unidentified developer"*
> or *"Apple could not verify…"*:
> 1. **Right-click** (or Control-click) **Make PDF** → **Open** → **Open**.
> 2. If there's no **Open** button, open **System Settings → Privacy & Security**,
>    scroll down, click **Open Anyway**, then try once more.
>
> **On Windows** — a blue *"Windows protected your PC"* (SmartScreen) box:
> 1. Click **More info**, then **Run anyway**.

## 3 · Three pictures to a page (landscape) 📐

Handy for **phone screenshots**: PDF Maker can place **three pictures side-by-side**
across a **landscape** page, in the same file order. Each picture is scaled to fit its
column — nothing is cropped — with a neat blank border and an equal gap between them.

```
┌───────────────────────────────┐
│  ┌─────┐  ┌─────┐  ┌─────┐   │
│  │     │  │     │  │     │   │   Three to a page — landscape
│  │     │  │     │  │     │   │
│  └─────┘  └─────┘  └─────┘   │
└───────────────────────────────┘
```

When PDF Maker asks *"How many pictures per page?"*, choose **3**. It then asks how
much **space** to leave around and between them:

| Your choice | What you get |
| --- | --- |
| **1) Half a centimetre** (default) | A tidy ½ cm border, and ½ cm between the three pictures. |
| **2) One centimetre** | A bit more breathing room. |
| **3) None** | The pictures sit edge to edge. |

In the Terminal (see §7) this is `--per-page 3` with `--gap 0.5` (in centimetres).
The file-size and split options work here too.

## 4 · Room for notes — the "shrinking factor" ✍️

By default a picture fills the whole page. If you want blank space to write in, PDF Maker can
**shrink each picture and center it**, leaving a white border. Nothing is cut off — the whole
picture stays, just smaller.

```
┌───────┐    ┌───────┐    ┌───────┐
│███████│    │ █████ │    │       │
│███████│    │ █████ │    │  ███  │
│███████│    │ █████ │    │  ███  │
│███████│    │ █████ │    │       │
└───────┘    └───────┘    └───────┘
  None         Some          Lots
(fills page) (side room)  (room all around)
```

When PDF Maker asks *"How much blank margin for handwriting notes?"*, pick:

| Your choice | What you get | Good for |
| --- | --- | --- |
| **1) None** (default) | Picture fills the page (phone shape). | Just viewing. |
| **2) Some** | ½-inch border on **Letter** paper. A tall phone photo becomes a centered column with roughly 2 inches of blank space on each side. | A few notes. |
| **3) Lots** | 1-inch border on Letter paper — the picture shrinks more, leaving space all the way around. | Lots of notes / annotations. |

### Fine control (the exact shrinking factor)

The margin is simply **how many inches of blank border to leave**. Bigger margin = smaller
picture = more room to write. For an exact amount, use the Terminal (see §7):

```
--margin 0.75      # three-quarter-inch blank border
--page letter      # standard US paper (or: a4, or a custom size like 8x10)
```

## 5 · Making the file smaller 📦

Big picture files make big PDFs. When PDF Maker asks *"Do you want a smaller PDF file?"*,
it lowers the resolution a bit and compresses the pages. Rough sizes for **100 pictures**:

| Your choice | Size (≈100 pictures) | Good for |
| --- | --- | --- |
| **1) No** (default) | ~50 MB | Best quality, archiving. |
| **2) Smaller** | ~6–8 MB | Email, printing — still sharp. |
| **3) Smallest** | ~3–4 MB | Quick sharing — still easy to read. |

> 💡 Two dials control file size (see §7 for the Terminal):
> - `--max-height 1200` — the resolution. Lower number = fewer pixels = smaller file.
> - `--quality 60` — image quality from 1–95. Lower = smaller file (60–75 looks great).
>
> Note: `--dpi` does **not** change the file size — it only sets the printed page size.

### Or split into several PDFs

The last question, *"How many PDF files?"*, can divide your pictures into
**1, 2, or 4** separate PDFs of roughly equal size — useful when one file is too big to
email, or a print shop won't take it. The pictures stay in order, split evenly, and the files
are named `…_part1_of_2.pdf`, `…_part2_of_2.pdf`, and so on.

## 6 · Which picture types work 🖼️

PDF Maker reads **JPG, JPEG, PNG, BMP, GIF, TIFF, and WEBP**. You can mix them in one folder.

> 📱 **iPhone photos (`.HEIC`)** aren't included automatically. PDF Maker will tell you
> if it finds any. To use them: on a Mac, open them in **Preview** → **File → Export** →
> set Format to **JPEG** → save into your folder. On Windows, open the photo in the
> **Photos** app → **… → Save as** → choose **JPG**. (Or on the iPhone itself:
> **Settings → Camera → Formats → Most Compatible**, which saves new photos as JPEG.)

### If a picture can't be read

If a file is damaged or isn't really a picture, PDF Maker **skips just that one and keeps going**,
and prints a clear line telling you exactly which file was the problem — for example:

```
WARNING: could not read beach_07.png — skipped it
WARNING: 1 file(s) were skipped; the PDF was built from the 24 that worked.
```

So you're never left guessing which picture caused trouble.

## Getting the pages in order

Pictures are ordered by their **file name**. Name them with numbers and a leading zero so they line up:

| Good ✅ | Risky ⚠️ |
| --- | --- |
| `01.jpg, 02.jpg, … 10.jpg` | `1.jpg, 2.jpg, … 10.jpg` (10 may come before 2) |

If your files already have a number anywhere in the name, PDF Maker sorts by that number.

## 7 · For the curious: the Terminal 🛠️

Every option is available directly. Open the **Terminal** (Mac) or **Command Prompt**
(Windows), type `python3` (Mac) or `py` (Windows) and a space, then **drag
`generate_pdf.py` into the window**, and add options. Combine anything:

```bash
# Notes + small file, on Letter paper, from your Photos folder:
python3 "…/generate_pdf.py" --src "…/pictures" --page letter --margin 0.75 --max-height 1200 --quality 65

# Three phone screenshots per landscape page, half-centimetre gaps:
python3 "…/generate_pdf.py" --src "…/pictures" --per-page 3 --gap 0.5

# Split into 3 smaller PDFs (great when a print shop won't take one big file):
python3 "…/generate_pdf.py" --src "…/pictures" --parts 3

# See every option:
python3 "…/generate_pdf.py" --help
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "unidentified developer" pop-up (Mac) | Right-click **Make PDF** → **Open** → **Open** (once). |
| "Windows protected your PC" (SmartScreen) | Click **More info** → **Run anyway** (once). |
| "permission denied" (Mac) | Open Terminal, type `chmod +x ` then drag in the **Make PDF** file and press Return (once). |
| "Python 3 isn't installed" | Do the one-time setup in §1 (python.org). |
| Window flashes open and closes (Windows) | Python probably isn't installed, or wasn't added to PATH — redo §1 and make sure **"Add python.exe to PATH"** is ticked. |
| "no supported images found" | Make sure the folder has `.jpg`/`.png` (etc.) pictures. |
| iPhone `.HEIC` photos skipped | Convert to JPEG (see §6). |
| One picture is missing from the PDF | Check the window for a **WARNING** line — it names the file it couldn't read. |

## Removing it

Nothing is installed system-wide. To remove everything, drag this whole **PDF Maker**
folder to the Trash / Recycle Bin.

---

*Made with the `generate_pdf.py` engine · one picture per page, or three to a landscape page, in order.*
