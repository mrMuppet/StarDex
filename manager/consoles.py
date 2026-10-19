"""FTP access to the consoles.

PS4 (GoldHEN FTP): installed songs = folders /user/addcont/CUSA00033/<LABEL>/ (label -> song id),
waiting packages = /data/pkg/*.pkg. PS3 (webMAN/multiMAN FTP): /dev_hdd0/FileSystem/Export/<ps3 id>/ + songs_4_0.xml.
Scans only read. Writes (each confirmed in the UI and logged in data/history.jsonl):
upload to PS4 /data/pkg, replace an installed ac.pkg (game closed), delete installed leftovers from /data/pkg.
Scan results are cached in manager/cache/ so the last known state stays visible while a console is off;
addcont.db (PS4) and songs_4_0.xml (PS3) are backed up to data/backups/ whenever they change.

Any number of consoles (cfg["consoles"]: [{id, type "ps4"|"ps3", name, host, port, enabled}], edited in the settings).
The console id names the cache (cache/<id>.json), backups and user data; the first PS4/PS3 keep the ids "ps4"/"ps3"
from the time when there was exactly one of each.
"""
import ftplib
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import library
import local_config  # noqa: E402  (tools/, on sys.path via library)
import store

CACHE = Path(__file__).parent / "cache"
BACKUPS = store.DATA / "backups"
PS4_ADDCONT = "/user/addcont/CUSA00033"
PS4_PKG = "/data/pkg"
PS4_ADDCONT_DB = "/system_data/priv/mms/addcont.db"
PS3_EXPORT = "/dev_hdd0/FileSystem/Export"
FIXER = local_config.path("singstar_fixer")  # optional: SingStar Fixer (singstar_fixer.py)

TYPES = ("ps4", "ps3")
DEFAULT_PORT = {"ps4": 2121, "ps3": 21}
online: dict[str, bool] = {}
on_scan = []  # callbacks(console id) after a successful scan (app: report songs that are only on a console)
checked: dict[str, float] = {}  # time of the last reachability check
on_tick = []  # callbacks(console id) on every monitor round while a console is online (app: pending disc pack)


def all_consoles(cfg: dict) -> list[dict]:
    return cfg.get("consoles") or []


def active(cfg: dict, kind: str | None = None) -> list[dict]:
    """Enabled consoles, optionally of one type."""
    return [c for c in all_consoles(cfg) if c.get("enabled", True) and (kind is None or c["type"] == kind)]


def get(cfg: dict, cid: str) -> dict:
    for c in all_consoles(cfg):
        if c["id"] == cid:
            return c
    raise KeyError(f"Konsole {cid} ist nicht eingerichtet")


def name(cfg: dict, cid: str) -> str:
    try:
        return get(cfg, cid)["name"]
    except KeyError:
        return cid.upper()


def migrate(cfg: dict, settings: dict) -> list[dict]:
    """Console list from the settings; older settings had exactly one "ps4" and one "ps3" entry."""
    if isinstance(settings.get("consoles"), list):
        return settings["consoles"]
    out = []
    for t in TYPES:
        c = {**cfg.get(t, {}), **settings.get(t, {})}
        if c.get("host"):
            out.append({"id": t, "type": t, "name": t.upper(), "host": c["host"],
                        "port": int(c.get("port") or DEFAULT_PORT[t]), "enabled": True})
    return out


def connect(c: dict, timeout: float = 8) -> ftplib.FTP:
    f = ftplib.FTP()
    f.connect(c["host"], c["port"], timeout=timeout)
    f.login()
    f.voidcmd("TYPE I")
    return f


class RetryFtp:
    """FTP session that reconnects and repeats an operation on transient errors
    (PS3 webMAN: "421 Could not create socket" after many transfers)."""

    # PS3 (webMAN): after a few dozen uploads it refuses data connections ("421 Could not create socket") and only
    # recovers after minutes (09.10.: ~40 min idle) -> wait patiently (~13 min in total) instead of giving up after 20 s
    WAITS = {"ps3": [5, 15, 30, 60, 90, 120, 120, 120, 120, 120], None: [1, 3, 5, 7]}

    def __init__(self, c: dict, timeout: float = 30, tries: int | None = None):
        self.c, self.timeout = c, timeout
        self.waits = self.WAITS["ps3" if c.get("type") == "ps3" else None]
        if tries is not None:
            self.waits = self.waits[:max(0, tries - 1)]
        self.on_wait = None  # callback(text) while waiting, e.g. a job's status line
        self.f = None
        self.f = self._connect()

    def _connect(self):
        for i, w in enumerate([*self.waits, None]):
            try:
                return connect(self.c, self.timeout)
            except (ftplib.error_temp, EOFError, OSError) as e:
                if w is None:
                    raise
                self._wait(e, w)

    def _wait(self, e, w):
        store.log("ftp-retry", f"{self.c['host']}: {e} – neuer Versuch in {w} s")
        if self.on_wait:
            self.on_wait(f"{self.c.get('name', self.c['host'])} überlastet ({e}) – warte {w} s")
        time.sleep(w)

    def do(self, fn):
        for w in [*self.waits, None]:
            try:
                if self.f is None:
                    self.f = self._connect()
                r = fn(self.f)
                if self.c.get("type") == "ps3":
                    time.sleep(0.3)  # short breather between transfers
                return r
            except (ftplib.error_temp, EOFError, OSError) as e:
                if w is None:
                    raise
                self._wait(e, w)
                try:
                    self.f.close()
                except Exception:  # noqa: BLE001
                    pass
                self.f = None

    def close(self):
        try:
            self.f.close()
        except Exception:  # noqa: BLE001
            pass


def names(f: ftplib.FTP, d: str) -> list[str]:
    return [n.rstrip("/").split("/")[-1] for n in f.nlst(d)]


def save(name: str, data: dict) -> dict:
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return data


def load(name: str) -> dict | None:
    p = CACHE / f"{name}.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def retr(f: ftplib.FTP, path: str) -> bytes:
    buf = io.BytesIO()
    f.retrbinary(f"RETR {path}", buf.write)
    return buf.getvalue()


def backup(kind: str, name: str, data: bytes) -> str | None:
    """Keep a dated copy when the content changed since the newest backup."""
    d = BACKUPS / kind
    d.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(name)
    old = sorted(d.glob(f"{stem}_*{ext}"))
    if old and hashlib.sha1(old[-1].read_bytes()).digest() == hashlib.sha1(data).digest():
        return None
    p = d / f"{stem}_{time.strftime('%Y%m%d-%H%M%S')}{ext}"
    p.write_bytes(data)
    return p.name


def free_space_ftp(f: ftplib.FTP, path: str) -> int | None:
    for cmd in (f"AVBL {path}",):  # GoldHEN FTP v2.2: 502 not implemented
        try:
            m = re.search(r"(\d{6,})", f.sendcmd(cmd))
            if m:
                return int(m.group(1))
        except ftplib.all_errors:
            pass
    return None


def free_space_ps3_http(host: str) -> int | None:
    """webMAN MOD: /cpursx.ps3 shows e.g. 'HDD: 123.4 GB free' (format differs between versions)."""
    import requests
    try:
        t = requests.get(f"http://{host}/cpursx.ps3", timeout=4).text
    except Exception:
        return None
    t = re.sub(r"<[^>]+>", " ", t)
    m = re.search(r"HDD[^0-9]{0,40}([\d.,]+)\s*([GM])B", t, re.I) or re.search(r"([\d.,]+)\s*([GM])B\s*free", t, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * (2**30 if m.group(2).upper() == "G" else 2**20))


def _diff_log(c: dict, old: dict | None, new_ids: set[int], what: str):
    if not old:
        return
    before = {int(x) for x in (old.get("installed") if c["type"] == "ps4" else old.get("dirs", []))}
    added, removed = sorted(new_ids - before), sorted(before - new_ids)
    if added or removed:
        store.log(f"{c['type']}-change", f"{c['name']}: {len(added)} {what} hinzugekommen, {len(removed)} entfernt",
                  added=added[:500], removed=removed[:500], console=c["id"])


def _after_scan(cid: str):
    for cb in on_scan:
        try:
            cb(cid)
        except Exception:  # noqa: BLE001  a report must not break the scan
            pass


def scan(cfg: dict, cid: str) -> dict:
    return scan_ps4(cfg, cid) if get(cfg, cid)["type"] == "ps4" else scan_ps3(cfg, cid)


def scan_ps4(cfg: dict, cid: str = "ps4") -> dict:
    c = get(cfg, cid)
    old = load(cid)
    f = connect(c)
    try:
        installed = {}
        for n in names(f, PS4_ADDCONT):
            if len(n) == 16:
                try:
                    installed[library.songid.id_from_label(n)] = n
                except ValueError:
                    pass
        pending = [n for n in names(f, PS4_PKG) if n.lower().endswith(".pkg")]
        try:  # song names from SingStar's song db, only reachable while the game runs
            import ps4names
            songdb = ps4names.fetch(f, cid)
        except Exception:  # noqa: BLE001
            songdb = False
        free = free_space_ftp(f, "/data")
        import startpatch
        nodialog = startpatch.status(f)
        try:
            bk = backup(cid, "addcont.db", retr(f, PS4_ADDCONT_DB))
        except ftplib.all_errors:
            bk = None
    finally:
        f.close()
    _diff_log(c, old, set(installed), "Songs")
    if bk:
        store.log("backup", f"{c['name']}: addcont.db gesichert ({bk})")
    r = save(cid, {"time": time.time(), "installed": installed, "pending": pending, "free": free,
                   "songdb": songdb, "nodialog": nodialog})
    _after_scan(cid)
    return r


def scan_ps3(cfg: dict, cid: str = "ps3") -> dict:
    c = get(cfg, cid)
    old = load(cid)
    ftp = RetryFtp(c, timeout=60, tries=4)  # webMAN needs ~9 s to list the Export folder; a scan does not wait long
    try:
        dirs = ftp.do(lambda f: [int(n) for n in names(f, PS3_EXPORT) if n.isdigit()])
        xml = ftp.do(lambda f: retr(f, f"{PS3_EXPORT}/songs_4_0.xml"))
        free = ftp.do(lambda f: free_space_ftp(f, "/dev_hdd0"))
    finally:
        ftp.close()
    if free is None:
        free = free_space_ps3_http(c["host"])
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{cid}_songs_4_0.xml").write_bytes(xml)
    bk = backup(cid, "songs_4_0.xml", xml)
    if bk:
        store.log("backup", f"{c['name']}: songs_4_0.xml gesichert ({bk})")
    _diff_log(c, old, set(dirs), "Song-Ordner")
    songs = library.parse_songs_xml(xml)
    # song folders without an entry in the song list: left by a transfer that broke off before updating the lists
    unlisted = sorted(set(dirs) - set(songs))
    if unlisted and (not old or set(unlisted) != set(old.get("unlisted", []))):
        store.log("ps3-unlisted", f"{c['name']}: {len(unlisted)} Song-Ordner ohne Eintrag in der Songliste "
                                  "(abgebrochene Übertragung) – „Konsolen & Verlauf“ → „eintragen“", console=cid,
                  songs=unlisted[:200])
    r = save(cid, {"time": time.time(), "dirs": dirs, "free": free, "unlisted": unlisted,
                   "songs": {str(k): {x: v[x] for x in ("artist", "title", "gamever")} for k, v in songs.items()}})
    _after_scan(cid)
    return r


def reachable(c: dict) -> bool:
    """PS3: ping only. webMAN runs out of sockets ("421 Could not create socket") and SingStar slows down when it is
    hit by FTP connections all the time (06.10.), so the PS3 is never contacted by FTP automatically."""
    if c["type"] == "ps3":
        p = subprocess.run(["ping", "-n", "1", "-w", "1000", c["host"]], capture_output=True, text=True,
                           encoding="cp850", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # no console window
        return p.returncode == 0 and "TTL=" in p.stdout.upper()
    try:
        with socket.create_connection((c["host"], c["port"]), timeout=1.5):
            return True
    except OSError:
        return False


def monitor(cfg: dict, interval: float = 30):
    """Background thread: watch all enabled consoles (the list may change in the settings); read one automatically
    when it comes online."""
    def loop():
        while True:
            cons = active(cfg)
            for gone in set(online) - {c["id"] for c in cons}:
                online.pop(gone, None)
                checked.pop(gone, None)
            for c in cons:
                cid = c["id"]
                up = reachable(c)
                was = online.get(cid, False)
                came_up = up and not was
                if was and not up:
                    store.log("offline", f"{c['name']} ist nicht mehr erreichbar")
                elif came_up:
                    store.log("online", f"{c['name']} ist online")
                online[cid], checked[cid] = up, time.time()
                if up:
                    for cb in on_tick:
                        try:
                            cb(cid)
                        except Exception:  # noqa: BLE001
                            pass
                cached = load(cid)
                # PS3: read only on request (button), never automatically – see reachable()
                if came_up and c["type"] != "ps3" and (not cached or time.time() - cached["time"] > 120):
                    try:
                        scan(cfg, cid)
                        store.log("scan", f"{c['name']} automatisch gelesen (online)")
                    except Exception as e:  # noqa: BLE001
                        store.log("error", f"{c['name']} automatisch lesen fehlgeschlagen: {e}")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()


class Job:
    """Background task with progress for the UI."""
    all: dict[int, "Job"] = {}

    def __init__(self, title: str):
        self.id = int(time.time() * 1000)
        while self.id in Job.all:
            self.id += 1
        Job.all[self.id] = self
        self.title, self.total, self.done_bytes, self.current = title, 0, 0, ""
        self.done, self.errors, self.log = [], [], []
        self.finished, self.cancelled = False, False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self):
        try:
            self.run()
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"{type(e).__name__}: {e}")
        finally:
            self.current, self.finished = "", True

    def state(self) -> dict:
        return {"id": self.id, "title": self.title, "total": self.total, "done_bytes": self.done_bytes,
                "current": self.current, "done": self.done, "errors": self.errors, "finished": self.finished,
                "log": self.log[-400:], "next": getattr(self, "next", None), "nexts": getattr(self, "nexts", [])}


class UploadJob(Job):
    """Uploads packages to PS4 /data/pkg under their full file name (never renamed)."""

    def __init__(self, cfg: dict, files: list[str], cid: str = "ps4"):
        super().__init__(f"{len(files)} Pakete → {name(cfg, cid)} /data/pkg")
        self.cfg, self.files, self.cid = cfg, files, cid
        self.total = sum(os.path.getsize(p) for p in files)

    def run(self):
        f = connect(get(self.cfg, self.cid), timeout=60)
        try:
            have = set(names(f, PS4_PKG))
            for p in self.files:
                if self.cancelled:
                    break
                name = os.path.basename(p)
                self.current = name
                size = os.path.getsize(p)
                if name in have:
                    try:
                        if f.size(f"{PS4_PKG}/{name}") == size:
                            self.done_bytes += size
                            self.done.append(name + " (schon da)")
                            continue
                    except ftplib.error_perm:
                        pass
                try:
                    with open(p, "rb") as fh:
                        f.storbinary(f"STOR {PS4_PKG}/{name}", fh, blocksize=1 << 20, callback=self._progress)
                    self.done.append(name)
                except Exception as e:  # noqa: BLE001  keep going with the next package
                    self.errors.append(f"{name}: {e}")
                    f.close()
                    f = connect(get(self.cfg, self.cid), timeout=60)
        finally:
            f.close()
            store.log("upload", f"{len(self.done)} Pakete nach {name(self.cfg, self.cid)} /data/pkg hochgeladen"
                      + (f", {len(self.errors)} Fehler" if self.errors else ""), files=self.done, console=self.cid)

    def _progress(self, b: bytes):
        self.done_bytes += len(b)
        if self.cancelled:
            raise RuntimeError("abgebrochen")


class ReplaceJob(Job):
    """Overwrite an installed pack (/user/addcont/CUSA00033/<LABEL>/ac.pkg). SingStar must be closed."""

    def __init__(self, cfg: dict, song: dict, cid: str = "ps4"):
        super().__init__(f"{song['artist']} – {song['title']} auf {name(cfg, cid)} ersetzen")
        self.cfg, self.song, self.cid = cfg, song, cid
        self.file = song["pkg"]["file"]
        self.total = os.path.getsize(self.file)

    def run(self):
        target = f"{PS4_ADDCONT}/{self.song['label']}/ac.pkg"
        f = connect(get(self.cfg, self.cid), timeout=60)
        try:
            self.current = target
            with open(self.file, "rb") as fh:
                f.storbinary(f"STOR {target}", fh, blocksize=1 << 20,
                             callback=lambda b: setattr(self, "done_bytes", self.done_bytes + len(b)))
            if f.size(target) != self.total:
                raise RuntimeError("Größe nach dem Hochladen stimmt nicht")
            self.done.append(target)
        finally:
            f.close()
        store.log("replace", f"{name(self.cfg, self.cid)}: {self.song['artist']} – {self.song['title']} ersetzt "
                             f"({self.song['label']})", console=self.cid)


def delete_pending(cfg: dict, pkg_names: list[str], cid: str = "ps4") -> list[str]:
    """Delete packages from PS4 /data/pkg (only names that exist there)."""
    f = connect(get(cfg, cid))
    deleted = []
    try:
        have = set(names(f, PS4_PKG))
        for n in pkg_names:
            if n in have and n.lower().endswith(".pkg") and "/" not in n:
                f.delete(f"{PS4_PKG}/{n}")
                deleted.append(n)
    finally:
        f.close()
    store.log("cleanup", f"{len(deleted)} installierte Pakete aus {name(cfg, cid)} /data/pkg gelöscht",
              files=deleted, console=cid)
    return deleted


class BuildJob(Job):
    """Build PS4 packages for several songs (grouped per source, one converter run per group).
    Existing packages are moved to pkgs_old/ first and restored if the build fails."""

    def __init__(self, cfg: dict, items: list[tuple[dict, str]], title: str | None = None):
        n = len(items)
        super().__init__(title or (f"{items[0][0]['artist']} – {items[0][0]['title']} bauen" if n == 1
                                   else f"{n} PS4-Pakete bauen"))
        self.cfg, self.items = cfg, items
        self.after = None  # callback (reload library)

    def _cmd(self, source: str, songs: list[dict], out: Path) -> list[str]:
        tools = library.ROOT / "tools"
        base = [sys.executable, "-u"]
        if source == "ultrastar":
            lst = store.DATA / f"build_{self.id}.txt"
            store.DATA.mkdir(exist_ok=True)
            names = [Path(s["sources"]["ultrastar"]["folder"]).name for s in songs]
            lst.write_text("\n".join(names) + "\n", "utf-8")
            return base + [str(tools / "batch_us.py"), "--jobs", "2", "--only", f"@{lst}", "--out", str(out),
                           "--root", str(library.path(self.cfg["ultrastar_dir"]))]
        if source in ("ps3lib", "ps3disc"):
            cmd = base + [str(tools / "batch_ps3.py"), "--jobs", "2", "--out", str(out),
                          "--only", ",".join(str(s["sources"][source]["id"]) for s in songs)]
            cmd += ["--export", songs[0]["sources"]["ps3disc"]["export"] if source == "ps3disc"
                    else str(library.path(self.cfg["ps3_export_dir"]))]
            return cmd
        return base + [str(tools / "batch_ps2.py"), "--jobs", "2", "--out", str(out),
                       "--only", ",".join(str(s["id"]) for s in songs),
                       "--ps2-root", str(library.path(self.cfg["ps2_root"])),
                       "--export", str(library.path(self.cfg["ps3_export_dir"]))]

    def run(self):
        groups: dict[tuple, list[dict]] = {}
        for s, src in self.items:
            key = (src, s["sources"][src].get("export", "")) if src == "ps3disc" else (src, "")
            groups.setdefault(key, []).append(s)
        self.total = len(self.items)
        for (src, _), songs in groups.items():
            if self.cancelled:
                break
            out = library.path(self.cfg["pkg_dirs"][src])
            (out / "pkgs").mkdir(parents=True, exist_ok=True)
            moved = []
            for s in songs:
                old = out / "pkgs" / f"EP9000-CUSA00033_00-{s['label']}.pkg"
                if s["id"] > 0 and old.exists():
                    (out / "pkgs_old").mkdir(exist_ok=True)
                    keep = out / "pkgs_old" / f"{old.stem}_{time.strftime('%Y%m%d-%H%M%S')}.pkg"
                    os.replace(old, keep)
                    moved.append((old, keep))
            self.current = f"{SOURCE_NAMES.get(src, src)}: {len(songs)} Songs"
            self.log.append(f"== {self.current}")
            p = subprocess.Popen(self._cmd(src, songs, out), cwd=library.ROOT / "tools", stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.proc = p
            for line in p.stdout:
                line = line.rstrip()
                self.log.append(line)
                if re.match(r"\[\d+/\d+\] ok", line):
                    self.done_bytes += 1
                    self.done.append(line)
                elif re.match(r"\[\d+/\d+\] FEHLER", line):
                    self.done_bytes += 1
                    self.errors.append(line)
                if self.cancelled:
                    p.kill()
            p.wait()
            for old, keep in moved:  # failed songs: put the previous package back
                if not old.exists() and keep.exists():
                    os.replace(keep, old)
                    self.log.append(f"altes Paket wiederhergestellt: {old.name}")
            if p.returncode and not self.errors:
                self.errors.append(f"Konverter beendet mit Code {p.returncode} (siehe Protokoll)")
        store.log("build", f"{self.title}: {len(self.done)} ok, {len(self.errors)} Fehler",
                  songs=[s["id"] for s, _ in self.items][:500])
        if self.after:
            self.after()

    def state(self) -> dict:
        st = super().state()
        st["unit"] = "Songs"
        return st


SOURCE_NAMES = {"ultrastar": "UltraStar", "ps3disc": "PS3-Disc", "ps3lib": "PS3-Bibliothek", "ps2": "PS2-Disc"}


class MoveJob(Job):
    """Move the PS4 package folders (batch*/: pkgs, pkgs_old, reports, logs) to a new storage folder."""

    def __init__(self, old_root: Path, new_root: Path):
        super().__init__(f"PS4-Pakete nach {new_root} verschieben")
        self.old, self.new = Path(old_root), Path(new_root)
        self.files = [f for sub in library.PKG_SUBDIRS.values() if (self.old / sub).is_dir()
                      for f in (self.old / sub).rglob("*") if f.is_file() and "work" not in f.relative_to(self.old).parts]
        self.total = sum(f.stat().st_size for f in self.files)
        self.after = None

    def run(self):
        import shutil
        for f in self.files:
            if self.cancelled:
                break
            dst = self.new / f.relative_to(self.old)
            dst.parent.mkdir(parents=True, exist_ok=True)
            self.current = f.name
            size = f.stat().st_size
            shutil.move(str(f), str(dst))
            self.done_bytes += size
        self.done.append(f"{len(self.files)} Dateien verschoben")
        store.log("move", f"PS4-Pakete verschoben: {self.old} → {self.new} ({self.done_bytes / 2**30:.1f} GB)")
        if self.after:
            self.after()


class ImportJob(Job):
    """Read disc images (tools/disc_import.py) into the library."""

    def __init__(self, cfg: dict, paths: list[str]):
        super().__init__(f"{len(paths)} Abbild(er) einlesen" if len(paths) > 1 else f"{Path(paths[0]).name} einlesen")
        self.cfg, self.paths = cfg, paths
        self.total = len(paths)
        self.after = None
        self.results = []

    def run(self):
        import disc_import
        disc_import.PS3_IMPORTS = library.path(self.cfg["ps3_imports"])
        disc_import.PS2_ROOT = library.path(self.cfg["ps2_root"])
        for p in self.paths:
            if self.cancelled:
                break
            self.current = Path(p).name
            try:
                r = disc_import.import_path(Path(p), log=self.log.append)
                self.results.append(r)
                self.done.append(f"{r['kind'].upper()}: {r['name']}")
                store.log("import", f"{r['kind'].upper()}-Disc eingelesen: {r['name']}", path=p)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"{Path(p).name}: {e}")
                store.log("error", f"Einlesen fehlgeschlagen: {Path(p).name}: {e}")
            self.done_bytes += 1
        if self.after:
            self.after(self)


class FixerJob(Job):
    """Run the PS3 check (singstar_fixer.py, read-only) against the PS3."""

    def __init__(self, cfg: dict, cid: str = "ps3"):
        super().__init__(f"{name(cfg, cid)}: Prüfung (SingStar Fixer, nur lesen)")
        self.cfg, self.cid = cfg, cid

    def run(self):
        if not FIXER.exists():
            raise RuntimeError(f"{FIXER} nicht gefunden")
        self.current = "prüft …"
        p = subprocess.Popen([sys.executable, str(FIXER), "--host", get(self.cfg, self.cid)["host"]], cwd=FIXER.parent,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})

        def watch_cancel():  # the read loop below blocks while the fixer is silent -> kill it from here
            while p.poll() is None:
                if self.cancelled:
                    p.kill()
                    return
                time.sleep(0.5)
        threading.Thread(target=watch_cancel, daemon=True).start()
        for line in p.stdout:
            self.log.append(line.rstrip())
        p.wait()
        if self.cancelled:
            self.errors.append("abgebrochen")
            store.log("fixer", f"{name(self.cfg, self.cid)}: Prüfung abgebrochen", console=self.cid)
            return
        (self.done if p.returncode == 0 else self.errors).append(f"beendet (Code {p.returncode})")
        store.log("fixer", f"{name(self.cfg, self.cid)}: Prüfung beendet (Code {p.returncode})", console=self.cid)
