# SingStar PS4 (CUSA00033) – Song-Format

Befund aus dem Dump vom 2026-09-27 (Referenz-Song: Idina Menzel – Let It Go, ID 39237, Pack `Prod_Sku_130U9X`).

## Wo die Songs liegen

| Ort | Inhalt |
|---|---|
| `app0/` | **keine Songs**; nur UI, Shader, Menü-Audio (`.bnk`/`.xvag`) |
| `/user/addcont/CUSA00033/<ID>/ac.pkg` | DLC-Songpacks, verschlüsselt (PKG) |
| `/addcont0/Prod_Sku_XXXXXX/` | gemountetes DLC, **entschlüsselte lose Dateien** |
| `/download0/song_covers/Prod_Sku_*/` | Metadaten-Cache aller Packs (ohne Video) |
| `/download0/songdb/` | LevelDB-Index (Keys `AA08<ARTIST>.<TITLE>~<id>`, `AT08…`, `AR08<year>.<id>`, `SA08<id>.0`) |

## Pack-Aufbau (`Prod_Sku_XXXXXX/`)

```
config.xml          Pack-Manifest: verweist auf songs/acts/covers/chc, CACHE-Dateiliste
songs_1_0.xml       Song-Metadaten: Titel, BPM, Chorus-Zeit, Medley-Bereiche, Video-Länge/-Größe
acts_1_0.xml        Interpreten (ACT ID → NAME)
covers.xml          Cover-Atlas: TPAGE_BIT → textures/page_N.jpg, UV 256x256
melodies_1.chc      zlib-Cache aller melody_1.xml (siehe unten)
textures/page_0.jpg Cover-Atlas
<songid>/melody_1.xml     Noten + Text (Klartext-XML)
<songid>/video.mp4        H.264 Main 1280x720@25 + AAC-LC 48 kHz stereo, moov vorne (faststart)
<songid>/preview.mp4      H.264 High 368x208 + AAC, 30 s
<songid>/audiopreview.mp4 bytegleich mit preview.mp4
```

Kein ATRAC9, keine Verschlüsselung auf Dateiebene. Das Audio steckt im `video.mp4` (eine Stereo-Spur, keine getrennte Gesangsspur).

## `.chc`

```
u32 version = 1 | u32 song_id | u32 offset = 20 | u32 packed_size | u32 raw_size | zlib(melody_1.xml)
```
Tool: `tools/chc.py pack|unpack`.
Offen: Das Beispiel enthält nur einen Song. Wie mehrere Songs in einer `.chc` aneinandergereiht werden, klärt erst ein Pack mit mehreren Songs.

## `melody_1.xml` → UltraStar

- `<MELODY Tempo="147.00" Resolution="Demisemiquaver">`: 1 Tick = 1/32-Note = 1/8 Viertel → `t = ticks * 60 / (BPM * 8)` s. UltraStar-`#BPM` zählt Viertelschläge × 4, also **US-BPM = SS-BPM × 2** bei 1 Tick = 1 US-Beat.
- Die Noten laufen sequenziell ohne Startzeiten; die Zeit ergibt sich aus der Summe der `Duration`-Werte. `MidiNote="0"` ist eine Pause. Die erste Pause ergibt `#GAP`.
- `MidiNote` ist absolut (MIDI); UltraStar-Pitch = MidiNote − 60.
- `Bonus="Yes"` → Goldene Note (`*`); `FreeStyle="Yes"` → `F`; `Rap="Yes"` → `R`/`G`.
- `<SENTENCE>` → Zeilenumbruch (`- <beat>`). `Singer="Solo 1|Solo 2|Group"` → Duett `P1`/`P2`/beide.
- Silbentrennung: `"moun -"` + `"tain"` → Leerzeichen und Bindestrich entfernen, dann aneinanderhängen; `"-"` allein = Haltesilbe (UltraStar `~`).
- Ignorierbar (Stimmerkennung/Mix): `MARKER_S`, `MARKER_N`, `POINT`, `ADRS`, `LABEL`.

## Disc-Pack (`Pack0.psarc`, Songs ohne PKG, ab 02.10.)

Der Disc-Song-Lader im eboot (aus der PS3-Fassung übernommen) sucht `<Präfix>Pack0.psarc`, `Pack1.psarc` … (`"%sPack%d%s"`, Funktion `0x7d8310`). Der GoldHEN-Spielpatch biegt den Präfix `/app0/` auf `/download0/` um (lea bei `0x7d8166`). Andere Präfixe (`/data/`, `/av_contents/…`) lädt Fios nicht.

- Archiv: **PSARC 1.4**, zlib, Blockgröße 64 KiB, Eintrag 0 = Manifest (Pfade, zeilengetrennt). Medien werden roh gespeichert, Text komprimiert (`tools/psarc.py`).
- Pfade im Archiv mit Präfix `filesystem/export/` (das funktionierende Layout; Wurzel-Layout ohne Präfix wurde nicht geladen):

```
filesystem/export/config.xml        VERSION 4 (höchste VERSION ≤ 5 wird genommen)
filesystem/export/songs_4_0.xml     SONG_SET im PS3-Format, PREV_VIDEO FOURCC="avc1"
filesystem/export/acts_4_0.xml      ACT_SET
filesystem/export/covers.xml        TPAGE_BIT je Song → textures/page_<id>.jpg (256×256)
filesystem/export/songlists_4.xml   SUBSETS, Carousel mit SONG_REF je Song
filesystem/export/filters.xml, credits.xml   aus der PS3-Bibliothek
filesystem/export/textures/page_<id>.jpg
filesystem/export/<id>/melody_4.xml, melody.xml, video.mp4, preview.mp4
```

- **Vorschau muss H.264 sein** (PS3-Vorschauen sind MPEG-4 Part 2 → Bild schwarz); `tools/ps4_discpack.py` wandelt nach 368×208 um. Video: H.264 wie bei den DLCs, Original-Auflösung geht.
- Disc-Songs stehen in der Song-DB unter `SB08<id>.0` (wie auf der PS3), Filter im Spiel: „Songs auf Disc“. Das Spiel gleicht bei jedem Start ab und entfernt nicht gefundene Disc-Songs.
- IDs: PS3-/PS4-ID des Songs; derselbe Song darf nicht zusätzlich als PKG installiert sein.

## `download0.dat` (Spielordner download0)

- Festes Image `/user/download/CUSA00033/download0.dat`, 1 GiB (`DOWNLOAD_DATA_SIZE 1024` in param.sfo und `app.db`; Ändern → „Daten defekt“). Daneben `download0_info.dat` = App-Version (`01.10`, 8 Byte).
- **Unverschlüsseltes UFS2** (little endian): Superblock bei `0x10000` (Magic `0x19540119` @ `0x55C`), bsize 32768, fsize 4096, 4 Zylindergruppen, ipg 16512, fpg 65544, iblkno 40, `fs_maxsymlinklen` 120 @ `0x528`. Inode-Offset = `(cg·fpg + iblkno)·fsize + (ino mod ipg)·256`, UFS2-Dinode 256 B (`di_db` ab `0x70`).
- Inhalt: `songdb/`, `song_covers/`, `<Benutzer-ID>/` (pinDB, songstatsdb), `DownloadQueue/`, `_bak*`, `Pack0.psarc` (Symlink auf `/av_contents/video/ss/Pack0.psarc`). Per FTP nur bei laufendem Spiel unter `/mnt/sandbox/CUSA00033_000/download0`; das Image selbst nur bei geschlossenem Spiel austauschen. Werkzeug: `tools/ufs_symlink.py`.
