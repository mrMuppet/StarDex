/* English UI for the SingStar Song-Manager.
   The page is written in German; with LANG='en' every text node and the attributes placeholder/title/aria-label
   are translated when they appear (MutationObserver): 1. exact texts (EN), 2. texts with numbers/names (RULES),
   3. phrases inside composed texts (PHRASES). Song data (artists, titles, editions, comments) is never touched. */
const EN = {
  'SingStar Song-Manager': 'SingStar Song Manager',
  'Lesen': 'Read', 'liest …': 'reading …', 'PC neu einlesen': 'Rescan PC', 'Einstellungen': 'Settings',
  'Bibliothek': 'Library', 'Baustellen': 'Issues', 'Dubletten': 'Duplicates', 'Discs einlesen': 'Import discs',
  'Wunschliste': 'Wishlist', 'Konsolen & Verlauf': 'Consoles & history',
  'Songs gesamt': 'songs in total', 'Nicht eingetragen': 'Not listed', 'wartet auf die laufende Übertragung zu dieser PS3 …': 'waiting for the running transfer to this PS3 …', 'alle angezeigten Songs auswählen': 'select all songs shown', 'fertige ausblenden': 'hide finished', '▾ einklappen': '▾ collapse', '▴ aufklappen': '▴ expand',
  'Aufträge ein-/ausklappen': 'Collapse/expand tasks', '1 Auftrag läuft': '1 task running', 'PS3-Fassung': 'PS3 version',
  'aus dem fertigen PS4-Paket – beim ersten Abspielen wird es entpackt (einige Sekunden)': 'from the finished PS4 package – unpacked when first played (a few seconds)', 'Ausgewählte laden': 'Download selected', 'Erst Songs ankreuzen.': 'Tick some songs first.',
  'Häkchen bei Songs mit gemerktem USDB-Eintrag; geladen wird nacheinander in einem Auftrag.': 'Tick songs with a remembered USDB entry; they are downloaded one after the other in one task.',
  'wartet auf die laufende USDB-Aufgabe …': 'waiting for the running USDB task …', 'Vorgemerkt': 'Queued', 'Vorgemerkte übertragen': 'Transfer queued songs', 'Goldene Noten': 'Golden notes', 'Bewertung': 'Rating', 'Aufrufe': 'Views', 'Bibliothek': 'Library', 'vorhanden': 'present', 'Jahr': 'Year', 'danach auf:': 'then to:', '(Disc-Pack)': '(disc pack)', 'GAP speichern': 'Save GAP',
  '– der Regler steht immer auf dem gespeicherten Wert. Text zu früh → Regler nach rechts. Zum Probehören verschieben, dann „GAP speichern“.': '– the slider always starts at the saved value. Lyrics too early → move right. Move it to listen, then “Save GAP”.',
  'Gespeichert:': 'Saved:', 'Gesangstrennung': 'Vocal separation',
  'Für die Stimmreduzierung im Spiel (ADRS) wird beim Umwandeln die Stimme vom Playback getrennt (Demucs, je Song mehrere Minuten). PS2-Discs mit eigener Gesangsspur brauchen dafür keine Trennung. Gilt für neue PS4-Pakete und PS3-Fassungen; fertige Pakete bleiben, wie sie sind.':
    'For the in-game vocal reduction (ADRS) the voice is separated from the backing track during conversion (Demucs, several minutes per song). PS2 discs with their own vocal track need no separation. Applies to new PS4 packages and PS3 versions; finished packages stay as they are.',
  'an (Stimmreduzierung für alle Songs, langsam)': 'on (vocal reduction for all songs, slow)',
  'nur ohne Trennung (Stimmreduzierung nur für PS2-Songs mit eigener Gesangsspur)': 'only without separation (vocal reduction only for PS2 songs with their own vocal track)',
  'aus (keine Stimmreduzierung, am schnellsten)': 'off (no vocal reduction, fastest)', 'im Disc-Pack': 'in disc pack', 'vorgemerkt': 'queued', 'wird entfernt': 'being removed',
  'Installation': 'Installation', 'PKG (GoldHEN-Installer)': 'PKG (GoldHEN installer)', 'Disc-Pack (GoldHEN-Patch)': 'Disc pack (GoldHEN patch)',
  'Videos im Disc-Pack': 'Videos in the disc pack', 'Original': 'Original',
  'verkleinert (CRF 24, ca. 40–60 MB je Song)': 'downsized (CRF 24, approx. 40–60 MB per song)', 'stark verkleinert (CRF 28)': 'strongly downsized (CRF 28)',
  'Disc-Pack (ohne PKG)': 'Disc pack (without PKG)', 'Größe': 'Size', 'Zuletzt': 'Last', 'noch nie': 'never',
  'Disc-Lader einrichten (GoldHEN-Patch)': 'Set up disc loader (GoldHEN patch)', 'Disc-Pack jetzt übertragen': 'Transfer disc pack now',
  'Aus Disc-Pack entfernen': 'Remove from disc pack', 'Aus dem Disc-Pack entfernen?': 'Remove from the disc pack?',
  'Disc-Lader einrichten?': 'Set up the disc loader?', 'Disc-Lader': 'Disc loader', 'Einrichten': 'Set up', 'Nichts zu übertragen.': 'Nothing to transfer.',
  'Übertragen geht, sobald die PS4 erreichbar ist (SingStar muss nicht laufen); offene Änderungen werden dann automatisch übertragen. Danach SingStar neu starten.':
    'Transfers work as soon as the PS4 is reachable (SingStar need not run); open changes are then transferred automatically. Restart SingStar afterwards.',
  'Fehlermeldung beim Start': 'Error message at start', 'Fehlermeldung beim Start ausblenden': 'Hide the error message at start',
  'Fehlermeldung beim Start ausblenden?': 'Hide the error message at start?', 'Meldung wieder anzeigen': 'Show the message again', 'Ausblenden': 'Hide',
  'ausgeblendet (Patch an)': 'hidden (patch on)', 'Meldung erscheint (Patch aus)': 'message appears (patch off)',
  'Meldung erscheint (Patch nicht eingetragen)': 'message appears (patch not installed)', 'unbekannt – „Lesen“': 'unknown – “Read”', 'Status:': 'Status:',
  'SingStar zeigt beim Start „Ein Fehler ist aufgetreten (SU-41766-4)“ bzw. NW-31201-7 (PSN-Server abgeschaltet). Ein GoldHEN-Spielpatch blendet diese System-Fehlermeldungen aus; wirksam nach Neustart von SingStar.':
    'At start SingStar shows “An error has occurred (SU-41766-4)” or NW-31201-7 (PSN servers shut down). A GoldHEN game patch hides these system error messages; effective after restarting SingStar.',
  'Patch eingeschaltet – wirksam nach Neustart von SingStar': 'Patch switched on – effective after restarting SingStar',
  'Patch ausgeschaltet – wirksam nach Neustart von SingStar': 'Patch switched off – effective after restarting SingStar',
  'In GoldHEN muss der Plugin-Lader eingeschaltet sein; SingStar nach GoldHEN starten': 'The plugin loader must be enabled in GoldHEN; start SingStar after GoldHEN',
  'Patch eingetragen (CUSA00033.xml)': 'Patch added (CUSA00033.xml)', 'Patch war schon eingetragen': 'Patch was already there', 'Patch eingeschaltet': 'Patch switched on',
  'In GoldHEN muss der Plugin-Lader eingeschaltet sein (Meldung beim Start: „1 Patch Applied“)': 'The plugin loader must be switched on in GoldHEN (message at start: “1 Patch Applied”)', 'Alle Konsolen': 'All consoles', 'Konsolen': 'Consoles',
  '★ Favorit auf allen Konsolen': '★ Favourite on all consoles', 'wie oft gesungen (alle Konsolen)': 'times sung (all consoles)',
  'Keine Konsole eingerichtet – unter Einstellungen hinzufügen.': 'No console set up – add one in the settings.',
  'Keine Konsole eingerichtet. In den Einstellungen PS3 oder PS4 hinzufügen.': 'No console set up. Add a PS3 or PS4 in the settings.',
  'Keine Konsole eingerichtet.': 'No console set up.', '+ PS4': '+ PS4', '+ PS3': '+ PS3', 'Name': 'Name', 'Typ': 'Type',
  'IP': 'IP', 'aktiv': 'active', 'Ziel:': 'Target:',
  'Keine PS4 eingerichtet (Einstellungen).': 'No PS4 set up (settings).', 'Keine PS3 eingerichtet (Einstellungen).': 'No PS3 set up (settings).',
  'Beliebig viele PS3 und PS4 – oder nur eine Konsole. PS4: GoldHEN-FTP (Port 2121), PS3: webMAN-FTP (Port 21). Nicht aktive Konsolen werden weder überwacht noch angezeigt; ihre gelesenen Daten bleiben erhalten.':
    'Any number of PS3 and PS4 – or just one console. PS4: GoldHEN FTP (port 2121), PS3: webMAN FTP (port 21). Inactive consoles are neither watched nor shown; their data read so far is kept.', 'auf PS4 installiert': 'installed on PS4', 'wartet auf Installation': 'waiting for install',
  'fehlt auf PS4 (Paket fertig)': 'missing on PS4 (package ready)', 'auf PS3': 'on PS3', 'fehlt auf PS3': 'missing on PS3',
  'zum Entfernen markiert': 'marked for removal', 'ohne PS4-Paket': 'without PS4 package',
  'nur auf Konsole (nicht am PC)': 'only on a console (not on PC)', 'neu, nicht umgewandelt': 'new, not converted',
  'Alle Quellen': 'All sources', 'UltraStar': 'UltraStar', 'PS3-Disc (eingelesen)': 'PS3 disc (imported)',
  'PS3-Bibliothek': 'PS3 library', 'PS2-Disc': 'PS2 disc', 'Nur auf Konsole': 'Only on a console',
  'Neu (nicht umgewandelt)': 'New (not converted)', 'Alle Editionen': 'All editions',
  'PS4: alle': 'PS4: all', 'PS4: installiert': 'PS4: installed', 'PS4: wartet in /data/pkg': 'PS4: waiting in /data/pkg',
  'PS4: fehlt': 'PS4: missing', 'PS3: alle': 'PS3: all', 'PS3: vorhanden': 'PS3: present', 'PS3: fehlt': 'PS3: missing',
  'Alle Songs': 'All songs', '★ Favoriten (irgendwo)': '★ Favourites (anywhere)', '★ Favorit auf beiden': '★ Favourite on both',
  '★ nur PS4-Favorit': '★ PS4 favourite only', '★ nur PS3-Favorit': '★ PS3 favourite only',
  'schon gesungen': 'already sung', 'nie gesungen': 'never sung',
  'Interpret': 'Artist', 'Titel': 'Title', 'Edition': 'Edition', 'ID': 'ID', 'Quelle': 'Source', 'Paket': 'Package',
  'Gesungen': 'Sung', 'PS4': 'PS4', 'PS3': 'PS3', 'PS2': 'PS2', 'PS3-Disc': 'PS3 disc', 'PS4-Paket': 'PS4 package',
  'installiert': 'installed', 'wartet': 'waiting', 'fehlt': 'missing', 'vorhanden': 'present', 'kein Paket': 'no package',
  'neu': 'new', 'entfernen': 'remove', 'Dublette?': 'Duplicate?', 'nur PS4': 'PS4 only', 'nur PS3': 'PS3 only',
  'PS4-Pakete bauen': 'Build PS4 packages', 'Pakete neu bauen': 'Rebuild packages',
  'Auf PS4 hochladen (/data/pkg)': 'Upload to PS4 (/data/pkg)', 'Auf PS3 übertragen': 'Transfer to PS3',
  'Auf den PC holen': 'Copy to PC', 'Auswahl aufheben': 'Clear selection', 'abbrechen': 'cancel', 'ausblenden': 'hide',
  'fertig': 'done',
  'Alle Stufen': 'All levels', 'Fehler': 'Errors', 'Warnungen': 'Warnings', 'Hinweise': 'Notes',
  'Klick auf einen Song öffnet Details, Vorschau und Bearbeiten.': 'Click a song for details, preview and editing.',
  'Keine Baustellen 🎉': 'No issues 🎉',
  'Kein PS4-Paket': 'No PS4 package', 'Bau fehlgeschlagen': 'Build failed', 'Neu, noch nicht umgewandelt': 'New, not converted yet',
  'UltraStar-Ordner fehlt': 'UltraStar folder missing', 'Ohne Cover': 'No cover', 'Timing prüfen': 'Check timing',
  'Mögliche Dublette': 'Possible duplicate', 'Niedrige Auflösung': 'Low resolution',
  'Leise Quelle (stark angehoben)': 'Quiet source (strongly boosted)', 'Edition unbekannt': 'Edition unknown',
  'Silbentrennung fehlerhaft (PS3-Toolbox)': 'Broken syllables (PS3 Toolbox)', 'Neue Version bei USDB': 'New version on USDB',
  'Schlechte USDB-Bewertung': 'Poor USDB rating', 'USDB-Kommentare melden Probleme': 'USDB comments report problems',
  'USDB-Kommentar mit GAP-Vorschlag': 'USDB comment suggests a GAP', 'UltraStar-Song ohne Cover': 'UltraStar song without cover',
  'Neuer UltraStar-Song, noch nicht umgewandelt': 'New UltraStar song, not converted yet',
  'Neuer UltraStar-Song, noch nicht umgewandelt (Duett – Konverter unterstützt P1/P2 noch nicht)': 'New UltraStar song, not converted yet (duet – converter does not support P1/P2 yet)',
  'PS3-Fassung (Toolbox): Silbentrennung fehlerhaft, Songtext ohne Leerzeichen': 'PS3 version (Toolbox): broken syllables, lyrics without spaces',
  'Gleicher Interpret und Titel unter verschiedenen IDs. Wähle je Gruppe, welche Fassung bleibt. Nicht behaltene Fassungen werden überall als „entfernen“ markiert. Auf der PS4 löschst du sie im Spiel unter Einstellungen → Songs löschen.':
    'Same artist and title under different IDs. Choose per group which version stays. Versions not kept are marked “remove” everywhere. On the PS4 you delete them in the game under Settings → Delete songs.',
  'nur unentschiedene': 'undecided only', 'offen': 'open', 'beide behalten': 'keep both', 'entschieden': 'decided',
  'Beide behalten': 'Keep both', 'zurücksetzen': 'reset', 'ansehen': 'view', 'diese behalten': 'keep this one', 'bleibt': 'stays',
  'Keine offenen Dubletten.': 'No open duplicates.',
  'Abbild': 'Image', 'Größe': 'Size', 'Status': 'Status', 'schon eingelesen': 'already imported',
  'Ordner anzeigen': 'Show folder', 'suche …': 'searching …', 'Ausgewählte einlesen': 'Import selected',
  'danach PS4-Pakete für neue Songs bauen': 'then build PS4 packages for new songs',
  'PS3: ca. 5–10 min je Disc, PS2: ca. 1–3 min.': 'PS3: approx. 5–10 min per disc, PS2: approx. 1–3 min.',
  'Keine SingStar-Abbilder (.iso/.7z) in diesem Ordner.': 'No SingStar images (.iso/.7z) in this folder.',
  'PS3- und PS2-Abbilder (': 'Import PS3 and PS2 images (', 'oder': 'or',
  'mit ISO darin) in die Bibliothek einlesen. PS3 braucht': 'containing an ISO) into the library. PS3 needs',
  'entschlüsselte': 'decrypted', 'Abbilder (': 'images (',
  ', z. B. mit PS3 ISO Tools) – originale Redump-ISOs sind zusätzlich verschlüsselt. Ziel: die Ordner „Eingelesene PS3-Discs“ und „PS2-Discs“ unter Einstellungen → Speicherorte am PC.':
    ', e.g. with PS3 ISO Tools) – original Redump ISOs are additionally encrypted. Target: the folders “Imported PS3 discs” and “PS2 discs” under Settings → Storage folders on the PC.',
  'Notiz (optional)': 'Note (optional)', 'Auf die Wunschliste': 'Add to wishlist', 'Nur in USDB suchen': 'Search USDB only',
  'nach dem Laden gleich PS4-Paket bauen': 'build PS4 package after download', 'mit Video': 'with video',
  'Alle gemerkten USDB-Songs laden': 'Download all remembered USDB songs', 'Auf USDB-Updates prüfen': 'Check for USDB updates',
  'prüft …': 'checking …', 'USDB-Infos aktualisieren': 'Refresh USDB info',
  'Laden mit deinem UltraStarWorker (usdb_download.py) in den UltraStar-Ordner.': 'Downloads with your UltraStarWorker (usdb_download.py) into the UltraStar folder.',
  'Notiz': 'Note', 'USDB': 'USDB', 'in Bibliothek': 'in library', 'suchen': 'search', 'laden': 'download',
  'erneut laden': 'download again', 'merken': 'remember', 'öffnen': 'open', 'auf Wunschliste': 'add to wishlist',
  'Die Wunschliste ist leer. Oben Interpret und Titel eintragen.': 'The wishlist is empty. Enter artist and title above.',
  'Nichts gefunden.': 'Nothing found.', 'noch nie geprüft': 'never checked',
  'In den Einstellungen USDB-Name und Passwort eintragen.': 'Enter USDB name and password in the settings.',
  'Keine neuen USDB-Versionen.': 'No new USDB versions.',
  'Keine gemerkten USDB-Songs – erst suchen und „merken“.': 'No remembered USDB songs – search and “remember” first.',
  'Gelesen': 'Read', 'Installiert': 'Installed', 'In /data/pkg': 'In /data/pkg', 'Frei (/data)': 'Free (/data)', 'Frei': 'Free',
  'vom FTP-Server nicht gemeldet': 'not reported by the FTP server', 'nicht ermittelbar': 'not available',
  '/data/pkg aufräumen': 'Clean up /data/pkg', 'Nichts aufzuräumen.': 'Nothing to clean up.',
  'Song-Ordner': 'Song folders', 'Prüfen': 'Check', 'PS3 prüfen': 'Check PS3',
  'SingStar Fixer: prüft die Song-XMLs auf der PS3 (nur lesen, nichts wird geändert).': 'SingStar Fixer: checks the song XMLs on the PS3 (read only, nothing is changed).',
  'Noch nicht gelesen.': 'Not read yet.',
  'Noch nicht gelesen. PS4 einschalten, GoldHEN-FTP aktiv, dann „Lesen“ (oder automatisch, sobald sie online ist).': 'Not read yet. Switch on the PS4 with GoldHEN FTP, then “Read” (or automatically as soon as it is online).',
  'Aufgaben': 'Tasks', 'Verlauf': 'History', 'Keine Aufgaben in dieser Sitzung.': 'No tasks in this session.',
  'Noch kein Verlauf.': 'No history yet.', 'läuft': 'running',
  'Schließen': 'Close', 'Schließen (Esc)': 'Close (Esc)', 'Baustellen ': 'Issues ',
  'Vorschau & Timing': 'Preview & timing', 'PS3-Bibliothek ': 'PS3 library ', 'Versatz': 'Offset',
  'als #GAP übernehmen': 'apply as #GAP', 'Bearbeiten (UltraStar-Datei)': 'Edit (UltraStar file)', 'Jahr': 'Year',
  'Genre': 'Genre', 'Sprache': 'Language', 'Speichern': 'Save',
  'Änderungen gehen in die .txt (mit Sicherung). Danach „Neu bauen“.': 'Changes go into the .txt (with backup). Then “Rebuild”.',
  'Keine Änderung': 'No change', 'Aktionen': 'Actions', 'Auf PS4 hochladen': 'Upload to PS4', 'Auf PS4 ersetzen': 'Replace on PS4',
  'Auf PS3 ersetzen': 'Replace on PS3', 'Auf Wunschliste': 'Add to wishlist', 'auf der Wunschliste ✓': 'on the wishlist ✓',
  'Für eine bessere Fassung auf die Wunschliste': 'Add to the wishlist to find a better version',
  'Details': 'Details', 'PS4-ID / Label': 'PS4 ID / label', 'PS3-ID': 'PS3 ID', 'noch keine': 'none yet',
  'Gesungen & Favoriten': 'Sung & favourites', 'Favorit': 'Favourite', 'nein': 'no', 'ja': 'yes', 'noch nie': 'never',
  'Bestwert': 'Best score', 'Spieler': 'Player', 'Punkte': 'Score', 'Konsole': 'Console', 'Datum': 'Date',
  'Bewertung': 'Rating', 'Geprüft': 'Checked', 'Von': 'By', 'Kommentare': 'Comments', 'keine': 'none',
  'auf USDB öffnen': 'open on USDB', 'Neu von USDB laden + PS4-Paket neu bauen': 'Download again from USDB + rebuild PS4 package',
  'Songcheck ja': 'song check yes', 'kein Songcheck': 'no song check',
  'Abbrechen': 'Cancel', 'OK': 'OK', 'Bauen': 'Build', 'Hochladen': 'Upload', 'Übertragen': 'Transfer', 'Holen': 'Copy',
  'Ersetzen': 'Replace', 'Löschen': 'Delete', 'Übernehmen': 'Apply', 'Neu laden': 'Download again',
  'PS4 IP': 'PS4 IP', 'PS3 IP': 'PS3 IP', 'Port': 'Port', 'USDB-Name': 'USDB name', 'USDB-Passwort': 'USDB password',
  'unverändert lassen': 'leave unchanged', 'gespeichert – leer lassen = unverändert': 'saved – leave empty to keep',
  'Passwort': 'Password', 'Die USDB-Zugangsdaten bleiben lokal in': 'The USDB login stays local in',
  'und werden nur an usdb.animux.de geschickt.': 'and is only sent to usdb.animux.de.',
  'Speicherorte am PC': 'Storage folders on the PC', 'UltraStar-Songs': 'UltraStar songs', 'Eingelesene PS3-Discs': 'Imported PS3 discs',
  'PS2-Discs': 'PS2 discs', 'PS4-Pakete': 'PS4 packages', 'Von Konsolen übernommen': 'Copied from consoles',
  'vorhandene PS4-Pakete beim Ändern in den neuen Ordner verschieben': 'move existing PS4 packages to the new folder when changing',
  'PS3-Fassungen': 'PS3 versions', 'Verkleinerte PS3-Fassungen dauerhaft auf dem PC behalten': 'Keep downsized PS3 versions on the PC',
  'Ordner': 'Folder', 'Sprache / Language': 'Language / Sprache',
  'Die PS3 spielt höchstens 720p (1080p bleibt schwarz, getestet 30.09.). Songs mit größerem Video, z. B. 1080p-UltraStar, bekommen für die PS3 eine verkleinerte Fassung. Songs aus PS3-Quellen brauchen keine.':
    'The PS3 plays at most 720p (1080p stays black, tested 30 Sep). Songs with a larger video, e.g. 1080p UltraStar, get a downsized version for the PS3. Songs from PS3 sources need none.',
  'An: schneller beim erneuten Übertragen, braucht Speicherplatz. Aus: nach dem Übertragen auf die PS3 wieder löschen und bei Bedarf neu erzeugen.':
    'On: faster when transferring again, needs disk space. Off: delete after transferring to the PS3 and recreate when needed.',
  'Interpret, Titel, Edition oder ID …': 'Artist, title, edition or ID …', 'alle sichtbaren mit Paket auswählen': 'select all visible',
  'UltraStar-Ordner, PS3-Bibliothek, PS2 und Pakete neu einlesen': 'Rescan UltraStar folder, PS3 library, PS2 and packages',
  'wie oft gesungen (PS3+PS4)': 'times sung (PS3+PS4)', 'Konsole ist nicht erreichbar': 'Console not reachable',
  'Toolbox-Export (FileSystem/Export)': 'Toolbox export (FileSystem/Export)', 'Songs, die nur auf PS3/PS4 waren': 'Songs that were only on PS3/PS4',
  'Bewertung, Songcheck und Kommentare für alle UltraStar-Songs von USDB holen': 'Fetch rating, song check and comments for all UltraStar songs from USDB',
  'Manager-Server nicht erreichbar – start.bat neu starten': 'Manager server not reachable – restart start.bat',
  'Zeitüberschreitung': 'Timeout', 'Die Konsole ist gerade nicht erreichbar.': 'The console is not reachable right now.',
  'PS3 ist gerade nicht erreichbar.': 'The PS3 is not reachable right now.', 'Hinweis: PS4 wurde noch nicht gelesen.': 'Note: the PS4 has not been read yet.',
  'Knapp!': 'Tight!', 'SingStar danach neu starten.': 'Restart SingStar afterwards.',
  'Die Songlisten der PS3 werden vorher gesichert, nach dem Ändern geprüft und zurückgelesen.': 'The PS3 song lists are backed up first, checked after the change and read back.',
  'Auf der PS4 ersetzen?': 'Replace on the PS4?', 'SingStar muss geschlossen sein.': 'SingStar must be closed.',
  'Neue USDB-Fassung laden?': 'Download the new USDB version?', '#GAP ändern?': 'Change #GAP?',
  'Umwandeln': 'Convert', 'Neu bauen': 'Rebuild', 'PS4-Paket bauen': 'Build PS4 package', 'gerade eben': 'just now',
  'nicht gelesen': 'not read', 'offline': 'offline', 'English': 'English', 'German': 'German',
  'Nicht übersetzt': 'Not translated', 'Gespeichert: ': 'Saved: ', 'nicht geeignet': 'not suitable',
  'enthält batch/, batch_ps3/, batch_ps3disc/, batch_ps2/': 'contains batch/, batch_ps3/, batch_ps3disc/, batch_ps2/',
  'kopiert': 'copied', 'kodiert': 'encoded',
};
const RULES = [
  [/^(.+ GB) nach$/, '$1 to'],
  [/^zuletzt vor (.+) \(automatisch alle (\d+) h\)$/, (m, a, b) => `last ${tr('vor ' + a)} (automatically every ${b} h)`],
  [/^(.*?)nur auf der (PS\d) \(ID (.+)\), nicht in der PC-Bibliothek\.$/, '$1only on the $2 (ID $3), not in the PC library.'],
  [/^(.*?)nur auf (.+?) \(ID (.+)\), nicht in der PC-Bibliothek\.$/, '$1only on $2 (ID $3), not in the PC library.'],
  [/^(.+): installiert$/, '$1: installed'],
  [/^(\d+) Songs liegen auf der PS3, fehlen aber in der Songliste.*$/, '$1 songs are on the PS3 but missing in the song list – SingStar does not show them (a transfer broke off). Entering them skips files that are there already, so it is quick.'],
  [/^(\d+) Songs eintragen$/, 'Enter $1 songs'],
  [/^(.+): (\d+) Song-Ordner ohne Eintrag in der Songliste .*$/, '$1: $2 song folders without an entry in the song list (transfer broke off) – “Consoles & history” → “Enter”'],
  [/^(\d+) neue Songs warten auf die Übertragung\. .*$/, '$1 new songs are waiting to be transferred. The PS3 is never written or read automatically (it disturbs SingStar) – transfer while nobody is singing.'],
  [/^(.+): (\d+) neue Songs vorgemerkt \((.*)\) – übertragen über .*$/, '$1: $2 new songs queued ($3) – transfer via “Consoles & history” → “Transfer queued songs”'],
  [/^(.+): (\d+) neue Songs vorgemerkt \((.*)\) – werden übertragen, sobald die Konsole online ist$/, '$1: $2 new songs queued ($3) – transferred as soon as the console is online'],
  [/^(.+): (\d+) neue Songs fürs Disc-Pack vorgemerkt \((.*)\)$/, '$1: $2 new songs queued for the disc pack ($3)'],
  [/^(.+) ist online: (\d+) vorgemerkte Songs werden übertragen$/, '$1 is online: transferring $2 queued songs'], [/^(.+): im Disc-Pack$/, '$1: in disc pack'], [/^(.+): vorgemerkt$/, '$1: queued'],
  [/^(.+): vorgemerkt – wird übertragen, sobald die PS4 erreichbar ist$/, '$1: queued – will be transferred as soon as the PS4 is reachable'],
  [/^ · Disc-Pack (\d+) Songs( \(Änderungen offen\))?$/, (m, a, b) => ` · disc pack ${a} songs${b ? ' (changes open)' : ''}`],
  [/^(\d+) übertragen$/, '$1 transferred'], [/^, Änderungen offen \((\d+) gewünscht\)$/, ', changes open ($1 wanted)'],
  [/^(.+): Disc-Pack mit (\d+) Songs übertragen$/, '$1: transfer disc pack with $2 songs'],
  [/^(.+): Disc-Pack mit (\d+) Songs übertragen \((.+)\) – SingStar neu starten$/, '$1: disc pack with $2 songs transferred ($3) – restart SingStar'],
  [/^(\d+) Songs im Disc-Pack \((.+)\) – SingStar neu starten$/, '$1 songs in the disc pack ($2) – restart SingStar'],
  [/^(.+): vorgemerkte Disc-Pack-Änderungen werden übertragen$/, '$1: queued disc pack changes are being transferred'],
  [/^(.+): Disc-Lader eingerichtet – (.+)$/, '$1: disc loader set up – $2'],
  [/^(.+): Fehlermeldung beim Start ausgeblendet \(Patch an\)$/, '$1: error message at start hidden (patch on)'],
  [/^(.+): Fehlermeldung beim Start wieder eingeschaltet \(Patch aus\)$/, '$1: error message at start shown again (patch off)'],
  [/^Vorherige CUSA00033\.xml gesichert \((.+)\)$/, 'Previous CUSA00033.xml saved ($1)'],
  [/^ältere Variante ausgeschaltet: (.+)$/, 'older variant switched off: $1'], [/^(.+): vorhanden$/, '$1: present'], [/^(.+): fehlt$/, '$1: missing'],
  [/^(.+): fehlt \(Paket fertig\)$/, '$1: missing (package ready)'], [/^(.+): wartet auf Installation$/, '$1: waiting for install'],
  [/^(.+): wartet in \/data\/pkg$/, '$1: waiting in /data/pkg'], [/^★ Favorit auf (.+)$/, '★ Favourite on $1'],
  [/^nur auf (.+)$/, 'only on $1'], [/^Frei auf (.+): (.+) \(Installation braucht kurzzeitig doppelt so viel\)\.$/, 'Free on $1: $2 (installing briefly needs twice as much).'],
  [/^Gerade nicht erreichbar: (.+)$/, 'Not reachable right now: $1'], [/^(.+) nicht erreichbar: (.+)$/, '$1 not reachable: $2'],
  [/^(.+): Diese Pakete liegen in$/, '$1: These packages are in'],
  [/^(\d+) Songs auf (.+) übertragen$/, 'Transfer $1 songs to $2'], [/^(.+) auf (.+) ersetzen$/, 'Replace $1 on $2'],
  [/^(\d+) Songs von (.+) auf den PC holen$/, 'Copy $1 songs from $2 to the PC'], [/^(\d+) Pakete von (.+) auf den PC holen$/, 'Copy $1 packages from $2 to the PC'],
  [/^(\d+) Songs von (.+) auf den PC geholt$/, '$1 songs copied from $2 to the PC'],
  [/^(\d+) Pakete von (.+) auf den PC geholt(.*)$/, (m, a, b, c) => `${a} packages copied from ${b} to the PC${c.replace('nicht möglich', 'not possible')}`],
  [/^(.+): Prüfung \(SingStar Fixer, nur lesen\)$/, '$1: check (SingStar Fixer, read only)'], [/^(.+): Prüfung beendet \(Code (.+)\)$/, '$1: check finished (code $2)'],
  [/^(.+): Favoriten\/Statistik nicht lesbar: (.+)$/, '$1: favourites/statistics not readable: $2'],
  [/^(\d+) installierte Pakete aus (.+) \/data\/pkg gelöscht$/, '$1 installed packages deleted from $2 /data/pkg'],
  [/^(\d+) neue Songs von der Disc bauen: (\d+) ok, (\d+) Fehler$/, 'Build $1 new songs from the disc: $2 ok, $3 errors'],
  [/^(\d+) Songs$/, '$1 songs'],
  [/^(?:(\d+) Aufträge laufen|1 Auftrag läuft)?(?: · )?(?:(\d+) fertig)?(?: · )?(?:(\d+) mit Fehler)?$/, (m, a, b, c) => [m.startsWith('1 Auftrag') ? '1 task running' : a && `${a} tasks running`, b && `${b} done`, c && `${c} with errors`].filter(Boolean).join(' · ')], [/^Ausgewählte laden \((\d+)\)$/, 'Download selected ($1)'], [/^(\d+) Treffer$/, '$1 results'],
  [/^Baustellen \((\d+)\)$/, 'Issues ($1)'], [/^Dubletten \((\d+)\)$/, 'Duplicates ($1)'],
  [/^(\d+) ausgewählt · (\d+) mit Paket \(([\d.,]+ GB)\)(?: · (\d+) ohne Paket)?$/, (m, a, b, c, d) => `${a} selected · ${b} with package (${c})${d ? ` · ${d} without package` : ''}`],
  [/^(\d+) PS4-Pakete bauen$/, 'Build $1 PS4 packages'], [/^(\d+) auf PS3 übertragen$/, 'Transfer $1 to PS3'],
  [/^(\d+) auf den PC holen$/, 'Copy $1 to PC'],
  [/^(\d+) PS4-Pakete (neu )?bauen\?$/, (m, a, b) => `${b ? 'Rebuild' : 'Build'} ${a} PS4 packages?`],
  [/^(\d+) Pakete auf die PS4 hochladen\?$/, 'Upload $1 packages to the PS4?'],
  [/^(\d+) Songs auf die PS3 übertragen\?$/, 'Transfer $1 songs to the PS3?'], [/^(\d+) Songs auf den PC holen\?$/, 'Copy $1 songs to the PC?'],
  [/^(\d+) Pakete löschen\?$/, 'Delete $1 packages?'], [/^(\d+) installierte Pakete aus \/data\/pkg löschen$/, 'Delete $1 installed packages from /data/pkg'],
  [/^(\d+) Pakete in \/data\/pkg sind schon installiert und können gelöscht werden\.$/, '$1 packages in /data/pkg are already installed and can be deleted.'],
  [/^Neu bauen \((.+)\)$/, 'Rebuild ($1)'], [/^Umwandeln \((.+)\)$/, 'Convert ($1)'], [/^PS4-Paket bauen \((.+)\)$/, 'Build PS4 package ($1)'],
  [/^Quelle (.+)$/, 'Source $1'], [/^Paket (.+)$/, 'Package $1'],
  [/^Mögliche Dublette von ID (.+)$/, 'Possible duplicate of ID $1'], [/^Video nur (\d+)×(\d+)$/, 'Video only $1×$2'],
  [/^Ton um ([+\-\d.]+) dB angehoben \(leise Quelle\)$/, 'Audio raised by $1 dB (quiet source)'],
  [/^Timing-Rundungsfehler (.+) \(GAP prüfen\)$/, 'Timing rounding error $1 (check GAP)'],
  [/^Kein PS4-Paket: (.+)$/, 'No PS4 package: $1'], [/^Letzter Bau fehlgeschlagen: (.+)$/, 'Last build failed: $1'],
  [/^Neue Version bei USDB vom (.+) – im Detailfenster „Neu von USDB laden“$/, 'New version on USDB from $1 – use “Download again from USDB” in the details'],
  [/^USDB-Bewertung nur (.+) Sterne \((\d+) Stimmen\)$/, 'USDB rating only $1 stars ($2 votes)'],
  [/^USDB-Kommentare melden Probleme \((\d+)\): (.*)$/s, 'USDB comments report problems ($1): $2'],
  [/^USDB-Kommentar nennt anderen GAP: (.+) – im Timing-Regler prüfen$/, 'USDB comment suggests another GAP: $1 – try it with the timing slider'],
  [/^PS3-Fassung \(Toolbox\): Silbentrennung fehlerhaft, Songtext ohne Leerzeichen – mit „Auf PS3 ersetzen“ aus UltraStar neu übertragen$/, 'PS3 version (Toolbox): broken syllables, lyrics without spaces – transfer again from UltraStar with “Replace on PS3”'],
  [/^• (.+)$/, (m, a) => '• ' + tr(a)],
  [/^(.+) – (\d+) Sterne, (\d+) Stimmen$/, '$1 – $2 stars, $3 votes'],
  [/^USDB: ([\d.]+) Sterne, (\d+) Stimmen(, geprüft)?$/, (m, a, b, c) => `USDB: ${a} stars, ${b} votes${c ? ', checked' : ''}`],
  [/^Favorit auf (.+)$/, (m, a) => 'Favourite on ' + a.replace(' + ', ' + ')],
  [/^(\d+)× \(PS3 (\d+), PS4 (\d+)\) · zuletzt (.+)$/, '$1× (PS3 $2, PS4 $3) · last $4'],
  [/^(\d+)× \((.*)\) · zuletzt (.+)$/, '$1× ($2) · last $3'],
  [/^zuletzt (.+?)( · Bestwert (.+))?$/, (m, a, b, c) => `last ${a}${b ? ' · best ' + c : ''}`],
  [/^(.+) Punkte · (.*) \((.+), (.+)\)$/, '$1 points · $2 ($3, $4)'],
  [/^(\d+) \((\d+) Stimmen\) · (\d+) Aufrufe$/, '$1 ($2 votes) · $3 views'],
  [/^zuletzt vor (.+) \(automatisch alle (\d+) h\)$/, (m, a, b) => `last ${tr('vor ' + a)} (automatically every ${b} h)`],
  [/^vor (\d+) min$/, '$1 min ago'], [/^vor (\d+) h$/, '$1 h ago'],
  [/^Gespeichert: (\d+) Songs, (.+)$/, 'Saved: $1 songs, $2'],
  [/^✓ GAP gespeichert: (-?\d+) → (-?\d+) ms\. .*$/, '✓ GAP saved: $1 → $2 ms. To take effect in the game: rebuild and replace the PS4 package or PS3 version.'],
  [/^GAP jetzt (-?\d+) ms\. Text zu früh → Regler nach rechts\.$/, 'GAP now $1 ms. Lyrics too early → move the slider right.'],
  [/^nur auf der (PS\d) \(ID (.+)\), nicht in der PC-Bibliothek\.$/, 'only on the $1 (ID $2), not in the PC library.'],
  [/^(.+) Song\(s\) haben eine neue USDB-Version \(siehe Baustellen\)$/, '$1 song(s) have a new USDB version (see issues)'],
  [/^PS4-Pakete liegen jetzt in (.+)\. Laufwerk C: ist fast voll – z\. B\. (.+) wählen\.$/, 'PS4 packages are now in $1. Drive C: is almost full – choose e.g. $2.'],
  [/^(\d+) Songs von USDB laden$/, 'Download $1 songs from USDB'], [/^USDB-Song (\d+) laden$/, 'Download USDB song $1'],
  [/^(\d+) PS4-Pakete bauen$/, 'Build $1 PS4 packages'],
  [/^(\d+) Pakete → (.+) \/data\/pkg$/, '$1 packages → $2 /data/pkg'],
  [/^(\d+) Songs auf die PS3 übertragen$/, 'Transfer $1 songs to the PS3'], [/^(.+) auf die PS3$/, '$1 to the PS3'],
  [/^(\d+) Songs von der PS3 auf den PC holen$/, 'Copy $1 songs from the PS3 to the PC'],
  [/^(\d+) Pakete von der PS4 auf den PC holen$/, 'Copy $1 packages from the PS4 to the PC'],
  [/^USDB-Infos holen$/, 'Fetch USDB info'],
  [/^(\d+) neue Songs von der Disc bauen$/, 'Build $1 new songs from the disc'],
  [/^(\d+) neue USDB-Songs als PS4-Paket bauen$/, 'Build $1 new USDB songs as PS4 packages'],
  [/^(\d+) Fehler: (.*)$/s, '$1 errors: $2'],
  [/^(.+) automatisch gelesen \(online\)$/, '$1 read automatically (online)'],
  [/^(.+) ist online$/, '$1 is online'], [/^(.+) ist nicht mehr erreichbar$/, '$1 is not reachable anymore'],
  [/^(PS\d) (.+) gesichert \((.+)\)$/, '$1 $2 backed up ($3)'], [/^(.+): (.+) gesichert \((.+)\)$/, '$1: $2 backed up ($3)'],
  [/^(.+): (\d+) (Songs|Song-Ordner) hinzugekommen, (\d+) entfernt$/, (m, a, b, c, d) => `${a}: ${b} ${c === 'Songs' ? 'songs' : 'song folders'} added, ${d} removed`],
  [/^(.+): (\d+) Song\(s\) nur auf der Konsole, nicht am PC – .*$/, '$1: $2 song(s) only on the console, not on the PC – “Only on a console” → “Copy to PC” in the library'],
  [/^(\d+) Pakete nach (.+) \/data\/pkg hochgeladen(.*)$/, (m, a, b, c) => `${a} packages uploaded to ${b} /data/pkg${c.replace('Fehler', 'errors')}`],
  [/^(\d+) Songs auf die PS3 übertragen \(SingStar neu starten\)$/, '$1 songs transferred to the PS3 (restart SingStar)'],
  [/^(\d+) Songs auf (.+) übertragen \(SingStar neu starten\)$/, '$1 songs transferred to $2 (restart SingStar)'],
  [/^(.+): (.+) – (.+) ersetzt \((.+)\)$/, '$1: $2 – $3 replaced ($4)'],
  [/^(\d+) Songs von USDB geladen(.*)$/, (m, a, b) => `${a} songs downloaded from USDB${b.replace('Fehler', 'errors')}`],
  [/^USDB-Infos für (\d+) Songs geholt(.*)$/, (m, a, b) => `USDB info fetched for ${a} songs${b.replace('Fehler', 'errors')}`],
  [/^(\d+) Song\(s\) bei USDB aktualisiert – .*$/, '$1 song(s) updated on USDB – see issues “New version on USDB” → download again'],
  [/^(PS\d)-Disc eingelesen: (.+)$/, '$1 disc imported: $2'], [/^(.+): (\d+) ok, (\d+) Fehler$/, (m, a, b, c) => `${tr(a)}: ${b} ok, ${c} errors`],
  [/^(.+): (.+) – neuer Versuch$/, '$1: $2 – retrying'], [/^nur (PS\d)$/, '$1 only'], [/^neu: (.+)$/, 'new: $1'], [/^weg: (.+)$/, 'gone: $1'],
  [/^Verbleibend: (.+)$/, 'Remaining: $1'],
  [/^(.+) einlesen$/, 'Import $1'], [/^(.+) bauen$/, 'Build $1'],   // generic, keep last
];
const PHRASES = [
  ['offline · Stand ', 'offline · as of '], ['offline · ', 'offline · '], [' installiert', ' installed'], [' in /data/pkg', ' in /data/pkg'],
  [' · frei ', ' · free '], ['nicht gelesen', 'not read'], ['gerade eben', 'just now'], [' Songs', ' songs'],
  ['ausgewählt', 'selected'], ['Favorit auf ', 'Favourite on '], [' und ', ' and '],
  ['PS3 und PS4', 'PS3 and PS4'], ['PS4 und PS3', 'PS4 and PS3'], ['Abbild(er)', 'image(s)'],
  ['Die Konverter laufen im Hintergrund (je Song ca. ', 'The converters run in the background (approx. '],
  [' Minuten, 2 parallel).', ' minutes per song, 2 in parallel).'], ['Vorhandene Pakete werden nach', 'Existing packages are moved to'],
  ['verschoben. Quelle je Song: UltraStar vor PS3-Disc vor PS3-Bibliothek vor PS2.', '. Source per song: UltraStar before PS3 disc before PS3 library before PS2.'],
  ['Quelle je Song: UltraStar vor PS3-Disc vor PS3-Bibliothek vor PS2.', 'Source per song: UltraStar before PS3 disc before PS3 library before PS2.'],
  [' nach ', ' to '], [', mit vollem Dateinamen. Danach im GoldHEN-Menü mit dem Paket-Installer alle installieren.', ', with full file names. Then install them all with the package installer in the GoldHEN menu.'],
  ['Frei auf der PS4: ', 'Free on the PS4: '], [' (Installation braucht kurzzeitig doppelt so viel).', ' (installing briefly needs twice as much).'],
  ['davon sind schon installiert. Zum Austauschen stattdessen in den Details „Auf PS4 ersetzen“.', 'of them are already installed. To exchange them use “Replace on PS4” in the details instead.'],
  ['davon sind als Dublette zum Entfernen markiert.', 'of them are marked for removal as duplicates.'],
  ['Quelle: ', 'Source: '], [' UltraStar (720p neu erzeugt), ', ' UltraStar (re-created in 720p), '],
  [' PS3-Disc (unverändert), ', ' PS3 disc (unchanged), '], [' PS2 (neu erzeugt).', ' PS2 (re-created).'],
  ['ausgewählte Songs haben keine passende Quelle und werden übersprungen.', 'selected songs have no suitable source and are skipped.'],
  ['davon sind schon auf der PS3 und werden ersetzt (z. B. alte Toolbox-Fassungen).', 'of them are already on the PS3 and will be replaced (e.g. old Toolbox versions).'],
  ['Das alte Paket wird nach', 'The old package is moved to'], ['verschoben. Dauert je nach Song 1–5 Minuten.', '. Takes 1–5 minutes depending on the song.'],
  [' aus der Quelle ', ' from source '], ['Das installierte Paket', 'The installed package'],
  ['wird mit dem aktuellen Paket vom PC überschrieben', 'is overwritten with the current package from the PC'],
  ['Die .txt wird gesichert und geändert, danach das Paket neu bauen.', 'The .txt is backed up and changed, then rebuild the package.'],
  ['Text, Audio, Video und Cover werden neu geladen, danach wird das PS4-Paket neu gebaut. Die bisherige .txt wird vorher gesichert (eigene GAP- oder Textänderungen gehen sonst verloren). Auf PS4/PS3 danach mit „ersetzen“ austauschen.',
   'Text, audio, video and cover are downloaded again, then the PS4 package is rebuilt. The current .txt is backed up first (own GAP or text changes would be lost otherwise). Afterwards exchange on PS4/PS3 with “replace”.'],
  ['Diese Pakete liegen in', 'These packages are in'], ['und sind laut PS4 schon installiert. Die installierten Songs bleiben erhalten.', 'and are already installed according to the PS4. The installed songs stay.'],
  ['Video, Melodie, Vorschau, Cover, Songlisten-Eintrag', 'video, melody, preview, cover, song list entry'],
  ['Offizielle Sony-Pakete sind verschlüsselt und lassen sich nicht übernehmen – nur eigene/fremde fPKGs.', 'Official Sony packages are encrypted and cannot be copied – only own/other fPKGs.'],
  ['Ziel: Ordner „Von Konsolen übernommen“ (Einstellungen). Danach sind es normale Quellen, z. B. für PS4-Pakete bzw. die PS3.', 'Target: folder “Copied from consoles” (settings). Afterwards they are normal sources, e.g. for PS4 packages or the PS3.'],
  ['Neue Version bei USDB', 'New version on USDB'], [' vom ', ' from '], ['deine Fassung: ', 'your version: '],
  ['Gespeichert: ', 'Saved: '], ['Bewertung', 'Rating'], [' Stimmen', ' votes'], [' Aufrufe', ' views'], ['goldene Noten', 'golden notes'],
  ['Songcheck ja', 'song check yes'], ['kein Songcheck', 'no song check'], [' · goldene Noten ja', ' · golden notes yes'],
  [' · goldene Noten nein', ' · golden notes no'], [' Punkte', ' points'], ['zuletzt', 'last'],
  ['Englisch', 'English'], ['Deutsch', 'German'], ['frei ', 'free '],
];
PHRASES.sort((a, b) => b[0].length - a[0].length);
let LANG = 'de';
try { LANG = localStorage.getItem('ssm-lang') || 'de'; } catch (e) { /* storage unavailable */ }
const LOC = () => LANG === 'en' ? 'en-GB' : 'de';
const DATA_TEXTS = new Set();   // artists/titles/editions: never translated
function tr(t) {
  if (LANG !== 'en' || !t) return t;
  if (t.includes('\n') && t.trim().includes('\n')) return t.split('\n').map(tr).join('\n');
  const k = t.trim();
  if (!k || DATA_TEXTS.has(k) || /^[A-Z]:[\\/]/.test(k)) return t;
  if (Object.prototype.hasOwnProperty.call(EN, k)) return t.replace(k, EN[k]);
  for (const [re, rep] of RULES) if (re.test(k)) return t.replace(k, k.replace(re, rep));
  let out = k;
  for (const [de, en] of PHRASES) if (out.includes(de)) out = out.split(de).join(en);
  out = out.replace(/\bvor (\d+) min\b/g, '$1 min ago').replace(/\bvor (\d+) h\b/g, '$1 h ago');
  return out === k ? t : t.replace(k, out);
}
let _translating = false;
const _done = new WeakMap();   // node -> text we set (never translate our own output again)
function translateTree(root) {
  if (LANG !== 'en' || _translating) return;
  _translating = true;
  try {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const p = n.parentElement;
      if (!p || p.closest('script,style,[data-notr],.lyr,pre.log')) continue;
      if (_done.get(n) === n.nodeValue) continue;
      const v = tr(n.nodeValue);
      if (v !== n.nodeValue) n.nodeValue = v;
      _done.set(n, n.nodeValue);
    }
    const els = root.querySelectorAll ? root.querySelectorAll('[placeholder],[title],[aria-label]') : [];
    for (const e of els) for (const a of ['placeholder', 'title', 'aria-label']) {
      const v = e.getAttribute(a);
      if (!v || (_done.get(e) || {})[a] === v) continue;
      const t = tr(v);
      if (t !== v) e.setAttribute(a, t);
      _done.set(e, { ...(_done.get(e) || {}), [a]: t });
    }
  } finally { _translating = false; }
}
function startI18n() {
  document.documentElement.lang = LANG;
  if (LANG !== 'en') return;
  translateTree(document.body);
  new MutationObserver(ms => {
    if (_translating) return;
    for (const m of ms) {
      if (m.type === 'characterData') translateTree(m.target.parentNode || document.body);
      else if (m.type === 'attributes') translateTree(m.target.parentNode || document.body);
      else m.addedNodes.forEach(n => translateTree(n.nodeType === 3 ? n.parentNode : n));
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true,
                               attributeFilter: ['placeholder', 'title', 'aria-label'] });
}
