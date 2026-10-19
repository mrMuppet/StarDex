# SingStar PS4 – Custom Songs

Sing your own **UltraStar** songs in **SingStar on the PS4**. Each song becomes a small add-on package (fake DLC)
that you install on a PS4 with GoldHEN. The songs then appear in SingStar's song list next to the official ones –
with lyrics, pitch lines, scoring, video, cover and preview, just like a bought song.

This package contains **tools only – no songs and no Sony files**. Only use songs you own.

---

## What you need

**PS4**
- Jailbroken with **GoldHEN** (tested with GoldHEN 2.4 on firmware 9.03).
- **FTP** switched on in the GoldHEN settings (port 2121).
- **SingStar, European version (CUSA00033)** installed. Other regions are not tested and will most likely not
  accept the packages.

**PC** (Windows, Linux or macOS)
- **Python 3.10** or newer – https://www.python.org (no extra packages needed).
- **ffmpeg** (with ffprobe) on the PATH – https://ffmpeg.org.
- **.NET runtime** (any version from 3.1 on, e.g. .NET 8) – https://dotnet.microsoft.com/download.
  Needed by PkgTool, which builds the packages.
- An FTP client (e.g. FileZilla, WinSCP), or use the built-in upload (`--upload`).

**Songs**: UltraStar song folders – a `.txt` with `#TITLE`/`#ARTIST` plus audio (mp3/ogg/m4a/…), ideally a video
(mp4/mkv/avi/…) and a cover (jpg/png).

---

## Step 1 – Build the packages

Open a terminal in this folder and run:

```
python singstar_pkg.py "D:\UltraStar\songs"
```

- You can pass one song folder or a folder with many songs (searched recursively), or several folders.
- The packages land in `pkgs\`, one per song, named like
  `EP9000-CUSA00033_00-130YQ70000000000.pkg`.
- Running it again only builds new or changed songs.

What happens to each song:
- lyrics and notes are converted (golden notes, freestyle and rap notes included),
- audio normalised to -12 LUFS so all songs are equally loud,
- the video is kept up to 1080p (copied without quality loss when possible, otherwise re-encoded);
  songs without a video get their cover as picture,
- a 30-second preview from the chorus (`#MEDLEYSTARTBEAT` if the txt has it).

Time: about 10–20 seconds per song when the video can be copied, a few minutes when it must be re-encoded.

> **Keep the file `song_ids.json`.** Every song gets a fixed id (45300 and up) that is stored there. If you lose it,
> rebuilt songs get new ids and install as *different* songs (scores and favourites are tied to the id).

> **Duets (`P1`/`P2` in the txt) are not supported yet** and are skipped.

## Step 2 – Copy the packages to the PS4

Copy the `.pkg` files via FTP into **`/data/pkg/`** on the PS4 (create the folder if it does not exist).

> ⚠️ **Never rename the package files.** Keep the full name `EP9000-CUSA00033_00-….pkg`. Installing a renamed
> package crashed a PS4 in testing (it needed a hard power-off).

Or let the tool upload them (GoldHEN FTP must be on):

```
python singstar_pkg.py "D:\UltraStar\songs" --upload <PS4-IP>
```

(use your PS4's IP address – shown in the GoldHEN notification or under Settings → Network → View Connection Status).
Packages that are already on the PS4 with the same size are skipped.

## Step 3 – Install on the PS4

Install the packages from `/data/pkg/` with the **package installer of GoldHEN**. It lists the packages in
`/data/pkg/`; you can install them one by one or all at once. Any other homebrew package installer that reads
`/data/pkg/` works as well.

You can install while SingStar is running. If new songs do not show up, close SingStar completely and start it
again.

After the installation you can delete the `.pkg` files in `/data/pkg/` to free space – the installed copy is
separate.

## Step 4 – Sing

The songs appear in SingStar's song list like any other song.

---

## Removing a song

In SingStar: **Settings → Delete songs**. This lists all installed songs (yours included) and removes them cleanly.

## Changing a song

Fix the UltraStar files, run `singstar_pkg.py` again (the song keeps its id, so the package keeps its name),
delete the old version in SingStar (Settings → Delete songs) and install the new package.

## Limits

- Up to about 1350 custom songs (ids 45300–46655; the id is encoded in the package name).
- Duets are not supported yet.
- Only the European SingStar (CUSA00033) is tested.

## Problems

| Problem | What to do |
|---|---|
| `ffmpeg not found` / `dotnet not found` | Install it and make sure it is on the PATH (open a new terminal after installing). |
| A song is `FAILED` | The last line of the message names the cause – usually a missing audio file, a broken txt or a video ffmpeg cannot read. Fix the song folder and run again. |
| Lyrics are too early/late | The UltraStar `#GAP`/`#VIDEOGAP` of that song is off – fix it in the txt (e.g. with an UltraStar editor) and rebuild. |
| Song installed but not in the list | Restart SingStar. Check that you have the European version (CUSA00033). |
| PS4 crashed during install | Was a package renamed? Use the original file name. |

---

## Contents

| File / folder | Purpose |
|---|---|
| `singstar_pkg.py` | UltraStar folders → one SingStar package per song (+ optional FTP upload) |
| `lib/` | converter (UltraStar → SingStar melody, video, preview, cover) and package builder |
| `lib/PkgTool/` | PkgTool from LibOrbisPkg (LGPL-3.0, see `lib/PkgTool/LICENSE.txt`, https://github.com/maxton/LibOrbisPkg) |
| `DISC_PACK.md`, `singstar_pack.py`, `ps4_install.py`, `ps4/` | experimental alternative without packages (see `DISC_PACK.md`) |

## How it works (short)

SingStar PS4 keeps every song in its own add-on package. The game links a package to its song through the package
label: characters 4–6 of the label, read as a base-36 number, must equal the song id (e.g. label `130YQ7…` →
`YQ7` → song 45007). The tool converts the UltraStar song into SingStar's own format (`songs`/`acts`/`covers` XML,
`melody` XML, `video.mp4`, `preview.mp4`, cover texture), assigns an id and builds a fake-DLC package with exactly
that label, which GoldHEN can install.
