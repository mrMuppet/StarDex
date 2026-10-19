"""Notice new versions of downloaded songs on USDB.

USDB lists songs ordered by last change (?link=list order=lastchange ud=desc, 100 per page, each row
<tr ... data-songid="ID" data-lastchange="UNIX">). A check pages back until the last check (first check: until the
oldest download) - about one page per day of USDB activity.
Per UltraStar folder, usdb.json keeps "downloaded" (time our copy was fetched: download log run time, else the
time the info was first fetched) and, when USDB changed the song later, "update" = {"lastchange", "seen"}.
"""
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import library
import store
import usdb
import usdbdl
import usdbinfo

STATE = "usdb_updates"           # data/usdb_updates.json: {"last_check": unix}
INTERVAL = 6 * 3600              # background check every 6 hours
MAX_PAGES = 40


def download_times() -> dict[int, float]:
    """USDB id -> time of the download run (UltraStarWorker/usdb_download.log, '######## 2026-09-25 22:14:00')."""
    log = usdbdl.WORKER / "usdb_download.log"
    out, run = {}, None
    if not log.exists():
        return out
    for line in log.read_text("utf-8", errors="replace").splitlines():
        m = re.match(r"######## (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", line)
        if m:
            run = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
            continue
        m = re.match(r"== \[(\d+)\] .+", line)
        if m and run and "schon vorhanden" not in line:
            out[int(m.group(1))] = run
    return out


def local_songs(cfg: dict) -> dict[int, Path]:
    """USDB id -> folder, for folders that have usdb.json; fills in the 'downloaded' baseline."""
    root = library.path(cfg["ultrastar_dir"])
    times = download_times()
    out = {}
    for f in root.glob("*/usdb.json"):
        try:
            d = json.loads(f.read_text("utf-8"))
        except ValueError:
            continue
        if not d.get("downloaded"):
            d["downloaded"] = times.get(d["id"]) or d.get("fetched") or f.stat().st_mtime
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
        out[int(d["id"])] = f.parent
    return out


def recent_changes(since: float) -> list[tuple[int, int]]:
    """[(usdb id, lastchange)] changed after 'since', newest first."""
    s = usdb._session or usdb._login()
    out = []
    for page in range(MAX_PAGES):
        r = s.post(usdb.BASE + "?link=list", data={"order": "lastchange", "ud": "desc", "limit": "100",
                                                   "start": str(page * 100), "details": "1"}, timeout=30)
        if "not logged in" in r.text.lower():
            s = usdb._login()
            continue
        rows = [(int(i), int(t)) for i, t in re.findall(r'data-songid="(\d+)" data-lastchange="(\d+)"', r.text)]
        if not rows:
            break
        out += [x for x in rows if x[1] > since]
        if rows[-1][1] <= since:
            break
        time.sleep(1)
    return out


def check(cfg: dict) -> list[dict]:
    """Mark local songs whose USDB version is newer than our copy. Returns the newly found updates."""
    songs = local_songs(cfg)
    if not songs:
        return []
    st = store.load(STATE, {})
    oldest = min(json.loads((d / "usdb.json").read_text("utf-8"))["downloaded"] for d in songs.values())
    since = st.get("last_check") or oldest  # first check: everything since the oldest download
    started = time.time()
    found = []
    for sid, lastchange in recent_changes(since - 60):
        folder = songs.get(sid)
        if not folder:
            continue
        p = folder / "usdb.json"
        d = json.loads(p.read_text("utf-8"))
        if lastchange > d["downloaded"] and (d.get("update") or {}).get("lastchange") != lastchange:
            d["update"] = {"lastchange": lastchange, "seen": started}
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
            found.append({"id": sid, "folder": folder.name, "lastchange": lastchange})
    st["last_check"] = started
    store.save(STATE, st)
    if found:
        store.log("usdb-update", f"{len(found)} Song(s) bei USDB aktualisiert – in den Baustellen „Neue Version bei "
                                 "USDB“ → neu laden", songs=[f["folder"] for f in found])
    return found


def mark_downloaded(folders: list[Path]) -> None:
    """After a (re)download: our copy is current, drop the update flag."""
    for folder in folders:
        p = folder / "usdb.json"
        if p.exists():
            d = json.loads(p.read_text("utf-8"))
            d["downloaded"] = time.time()
            d.pop("update", None)
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")


def background(cfg: dict, on_found=None):
    """Check once a minute after start, then every INTERVAL (only with USDB credentials)."""
    def loop():
        time.sleep(60)
        while True:
            if store.load("secrets", {}).get("usdb_pass"):
                try:
                    if check(cfg) and on_found:
                        on_found()
                except Exception as e:  # noqa: BLE001
                    store.log("error", f"USDB-Update-Prüfung fehlgeschlagen: {e}")
            time.sleep(INTERVAL)
    threading.Thread(target=loop, daemon=True).start()
