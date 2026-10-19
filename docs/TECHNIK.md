# Technische Hintergründe

Was über SingStar PS3/PS4 herausgefunden wurde und worauf StarDex aufbaut. Das Songformat selbst steht in
[FORMAT.md](FORMAT.md), die Einrichtung in [SETUP.md](SETUP.md).

Getestet mit SingStar PS4 `CUSA00033` (EU, v01.10) auf GoldHEN 2.4 / Firmware 9.03 und SingStar PS3 mit webMAN.

## Überblick

| Thema | Ergebnis |
|---|---|
| Eigene DLC-Pakete (fPKG) auf der PS4 | funktionieren: installieren, anzeigen, spielen, bleiben dauerhaft |
| Songs ohne PKG auf der PS4 (Disc-Pack) | funktionieren über SingStars Disc-Song-Lader, GoldHEN-Spielpatch und einen Symlink |
| AFR (GoldHEN File Redirector) | **Sackgasse**: SingStar lädt über Fios2 und damit an AFR vorbei |
| PS3 | lose Dateien in `/dev_hdd0/FileSystem/Export/` plus XML-Songlisten, kein Paket nötig |
| Latenz | PS3 ~40 ms, PS4 nicht unter ~60 ms – ein Grund, die PS3 zu bevorzugen |

## PS4: Wie SingStar Songs lädt

- `app0` enthält **keine** Songs. Alle Songs sind DLC-Pakete unter `/user/addcont/CUSA00033/<LABEL>/ac.pkg`.
- Das Spiel fragt die installierten DLCs über `sceAppContentGetAddcontInfoList` ab, hängt neue Pakete als
  `/addcont0` bzw. `/addcont1` ein und liest `Prod_Sku_<SKU>/config.xml` usw.
- Pro Paket entsteht ein Cache in `download0/song_covers/Prod_Sku_<SKU>/`.
- Die Songliste steht in einer LevelDB `download0/songdb/`: `SA08<id>.0` (JSON), Indizes `AA08<ARTIST>.<TITLE>~<id>`,
  `AT08…`, `AR08<Jahr>.<id>`. Lesen mit `tools/leveldb_log.py` und `tools/leveldb_table.py`.
- Installierte DLCs stehen zusätzlich in `/system_data/priv/mms/addcont.db`. Die installierte `ac.pkg` ist
  byte-identisch mit dem gebauten Paket.
- Lizenzen (`entitlement.db`) sind für eigene Pakete nicht nötig.
- Die Spielordner (`download0`, `savedata*`, `addcont0/1`) sind nur bei laufendem Spiel unter
  `/mnt/sandbox/CUSA00033_000/` erreichbar. GoldHEN muss vor SingStar gestartet sein.

### Paket-Label ↔ Song-ID (wichtigste Regel)

SingStar liest die Song-ID aus dem **Paket-Label**: Zeichen 4–6 des 16-stelligen Labels als Basis-36-Zahl.

| Label | Zeichen 4–6 | Song-ID |
|---|---|---|
| `130U9X0000000000` | `U9X` | 39237 |
| `130YQ70000000000` | `YQ7` | 45007 |

- Steht die ID schon in der Song-DB, wird das Paket übersprungen. Download-Songs, deren ID zu keinem Paket passt,
  werden beim Start aus der Song-DB gelöscht. Passen Label und Song nicht zusammen, verschwinden Songs also wieder.
- Song-IDs müssen ≤ 46655 (`ZZZ`) sein. Eigene Songs bekommen **45xxx** (`tools/songid.py`).
- Label = `130` + Basis-36(ID) + `0000000000`, Ordner im Paket `Prod_Sku_130XXX`. `build_dlc.py` prüft das.

### Weitere Regeln für PS4-Pakete

1. **Ein Song pro Paket** (folgt aus der Label-Regel). Bei mehreren Songs zeigen alle die Vorschau des letzten.
2. **Duett-Aufteilung ist Pflicht:** `melody_1.xml` braucht Zeilen mit `Singer="Solo 1"` **und** `"Solo 2"`, auch
   bei Solo-Songs, sonst stürzt Battle-Duett ab. Die Konverter teilen an den PTM-Marken auf.
3. Keine Song- oder Interpreten-IDs doppelt vergeben.
4. Vorschauvideos müssen H.264 sein (MPEG-4 Part 2 der PS3 bleibt schwarz).
5. Paketdateien nur unter vollem Namen `EP9000-CUSA00033_00-<LABEL>.pkg` installieren – ein umbenanntes Paket hat
   beim Installieren einen Absturz der Konsole ausgelöst.
6. Das Spiel beendet einen Song, wo die Melodie endet. Die Konverter hängen deshalb eine Schluss-Pause bis zum
   Videoende an.

### Pakete installieren, austauschen, entfernen

- **Installieren:** nach `/data/pkg/` hochladen, im GoldHEN-Menü mit dem Paket-Installer installieren (ganzer
  Ordner auf einmal). Pakete lassen sich bei laufendem SingStar installieren.
- **Austauschen:** Spiel schließen, neue `.pkg` mit gleichem Label per FTP über `/user/addcont/CUSA00033/<LABEL>/ac.pkg`
  schreiben. Die Song-ID muss gleich bleiben.
- **Entfernen:** im Spiel unter Einstellungen → Songs löschen. Das entfernt Paket, `addcont.db`-Zeile, Cache und
  Song-DB-Einträge sauber.
- Der Remote Package Installer hat nicht funktioniert (Fehler 0x80991404/0x80990015).

## PS4: Songs ohne PKG (Disc-Pack)

Das PS4-Spiel enthält den kompletten Disc-Song-Lader der PS3-Fassung. Er sucht `Pack0.psarc`, `Pack1.psarc` … in
`/app0/` – die Download-Fassung hat dort keine.

- Ein **GoldHEN-Spielpatch** (Plugin `game_patch.prx`, Plugin-Lader in GoldHEN eingeschaltet) lenkt den Pfad auf
  `/download0/` um. Andere Ziele (`/data`, `/av_contents`) lädt Fios2 nicht.
- Das Archiv ist ein PSARC mit dem Layout `filesystem/export/…` im PS3-Export-Format (`config.xml`, `songs_N_0.xml`,
  `acts`, `covers`, `textures`, `<id>/melody/video/preview`). Erzeugt von `tools/ps4_discpack.py` / `tools/psarc.py`.
- Disc-Songs erscheinen unter dem Filter „Songs auf Disc“ und stehen in der Song-DB unter `SB08<id>`. Nicht mehr
  gefundene Disc-Songs entfernt das Spiel beim nächsten Start.
- **1-GiB-Grenze:** `download0` ist ein festes Image (`download0.dat`, 1 GiB). Jede Änderung an
  `DOWNLOAD_DATA_SIZE` lehnt das System ab („Daten sind defekt“).
- **Lösung per Symlink:** `download0.dat` ist ein unverschlüsseltes UFS2. `download0/Pack0.psarc` wird zu einem
  Symlink auf `/av_contents/video/ss/Pack0.psarc` (= `/user/av_contents/video/ss/`, große Benutzerpartition, jederzeit
  per FTP erreichbar). Den Symlink legt die Payload `tools/payload/dl0link.elf` direkt auf der PS4 an (an den GoldHEN-BinLoader, Port 9090;
  die rohe `.bin` lehnt GoldHEN ab) – der Manager und `tools/ps4_install.py` senden sie selbst. Alternativ am PC über
  das Image (`tools/ufs_symlink.py`, `tools/dev/dl0_link.py`). Wird `download0` neu angelegt, muss der Symlink neu gesetzt werden.

## PS4: Fehlerdialog beim Start

Ohne PSN-Server zeigt SingStar beim Start „Ein Fehler ist aufgetreten (SU-41766-4)“ bzw. NW-31201-7. Der Patch
„No online check error at startup“ (`tools/no_online_check.py`, auch im Manager) lässt das Öffnen des
System-Fehlerdialogs fehlschlagen (`sceErrorDialogInitialize` → nop, `sceErrorDialogOpen` → `mov eax,1`).
Nebenwirkung: SingStar zeigt gar keine System-Fehlerdialoge mehr.

## PS3: Songs schreiben

- Pro Song ein Ordner `Export/<id>/` mit `melody_4.xml` (+ `melody.xml`), `video.mp4` (H.264 + AAC, **max.
  1280×720** – 1080p bleibt schwarz) und `preview.mp4` (368×208, MPEG-4 Part 2 „mp4v“ + AAC, 30 s).
- Dazu Einträge in `songs_4_0.xml`, `acts_4_0.xml`, `covers.xml` + `textures/page_<id>.jpg` (256×256) und **jeder
  Song im Carousel** von `songlists_4.xml`.
- Lautheit: offizielle PS3-Songs −4,7 … −22,6 LUFS (Median ≈ −9,5) → StarDex nimmt −10 LUFS (PS4: −12).
- webMAN-FTP ist schnell überlastet („421 Could not create socket“). StarDex wiederholt mit neuer Verbindung, liest
  und schreibt die PS3 nur auf Knopfdruck und ändert die Listen einmal pro Auftrag (Sicherung → Zusammenführen →
  XML-Prüfung → Upload → Zurücklesen).
- Die Song-DB der PS3 (`/dev_hdd0/game/BCES00011SINGSTARFAMILY/USRDIR/songdb`) wird aus dem Export-Ordner aufgebaut.

## UltraStar → SingStar

- Umrechnung (gegen die SingStar Toolbox geprüft): Tempo = BPM/2, 1 UltraStar-Beat = 1 Tick, MidiNote = 60 + Ton,
  `*` Bonus, `F` FreeStyle, `R`/`G` Rap, `#GAP` als Vorlauf in ganzen Ticks.
- Silbentrennung aus den UltraStar-Leerzeichen (` -` nur innerhalb eines Wortes). Typografische Zeichen → ASCII.
- Lautheit nach EBU R128, Spitzen ≤ −1,5 dBTP.
- Video: H.264 yuv420p bis 1080p wird übernommen, sonst neu kodiert (H.264 High, 25 fps); `#VIDEOGAP` erzwingt
  Neukodierung. Ohne Video: Cover als Standbild.
- Vorschau/Medley-Start: `#MEDLEYSTARTBEAT` → Refrain-Zeit aus einer PS3-Bibliothek (falls vorhanden) → eigene
  Refrain-Erkennung (häufigster Textblock) → ein Drittel der Songlänge.
- Rap: Rap-Noten bekommen `FreeStyle="Yes" Rap="Yes"`, eine Tonhöhe pro Zeile, Prüfpunkte an Wortanfängen und
  `GAMEPLAY Rap` / `<RAP>`-Block in den Metadaten. Unmarkierter Rap wird für Songs in `rap_songs.json`
  (`{"Interpret - Titel": true}`) erkannt (`tools/rap_detect.py`).
- Noch nicht unterstützt: UltraStar-Duette `P1`/`P2`, `#RELATIVE`.

## Gesangsreduktion (ADRS)

SingStar kann die Originalstimme absenken („Stimmreduzierung“), wenn die Melodie `<ADRS>`-Einträge hat (Stereoposition,
Breite, Frequenzband). Sonys Werte sind redaktionell gewählt und lassen sich nicht aus dem Mix ableiten.

- StarDex setzt ADRS nur bei geeigneten Songs: Azimuth 0, Breite 0,15, Band 312,5–3125 Hz, SoftSupression 0.
- Ob ein Abschnitt reduziert wird, entscheidet eine Demucs-Gesangsspur (`tools/adrs_auto.py`); Eignung messen
  `tools/adrs_fit.py` / `tools/adrs_us_scan.py`.
- Bei PS2-Songs dient die echte Gesangsspur der Disc als Grundlage.

## Favoriten und Statistik

- PS3 und PS4 nutzen dasselbe Backend: pro Benutzer LevelDBs `pinDB` (Favoriten), `songstatsdb`, `chartsdb`.
- Ein Favorit = 5 Schlüssel in `pinDB`: `SI00<id>.0`, `AI00<artistKey>.<id>`, `TI00<titleKey>.<id>`,
  `RI00<Jahr>.<id>`, `DPI0<pinnedDate>.<id>`.
- PS4: bei laufendem Spiel eine neue LevelDB-Logdatei mit hoher Nummer in `download0/<user>/pinDB/` legen und
  SingStar neu starten – das Spiel spielt sie ein (`tools/dev/ps4_favs.py`).
- PS3: Daten liegen unverschlüsselt in `/dev_hdd0/game/BCES00011SINGSTARFAMILY/USRDIR/` und sind jederzeit per FTP
  lesbar.

## Werkzeuge

| Datei | Zweck |
|---|---|
| `tools/us_to_ps4.py` | UltraStar-Ordner → PS4-Paketordner (Label/ID, Lautheit, Vorschau, Refrain, Duett-Aufteilung, Medley, Rap, ADRS) |
| `tools/ps3_to_ps4.py` | PS3-Export → PS4-Paketordner |
| `tools/ps2_to_ps4.py`, `tools/ps2pak.py` | PS2-Disc → PS4-Paketordner (IPU-Video, MIB-Ton, Cover, ADRS) |
| `tools/to_ps3.py` | PS3-Fassung aus UltraStar, PS2, PS3-Disc oder PS4-Paket |
| `tools/build_dlc.py`, `tools/songid.py` | Paketordner → `.pkg` (mit Label-Prüfung), Label ↔ Song-ID |
| `tools/singstar_pkg.py`, `tools/singstar_pack.py`, `tools/ps4_install.py` | eigenständige Werkzeuge des Weitergabe-Pakets (`tools/make_release.py`) |
| `tools/ps4_discpack.py`, `tools/psarc.py` | Disc-Pack (`Pack0.psarc`) bauen, Patch-XML schreiben |
| `tools/payload/`, `tools/ufs_symlink.py`, `tools/dev/dl0_link.py` | Symlink in `download0` anlegen (PC oder PS4) |
| `tools/no_online_check.py` | Patch gegen den Fehlerdialog beim Start |
| `tools/disc_import.py` | PS3-/PS2-Disc-Abbilder einlesen (scee_london, 7-Zip) |
| `tools/batch_us.py`, `tools/batch_ps3.py`, `tools/batch_ps2.py` | Gesamtdurchläufe → Pakete + Bericht (`--only`, `--upload`) |
| `tools/ps4_pins.py`, `tools/dev/ps4_favs.py`, `tools/leveldb_*.py` | Favoriten und Song-DB (LevelDB) lesen/schreiben |
| `tools/adrs_*.py`, `tools/rap_detect.py`, `tools/dev/vocal_adrs.py` | Gesangsreduktion, Rap-Erkennung |
| `tools/dev/ebootdis.py`, `xref.py`, `nid.py`, `imports.py` | `eboot.bin` untersuchen |
| `tools/dev/remote/ps4ctl.py` | PS4-Fernsteuerung für Entwicklung und Tests (SingStar starten/beenden, Bild, Tasten) |
| `tools/local_config.py` | liest IPs und Ordner aus `manager/config.json` |
