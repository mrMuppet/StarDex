# Setup

**English** · [Deutsch](SETUP.md)

## In three steps

1. **Install:**
   - [Python](https://www.python.org) 3.10 or newer (on Windows tick “Add python.exe to PATH” during installation)
   - [ffmpeg](https://ffmpeg.org) on the PATH (on Windows e.g. `winget install ffmpeg`)
   - for the PS4 only: the [.NET runtime](https://dotnet.microsoft.com/download) as well (e.g. .NET 8)
2. **Start:** double-click `start.bat` (Linux/macOS: `./start.sh`). On first start the Python environment is set up
   and you are asked once whether PkgTool, scee_london and IPUenc should be downloaded (see
   [Additional programs](#additional-programs)); then the manager opens in the browser at http://127.0.0.1:5077.
3. **Set up in the manager:** under **Settings**, enter the consoles (type, IP) and the storage folders. The language
   can be switched to English there as well. Your own UltraStar songs go into the folder “UltraStar songs” – by
   default `songs/ultrastar` in the project folder.

Then select songs and use “Transfer to PS3” or “Build PS4 packages” and upload.

## Preparing the consoles

At least one of the two consoles is needed; the manager can handle both at the same time.
The PS3 is recommended (SingStar has less delay there, transfer without packages and patches).

### PS3

- Custom firmware or HEN with **webMAN** and FTP (port 21).
- SingStar PS3 with song library. StarDex writes to `/dev_hdd0/FileSystem/Export/` and backs up the song lists before
  every change.
- Restart SingStar after transferring. Do not transfer while someone is singing (webMAN FTP gets overloaded).

### PS4

- Jailbreak with **GoldHEN** (tested: GoldHEN 2.4, firmware 9.03), **FTP** switched on (port 2121).
- **SingStar, EU version `CUSA00033`, v01.10.** Other regions are not tested.
- Two routes, selectable per PS4 under Settings → Consoles → “Installation”:
  - **PKG (recommended):** the manager uploads the packages to `/data/pkg/`; they are installed in the GoldHEN menu
    with the package installer (whole folder at once). Remove them in the game under Settings → Delete songs.
  - **Disc pack (without PKG):** all songs end up in one `Pack0.psarc`. This needs the GoldHEN plugin
    `game_patch.prx` with the plugin loader switched on, and the **BinLoader** (port 9090). “Set up disc loader” in
    the manager adds the game patch and, while SingStar is running, creates the required link itself via a payload
    (`tools/payload/dl0link.elf`). The songs appear under the filter “Songs on disc”.
- Optional: “Hide the error message at start” in the console box (patch against SU-41766-4 / NW-31201-7).

## Additional programs

Not included in the repository; only needed if you use the respective feature.

**StarDex downloads PkgTool, scee_london and IPUenc itself** – from the official GitHub releases, in a pinned version
and with a verified SHA-256 checksum; the licence files are placed next to the programs.
Three equivalent ways:

- `start.bat` / `start.sh` asks once on first start (less than 1 MB),
- in the manager under **Settings → Additional programs**, “Download missing” (it also lists what else is missing:
  .NET, ffmpeg, 7-Zip),
- by hand: `.venv/Scripts/python tools/fetch_tools.py` (`--check` only shows the state, `--force` downloads again).

| For | Program | Location | Source |
|---|---|---|---|
| Building PS4 packages | PkgTool from LibOrbisPkg v0.2.231 (LGPL-3.0) + .NET runtime | `tools/PkgTool/` (`PkgTool.Core.dll` etc.), **automatic** | https://github.com/maxton/LibOrbisPkg (release v0.2, `PkgTool.Core-0.2.231.zip`) |
| Importing PS3 discs | scee_london v1.4.3 (GPL-3.0) | `tools/scee_london/windows/scee_london.exe`, **automatic** | https://github.com/EdnessP/scee-london (release v1.4.3) |
| Importing PS2 discs | IPUenc v1.1 by ravenDS (GPL-3.0) | `tools/IPUenc/IPUenc.exe`, **automatic** | https://github.com/ravenDS/IPUenc (release v1.1, `IPUenc-win-x64.exe`) |
| `.7z` disc images | 7-Zip | `C:/Program Files/7-Zip/7z.exe` | https://www.7-zip.org |
| Vocal separation for ADRS | Demucs | path in `manager/config.json` → `demucs` (otherwise PATH) | https://github.com/adefossez/demucs |
| USDB downloads | UltraStarWorker | folder in `manager/config.json` → `usdb_worker` | – |
| “Check PS3” | SingStar Fixer | file in `manager/config.json` → `singstar_fixer` | – |

For a newer version of PkgTool, scee_london or IPUenc: adjust URL, version and `sha256` of the release files in
`tools/fetch_tools.py`, then run `tools/fetch_tools.py --force`.

PkgTool is built for .NET Core 3.0; `tools/build_dlc.py` sets `DOTNET_ROLL_FORWARD=Major` so that it also runs on
.NET 8.

## Advanced

### `manager/config.json`

Created from `manager/config.example.json` on first start. Storage folders are easier to change in the manager's
settings; the file itself only holds things the app does not ask for:

- `toolbox_exports`, `toolbox_keys_db` – exports and `tools/keys.db` of the SingStar Toolbox (for the editions)
- `demucs`, `singstar_fixer`, `usdb_worker` – see the table above
- `ps4.host` / `ps3.host` – IPs for the command-line tools in `tools/` (the manager takes the console list from its
  settings)

Relative paths are relative to the project folder.

### Command line

All converters can also be used without the manager (Python from `.venv`):

```bash
.venv/Scripts/python tools/to_ps3.py ultrastar "songs/ultrastar/Artist - Title" build/ps3/song --ps4-id 45300
.venv/Scripts/python tools/us_to_ps4.py "songs/ultrastar/Artist - Title" build/song/root
.venv/Scripts/python tools/build_dlc.py build/song/root auto "SingStar Custom Artist" build/song
```

### Rebuilding the payload

`tools/payload/dl0link.elf` is included ready-made. To rebuild it in WSL/Linux with gcc: `cd tools/payload && make`.

### Developer tools

`tools/dev/` contains development tools: eboot analysis, test scripts, the PS4 remote control (`tools/dev/remote/`,
own venv, pairing via PSN account ID and PIN) and more. Extra packages: `tools/dev/requirements.txt`. None of this is
needed for normal use.

More background (German): [TECHNIK.md](TECHNIK.md), format: [FORMAT.md](FORMAT.md).
