# SingStar Song-Manager

Lokale Web-App zum Verwalten einer eigenen SingStar-Songsammlung für **PS4** (CUSA00033) und **PS3**. Sie führt alle Quellen am PC zusammen (UltraStar, PS3-Bibliothek, PS3- und PS2-Discs), baut daraus PS4-Pakete bzw. PS3-Fassungen, überträgt sie per FTP auf die Konsolen und zeigt, was wo installiert ist.

- **Start:** `start.bat` im Projektordner (Linux/macOS: `./start.sh`); richtet beim ersten Mal die Python-Umgebung ein und öffnet `http://127.0.0.1:5077`. Mit `--no-browser` öffnet sich kein Browser.
- **Voraussetzungen:** Python 3.12 mit Flask, ffmpeg, .NET (für PkgTool). Auf der PS4 GoldHEN mit FTP (Port 2121), auf der PS3 webMAN-FTP.
- **Einstellungen:** `manager/config.json` wird beim ersten Start angelegt (siehe `docs/SETUP.md`). Konsolen, Speicherorte, USDB-Zugang und Sprache stellt man in der App ein (`manager/data/settings.json`, Zugangsdaten in `secrets.json`).
- **Daten:** `manager/data/` (Verlauf, Entscheidungen, Wunschliste, Sicherungen), Konsolenstand in `manager/cache/`.

## Funktionen

### Bibliothek
- Alle Songs aus allen Quellen in einer Tabelle, zusammengeführt über die PS4-Song-ID. Quellen-Reihenfolge: UltraStar > PS3-Disc > PS3-Bibliothek > PS2.
- Spalten: Cover, Interpret, Titel, Edition, ID, Quelle, Paketgröße, wie oft gesungen; dazu je Konsole der Status (installiert / in `/data/pkg` / im Disc-Pack / vorgemerkt / fehlt).
- **Editionen:** Herkunft jedes Songs, z. B. „SingStar ABBA (Europe)“. Sie wird aus Toolbox-Exporten, Disc-Seriennummern (PS3 `keys.db`, PS2 `SYSTEM.CNF`) oder „UltraStar“ / „Eigener Song“ ermittelt.
- Suche, Sortierung und Filter: Quelle, Konsole, „nur auf Konsole“, Favoriten (irgendwo / auf allen / je Konsole), schon gesungen oder nie gesungen.
- Cover für jeden Song: UltraStar-Datei, Ausschnitt aus der Texturseite (PS3) oder PS2-Disc.

### Vorschau, Timing und Bearbeiten
- Vorschau im Browser mit mitlaufendem, wortgenauem Songtext: UltraStar (Audio + Video mit `#VIDEOGAP`) oder PS3-Fassung (`video.mp4` + `melody.xml`).
- Versatz-Regler mit „als #GAP übernehmen“.
- UltraStar-Songs bearbeiten: Interpret, Titel, Jahr, Genre, Sprache, GAP. Die alte `.txt` wird gesichert, die Song-ID bleibt.

### Baustellen und Dubletten
- Automatische Problemliste: kein Paket, Bau fehlgeschlagen, neuer Song, Ordner fehlt, kein Cover, Timing-Fehler (≥ 50 ms), Auflösung unter 400 px, Ton stark angehoben, Edition unbekannt, fehlerhafte Silbentrennung (Toolbox), USDB-Kommentare melden Probleme, GAP-Vorschlag, schlechte USDB-Bewertung, neue Version bei USDB.
- Dubletten (gleicher Interpret und Titel unter verschiedenen IDs) mit Entscheidung je Gruppe: „behalten“ oder „beide“.

### Pakete bauen
- „PS4-Pakete bauen“ für fehlende oder „neu bauen“ für ausgewählte Songs. Je Quelle läuft ein Konverter (UltraStar / PS3 / PS2), zwei parallel.
- Die alten Pakete wandern nach `pkgs_old/` und werden bei einem Fehler zurückgeholt.
- PS4-Pakete: 1080p, Lautheit −12 LUFS, Vorschau und Refrain automatisch, Duett-Aufteilung.
- PS3-Fassungen: max. 720p, −10 LUFS, Vorschau im PS3-Format. Wahlweise bleiben sie auf dem PC oder werden nach dem Übertragen gelöscht.

### Discs einlesen
- PS3-Discs (`.dec.iso` oder `.7z`) werden mit scee_london ausgepackt, PS2-Discs (`.iso` oder `.7z`) direkt gelesen. Schon eingelesene Discs werden übersprungen.
- Optional danach alle neuen Disc-Songs gleich als PS4-Paket bauen.

### Wunschliste und USDB
- Wunschliste mit USDB-Suche (Login nötig) und Download über den UltraStarWorker (Text, Cover, Audio/Video). Auf Wunsch wird danach gleich das PS4-Paket gebaut.
- USDB-Qualitätsinfos je Song: Bewertung, Stimmen, Songcheck, goldene Noten, Kommentare.
- **Update-Prüfung:** 1 min nach dem Start, dann alle 6 h oder per Knopf. Bei einer neuen USDB-Fassung erscheint „Neu von USDB laden“; die alte `.txt` wird gesichert und das Paket neu gebaut.

### Konsolen
- Beliebig viele PS4 und PS3 mit Name, IP, Port und an/aus. Sie werden alle 10 s überwacht und automatisch gelesen, sobald sie online sind.
- Änderungen an installierten Songs landen im **Verlauf**. Bei jeder Änderung werden `addcont.db` (PS4) bzw. `songs_4_0.xml` (PS3) gesichert.
- Freier Speicher, installierte Songs, Pakete in `/data/pkg`.
- Favoriten, Spielstatistik und Bestwerte werden von den Konsolen gelesen (Song-Datenbanken der Benutzer; PS4 nur bei laufendem SingStar).
- Songs, die nur auf einer Konsole liegen, werden erkannt und lassen sich mit „Auf den PC holen“ übernehmen. Offizielle, verschlüsselte PKGs werden nicht heruntergeladen.
- Wenn ein Ziel mehrdeutig ist, fragt ein Dialog mit Häkchen, welche Konsolen gemeint sind.

### PS4
- **Installationsart je PS4:**
  - **PKG:** Upload nach `/data/pkg`, installiert wird mit dem Paket-Installer von GoldHEN. Mit „Auf PS4 ersetzen“ wird ein installiertes Paket direkt überschrieben. Schon installierte Pakete lassen sich aus `/data/pkg` aufräumen.
  - **Disc-Pack (ohne PKG):** Alle gewählten Songs kommen in ein `Pack0.psarc` unter `/user/av_contents/video/ss/`. SingStars Disc-Song-Lader liest es über einen GoldHEN-Spielpatch und einen Verweis in `download0`. Es gibt kein Größenlimit; Änderungen werden vorgemerkt und automatisch übertragen, sobald die PS4 erreichbar ist. „Disc-Lader einrichten“ trägt den Patch ein und prüft Plugin und Verweis.
- **Fehlermeldung beim Start ausblenden:** Ein Schalter im Konsolen-Kasten trägt den GoldHEN-Patch „No online check error at startup“ ein und schaltet ihn ein oder aus. Danach erscheint „Ein Fehler ist aufgetreten (SU-41766-4)“ bzw. NW-31201-7 nicht mehr. Der Status (an / aus / nicht eingetragen) wird bei jedem Lesen der PS4 aktualisiert.

### PS3
- „Auf PS3 übertragen“: zuerst die Medien, dann `songs_4_0.xml`, `acts`, `covers` und `songlists` in einem Durchgang (Sicherung → Zusammenführen → Prüfung → Upload → Zurücklesen).
- „Auf PS3 ersetzen“, z. B. Toolbox-Songs mit kaputter Silbentrennung durch die UltraStar-Fassung.
- „PS3 prüfen“ mit SingStar Fixer (liest nur).

### Sonstiges
- Aufgabenliste mit Fortschritt, Protokoll und Abbrechen; Verlauf aller Änderungen.
- Speicherorte einstellbar. Den Ordner mit den PS4-Paketen kann man auf Wunsch samt Inhalt verschieben.
- Oberfläche auf Deutsch oder Englisch (`i18n.js`).

## Hinweise
- Alles, was auf eine Konsole schreibt, passiert erst nach einer Bestätigung.
- GoldHEN-Patches (Disc-Lader, Fehlermeldung) wirken erst nach einem Neustart von SingStar. GoldHEN muss vor SingStar gestartet sein, und in GoldHEN muss der Plugin-Lader eingeschaltet sein.
- Nach einer Änderung am Manager-Code muss der Server neu gestartet werden.
- Technische Details und Hintergründe: `docs/TECHNIK.md`, Dateiformate: `docs/FORMAT.md`.
