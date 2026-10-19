# SingStar PS4 – own songs without PKG (disc-pack loader, experimental)

> Alternative to the package method in README.md. Advantage: no install step on the PS4, no fake DLC.
> Drawback: all songs are in ONE file – every new song means rebuilding and re-uploading the whole pack.
> Needs a GoldHEN game patch for SingStar v01.10 and a payload. For most people README.md (packages) is simpler.

Put your own UltraStar songs into **SingStar (PS4, CUSA00033)** – no fake PKGs, no DLC installs. All songs go into
one file `Pack0.psarc`, which the game's built-in disc-song loader reads. The songs show up in the song list
(filter **"Songs on disc"**) and can be sung like any other song.

This package contains **tools only, no songs and no Sony files**. Only use songs you own.

## Kurzanleitung (Deutsch)

1. PS4: GoldHEN läuft, FTP und BinLoader an, Plugin `game_patch.prx` für CUSA00033 in `plugins.ini`,
   Plugin-Lader in GoldHEN eingeschaltet.
2. PC: Python 3.10+ und ffmpeg installieren.
3. `python singstar_pack.py "D:\UltraStar\songs" -o Pack0.psarc`
4. SingStar auf der PS4 starten, dann `python ps4_install.py <PS4-IP> Pack0.psarc`
5. SingStar ganz schließen und neu starten → Filter „Songs auf Disc“.

Neue Songs: Schritt 3 wiederholen (bereits umgewandelte Songs werden wiederverwendet), Pack hochladen
(`ps4_install.py`), SingStar neu starten. Die Datei `song_ids.json` nicht löschen – sie hält die Song-IDs fest.

## Requirements

**PS4**
- Jailbroken with **GoldHEN 2.4** (tested on firmware 9.03), with **FTP** (port 2121) and **BinLoader**
  (port 9090) switched on in the GoldHEN settings.
- **SingStar CUSA00033, version 01.10** (the patch is made for this eboot).
- **GoldHEN game_patch plugin** (`game_patch.prx` from GoldPlugins) in `/data/GoldHEN/plugins/` and listed in
  `/data/GoldHEN/plugins.ini`:
  ```
  [CUSA00033]
  /data/GoldHEN/plugins/game_patch.prx
  ```
- **Plugin loader enabled** in the GoldHEN menu. When SingStar starts, GoldHEN shows "1 Patch Applied".

**PC**
- Python 3.10 or newer (no extra packages needed).
- ffmpeg and ffprobe on PATH (https://ffmpeg.org).

## 1. Build the pack

```
python singstar_pack.py "D:\UltraStar\songs" -o Pack0.psarc
```

- Takes one or more folders; song folders are found recursively (UltraStar `.txt` with `#TITLE` and `#ARTIST`, plus
  audio, video and cover).
- Each song: melody/lyrics converted, audio normalised to -12 LUFS, video kept up to 1080p (copied when possible),
  30 s preview from the chorus (`#MEDLEYSTARTBEAT` if set). Songs without video get the cover as picture.
- Converted songs are cached in `work/`; running it again only converts new or changed songs.
- **Duets (P1/P2) are not supported yet** and are skipped.
- Song ids start at 45300 and are kept in `song_ids.json` – keep that file, otherwise ids change and in-game scores
  and favourites no longer match.

Takes roughly 10–20 s per song when the video can be copied, a few minutes when it has to be re-encoded.

## 2. Install on the PS4

Start SingStar on the PS4 (it must be running for the first install), then:

```
python ps4_install.py 192.168.x.x Pack0.psarc
```

What it does:
1. Adds the GoldHEN patch "Disc songs from /download0/Pack0.psarc" to `/data/GoldHEN/patches/xml/CUSA00033.xml`
   (an existing file is kept and saved to `backup/` first) and switches it on.
2. Uploads the pack to `/user/av_contents/video/ss/Pack0.psarc` (no size limit, SingStar may be closed).
3. Creates the link `download0/Pack0.psarc` → that file by sending the payload `ps4/dl0link.elf` to the
   BinLoader. The game's loader only reads from its own `download0` folder, which is a fixed 1 GiB image –
   the link lets it read the big file from the user partition. It is only needed once.

Then **close SingStar completely and start it again**. Use the filter "Songs on disc" to see only the new songs.

`python ps4_install.py 192.168.x.x --check` shows the current state without changing anything.

### Updating the pack

Rebuild (`singstar_pack.py`), upload again (`ps4_install.py <IP> Pack0.psarc` – SingStar may be closed for the
upload), restart SingStar.

### Removing

Delete `/user/av_contents/video/ss/Pack0.psarc` via FTP, or switch the patch off in the GoldHEN patch menu.

## Manual install (without ps4_install.py)

1. Copy `ps4/CUSA00033.xml` to `/data/GoldHEN/patches/xml/` (or add its `<Metadata>` block to your existing file)
   and switch the patch on in the GoldHEN game patch menu.
2. Upload `Pack0.psarc` to `/user/av_contents/video/ss/` via FTP.
3. Start SingStar, send `ps4/dl0link.elf` to port 9090 (any payload sender). Use the **.elf** – GoldHEN rejects a raw
   .bin with "invalid payload format".
4. Restart SingStar.

## Problems

- **No songs after the restart:** is the patch applied ("1 Patch Applied" when SingStar starts)? Is the plugin loader
  on? Run `ps4_install.py <IP> --check` with SingStar running: the link must be "link".
- **Link "missing" again** (e.g. after deleting SingStar's game data or reinstalling the game): start SingStar and
  run `ps4_install.py <IP>` again.
- **A song shows no preview picture / black video:** the source video uses an unusual format; re-encode it to H.264
  or let the tool re-encode it (delete its folder in `work/` after fixing the source).
- The payload writes its result to the GoldHEN kernel log (port 3232) as "SingStar-Link …".

## Contents

| File | Purpose |
|---|---|
| `singstar_pack.py` | UltraStar folders → `Pack0.psarc` |
| `ps4_install.py` | patch + upload + link on the PS4 (FTP, BinLoader) |
| `lib/` | converter modules (UltraStar → SingStar melody/video/preview, PSARC writer) |
| `ps4/CUSA00033.xml` | GoldHEN patch (one line: loader prefix `/app0/` → `/download0/`) |
| `ps4/dl0link.elf` | GoldHEN payload: creates the `download0` link (source in `ps4/payload_source/`, build with gcc: `make`) |

How it works: SingStar PS4 still contains the disc-song loader of the PS3 version. It looks for `Pack0.psarc`
in `/app0/`; the patch changes that prefix to `/download0/`. The pack holds the same files as a PS3 SingStar disc
(`filesystem/export/`: `config.xml`, `songs_4_0.xml`, `acts_4_0.xml`, `covers.xml`, per song `melody`, `video.mp4`,
`preview.mp4`, cover page).
