"""USDB quality info per UltraStar song, stored as <song folder>/usdb.json (see usdb.detail).

Which USDB song a folder came from: the download log of UltraStarWorker ("== [<id>] <folder>"), else the USDB song
list (usdb_songlist.json from usdb_match.py) matched by artist + title.
"""
import json
import re
import time
from pathlib import Path

import consoles
import library
import store
import usdb
import usdbdl


def id_map(us_root: Path) -> dict[str, int]:
    """{folder name: usdb id}"""
    out = {}
    log = usdbdl.WORKER / "usdb_download.log"
    if log.exists():
        for sid, name in re.findall(r"^== \[(\d+)\] (.+?)(?::\s*schon vorhanden.*)?$",
                                    log.read_text("utf-8", errors="replace"), re.M):
            out[name.strip()] = int(sid)
    songlist = usdbdl.WORKER / "usdb_songlist.json"
    if songlist.exists():
        by_key = {}
        for s in json.loads(songlist.read_text("utf-8")):
            by_key.setdefault(library.norm(s["artist"]) + "|" + library.norm(s["title"]), s["id"])
        for d in us_root.iterdir() if us_root.is_dir() else []:
            if d.is_dir() and d.name not in out:
                h = library.us_header(d)
                sid = by_key.get(library.norm(h.get("ARTIST", "")) + "|" + library.norm(h.get("TITLE", "")))
                if sid:
                    out[d.name] = sid
    return out


def save(folder: Path, info: dict) -> None:
    info["fetched"] = time.time()
    old = folder / "usdb.json"
    if old.exists():  # keep the version tracking (usdbupdates.py) when only the info is refreshed
        try:
            prev = json.loads(old.read_text("utf-8"))
            for k in ("downloaded", "update"):
                if k in prev:
                    info.setdefault(k, prev[k])
        except ValueError:
            pass
    (folder / "usdb.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")


class USDBInfoJob(consoles.Job):
    """Fetch the USDB quality info for UltraStar folders (only missing ones unless refresh)."""

    def __init__(self, cfg: dict, folders: list[str] | None = None, refresh: bool = False):
        super().__init__("USDB-Infos holen")
        self.cfg, self.only, self.refresh = cfg, folders, refresh
        self.after = None

    def run(self):
        if not usdb.JOBS.acquire(blocking=False):
            self.current = "wartet auf die laufende USDB-Aufgabe …"
            usdb.JOBS.acquire()
        try:
            self._run_locked()
        finally:
            usdb.JOBS.release()

    def _run_locked(self):
        root = library.path(self.cfg["ultrastar_dir"])
        ids = id_map(root)
        todo = [(n, i) for n, i in ids.items() if (root / n).is_dir() and (self.only is None or n in self.only)
                and (self.refresh or not (root / n / "usdb.json").exists())]
        self.total = len(todo)
        for n, sid in todo:
            if self.cancelled:
                break
            self.current = n
            try:
                save(root / n, usdb.detail(sid))
                self.done.append(f"{sid} {n}")
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"{n}: {e}")
            self.done_bytes += 1
            time.sleep(1)  # be gentle with USDB
        store.log("usdb", f"USDB-Infos für {len(self.done)} Songs geholt"
                  + (f", {len(self.errors)} Fehler" if self.errors else ""))
        if self.after:
            self.after()

    def state(self) -> dict:
        st = super().state()
        st["unit"] = "Songs"
        return st
