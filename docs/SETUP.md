# Einrichtung

## In drei Schritten

1. **Installieren:**
   - [Python](https://www.python.org) 3.10 oder neuer (unter Windows beim Installieren „Add python.exe to PATH“
     anhaken)
   - [ffmpeg](https://ffmpeg.org) im PATH (unter Windows z. B. `winget install ffmpeg`)
   - nur für die PS4 zusätzlich die [.NET-Runtime](https://dotnet.microsoft.com/download) (z. B. .NET 8)
2. **Starten:** `start.bat` doppelklicken (Linux/macOS: `./start.sh`). Beim ersten Start wird die Python-Umgebung
   eingerichtet und einmal gefragt, ob PkgTool, scee_london und IPUenc heruntergeladen werden sollen (siehe
   [Zusatzprogramme](#zusatzprogramme)); danach öffnet sich der Manager im Browser unter http://127.0.0.1:5077.
3. **Im Manager einrichten:** unter **Einstellungen** die Konsolen (Typ, IP) und die Speicherorte eintragen. Eigene
   UltraStar-Songs kommen in den Ordner „UltraStar-Songs“ – standardmäßig `songs/ultrastar` im Projektordner.

Danach Songs auswählen und „Auf PS3 übertragen“ bzw. „PS4-Pakete bauen“ und hochladen.

## Konsolen vorbereiten

Mindestens eine der beiden Konsolen wird gebraucht; der Manager kann beide gleichzeitig verwalten.
Empfohlen ist die PS3 (SingStar läuft dort flüssiger, Übertragung ohne Pakete und Patches).

### PS3

- Custom Firmware oder HEN mit **webMAN** und FTP (Port 21).
- SingStar PS3 mit Song-Bibliothek. StarDex schreibt nach `/dev_hdd0/FileSystem/Export/` und sichert die Songlisten
  vor jeder Änderung.
- Nach dem Übertragen SingStar neu starten. Nicht übertragen, während gesungen wird (webMAN-FTP wird sonst überlastet).

### PS4

- Jailbreak mit **GoldHEN** (getestet: GoldHEN 2.4, Firmware 9.03), **FTP** eingeschaltet (Port 2121).
- **SingStar, EU-Fassung `CUSA00033`, v01.10.** Andere Regionen sind nicht getestet.
- Zwei Wege, einstellbar je PS4 unter Einstellungen → Konsolen → „Installation“:
  - **PKG (empfohlen):** Der Manager lädt die Pakete nach `/data/pkg/`, installiert wird im GoldHEN-Menü mit dem
    Paket-Installer (ganzer Ordner auf einmal). Entfernen im Spiel unter Einstellungen → Songs löschen.
  - **Disc-Pack (ohne PKG):** Alle Songs landen in einem `Pack0.psarc`. Dafür braucht GoldHEN das Plugin
    `game_patch.prx` mit eingeschaltetem Plugin-Lader und den **BinLoader** (Port 9090). „Disc-Lader einrichten“ im
    Manager trägt den Spielpatch ein und legt bei laufendem SingStar den nötigen Verweis per Payload
    (`tools/payload/dl0link.elf`) selbst an. Die Songs erscheinen unter dem Filter „Songs auf Disc“.
- Optional: „Fehlermeldung beim Start ausblenden“ im Konsolen-Kasten (Patch gegen SU-41766-4 / NW-31201-7).

## Zusatzprogramme

Nicht im Repository enthalten; nur nötig, wenn man die jeweilige Funktion nutzt.

**PkgTool, scee_london und IPUenc lädt StarDex selbst herunter** – von den offiziellen GitHub-Releases, in fester
Version und mit geprüfter SHA-256-Prüfsumme; die Lizenzdateien liegen danach neben den Programmen.
Drei Wege, alle gleichwertig:

- `start.bat` / `start.sh` fragt beim ersten Start einmal nach (unter 1 MB),
- im Manager unter **Einstellungen → Zusatzprogramme** „Fehlende herunterladen“ (dort steht auch, was sonst fehlt:
  .NET, ffmpeg, 7-Zip),
- von Hand: `.venv/Scripts/python tools/fetch_tools.py` (`--check` zeigt nur den Stand, `--force` lädt neu).

| Wofür | Programm | Ablage | Quelle |
|---|---|---|---|
| PS4-Pakete bauen | PkgTool aus LibOrbisPkg v0.2.231 (LGPL-3.0) + .NET-Runtime | `tools/PkgTool/` (`PkgTool.Core.dll` usw.), **automatisch** | https://github.com/maxton/LibOrbisPkg (Release v0.2, `PkgTool.Core-0.2.231.zip`) |
| PS3-Discs einlesen | scee_london v1.4.3 (GPL-3.0) | `tools/scee_london/windows/scee_london.exe`, **automatisch** | https://github.com/EdnessP/scee-london (Release v1.4.3) |
| PS2-Discs einlesen | IPUenc v1.1 von ravenDS (GPL-3.0) | `tools/IPUenc/IPUenc.exe`, **automatisch** | https://github.com/ravenDS/IPUenc (Release v1.1, `IPUenc-win-x64.exe`) |
| `.7z`-Disc-Abbilder | 7-Zip | `C:/Program Files/7-Zip/7z.exe` | https://www.7-zip.org |
| Gesangstrennung für ADRS | Demucs | Pfad in `manager/config.json` → `demucs` (sonst PATH) | https://github.com/adefossez/demucs |
| USDB-Downloads | UltraStarWorker | Ordner in `manager/config.json` → `usdb_worker` | – |
| „PS3 prüfen“ | SingStar Fixer | Datei in `manager/config.json` → `singstar_fixer` | – |

Eine neuere Version von PkgTool, scee_london oder IPUenc: in `tools/fetch_tools.py` Adresse, Version und `sha256` der
Release-Dateien anpassen, dann `tools/fetch_tools.py --force`.

PkgTool ist für .NET Core 3.0 gebaut; `tools/build_dlc.py` setzt `DOTNET_ROLL_FORWARD=Major`, damit es auch mit .NET 8
läuft.

## Für Fortgeschrittene

### `manager/config.json`

Wird beim ersten Start aus `manager/config.example.json` angelegt. Die Speicherorte lassen sich bequemer in den
Einstellungen des Managers ändern; direkt in der Datei stehen nur Dinge, die die App nicht abfragt:

- `toolbox_exports`, `toolbox_keys_db` – Exporte und `tools/keys.db` der SingStar Toolbox (für die Editionen)
- `demucs`, `singstar_fixer`, `usdb_worker` – siehe Tabelle oben
- `ps4.host` / `ps3.host` – IPs für die Kommandozeilenwerkzeuge in `tools/` (der Manager nimmt die Konsolenliste aus
  den Einstellungen)

Relative Pfade gelten ab dem Projektordner.

### Kommandozeile

Alle Konverter lassen sich auch ohne Manager benutzen (Python aus `.venv`):

```bash
.venv/Scripts/python tools/to_ps3.py ultrastar "songs/ultrastar/Artist - Title" build/ps3/song --ps4-id 45300
.venv/Scripts/python tools/us_to_ps4.py "songs/ultrastar/Artist - Title" build/song/root
.venv/Scripts/python tools/build_dlc.py build/song/root auto "SingStar Custom Artist" build/song
```

### Payload neu bauen

`tools/payload/dl0link.elf` liegt fertig bei. Neu bauen in WSL/Linux mit gcc: `cd tools/payload && make`.

### Entwicklerwerkzeuge

`tools/dev/` enthält Werkzeuge für die Entwicklung: eboot-Analyse, Testskripte, die PS4-Fernsteuerung
(`tools/dev/remote/`, eigene venv, Kopplung per PSN-Konto-ID und PIN) u. a. Zusätzliche Pakete:
`tools/dev/requirements.txt`. Für die normale Nutzung wird nichts davon gebraucht.

Mehr Hintergrund: [TECHNIK.md](TECHNIK.md), Format: [FORMAT.md](FORMAT.md).
