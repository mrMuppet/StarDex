"""Favourites, play statistics and best scores from the consoles (SingStar's per-user LevelDBs, same format on
PS3 and PS4, see docs/TECHNIK.md):

  pinDB        SI00<id>.0 = favourite
  songstatsdb  ST00<id>.0 = {perf_started, perf_completed, last_perf_date (ns), last_perf_score}
  chartsdb     CSTO<n>.0  = {SongId, HiScore, PlayerName, IsCustomName, CreationDate}  (PS3; own entries only)

PS3: /dev_hdd0/game/BCES00011SINGSTARFAMILY/USRDIR/<user>/ - always reachable.
PS4: /mnt/sandbox/CUSA00033_000/download0/<user>/ (pinDB, songstatsdb) and temp0/chartsdb (all users) - only while
SingStar runs.
Copies go to cache/<console id>_userdb/, the summary to cache/<console id>_userdata.json (one per console, any
number of consoles). Song ids are PS4 ids (PS3 own songs 600xx -> 45xxx).
"""
import json
import sys
import time
from pathlib import Path

import library

sys.path.insert(0, str(library.ROOT / "tools"))
import ps4_pins  # noqa: E402
import songid  # noqa: E402

CACHE = Path(__file__).parent / "cache"
ROOTS = {"ps3": "/dev_hdd0/game/BCES00011SINGSTARFAMILY/USRDIR", "ps4": "/mnt/sandbox/CUSA00033_000/download0"}
DBS = ("pinDB", "songstatsdb", "chartsdb")


def _names(f, d):
    return [n.rstrip("/").split("/")[-1] for n in f.nlst(d) if n.rstrip("/").split("/")[-1] not in (".", "..")]


def fetch(ftp, console: str, kind: str) -> bool:
    """Copy the user dbs of console id `console` of type `kind` (ftp = consoles.RetryFtp).
    False if not reachable (PS4: game not running)."""
    root = ROOTS[kind]
    try:
        users = [u for u in ftp.do(lambda f: _names(f, root)) if u.isdigit()]
    except Exception:  # noqa: BLE001
        return False
    if not users:
        return False
    base = CACHE / f"{console}_userdb"
    for u in users:
        for db in DBS:
            try:
                files = ftp.do(lambda f, u=u, db=db: _names(f, f"{root}/{u}/{db}"))
            except Exception:  # noqa: BLE001  (PS4 has no chartsdb)
                continue
            d = base / u / db
            d.mkdir(parents=True, exist_ok=True)
            for old in d.iterdir():
                old.unlink()
            for n in files:
                if n.startswith("LOG"):
                    continue

                def get(f, n=n, u=u, db=db, d=d):
                    with open(d / n, "wb") as fh:
                        f.retrbinary(f"RETR {root}/{u}/{db}/{n}", fh.write)
                ftp.do(get)
    if kind == "ps4":  # PS4 keeps the charts (best scores) for all users in temp0, not per user
        charts = "/mnt/sandbox/CUSA00033_000/temp0/chartsdb"
        try:
            files = ftp.do(lambda f: _names(f, charts))
            d = base / "_charts" / "chartsdb"
            d.mkdir(parents=True, exist_ok=True)
            for old in d.iterdir():
                old.unlink()
            for n in files:
                if n.startswith("LOG"):
                    continue

                def get(f, n=n, d=d):
                    with open(d / n, "wb") as fh:
                        f.retrbinary(f"RETR {charts}/{n}", fh.write)
                ftp.do(get)
        except Exception:  # noqa: BLE001
            pass
    summarize(console, kind)
    return True


def _pid(kind: str, sid: int) -> int:
    return songid.ps4_id(sid) if kind == "ps3" else sid


def summarize(console: str, kind: str) -> dict:
    base = CACHE / f"{console}_userdb"
    favs, stats, best, charts = set(), {}, {}, {}
    for udir in sorted(base.iterdir()) if base.is_dir() else []:
        if (udir / "pinDB").is_dir():
            for k, v in ps4_pins.entries(udir / "pinDB").items():
                if k.startswith("SI00") and v:
                    favs.add(_pid(kind, int(k[4:].split(".")[0])))
        if (udir / "songstatsdb").is_dir():
            for k, v in ps4_pins.entries(udir / "songstatsdb").items():
                if k.startswith("ST00") and v:
                    j = json.loads(v)
                    sid = _pid(kind, int(j["song_id"]))
                    s = stats.setdefault(sid, {"plays": 0, "last": 0, "last_score": 0})
                    s["plays"] += int(j.get("perf_completed") or 0)
                    if (j.get("last_perf_date") or 0) > s["last"] and j.get("perf_completed"):
                        s["last"], s["last_score"] = j["last_perf_date"], j.get("last_perf_score") or 0
        if (udir / "chartsdb").is_dir():
            for k, v in ps4_pins.entries(udir / "chartsdb").items():
                if k.startswith("CSTO") and v:
                    j = json.loads(v)
                    if not j.get("IsCustomName"):
                        continue  # game-made default charts with invented names
                    sid = _pid(kind, int(j["SongId"]))
                    entry = {"score": j["HiScore"], "date": j.get("CreationDate"), "player": j.get("PlayerName"),
                             "length": j.get("SongLength"), "photo": j.get("PhotoPath") or ""}
                    charts.setdefault(sid, []).append(entry)
                    if j["HiScore"] > best.get(sid, {}).get("score", -1):
                        best[sid] = entry
    out = {"time": time.time(), "favs": sorted(favs),
           "stats": {str(k): v for k, v in stats.items() if v["plays"]},
           "best": {str(k): v for k, v in best.items()},
           "charts": {str(k): sorted(v, key=lambda e: -e["score"])[:20] for k, v in charts.items()}}
    (CACHE / f"{console}_userdata.json").write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    return out


def load(console: str) -> dict:
    p = CACHE / f"{console}_userdata.json"
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {"time": None, "favs": [], "stats": {}, "best": {}}


def per_song(cons: list[str]) -> dict[int, dict]:
    """cons = console ids. {ps4 id: {fav: {console id: True}, plays, plays_by: {console id: n}, last, best,
    best_console}}"""
    out: dict[int, dict] = {}
    for c in cons:
        d = load(c)
        for sid in d["favs"]:
            out.setdefault(sid, {}).setdefault("fav", {})[c] = True
        for sid, s in d["stats"].items():
            o = out.setdefault(int(sid), {})
            o.setdefault("plays_by", {})[c] = s["plays"]
            o["plays"] = o.get("plays", 0) + s["plays"]
            if s["last"] > o.get("last", 0):
                o["last"] = s["last"]
        for sid, b in d["best"].items():
            o = out.setdefault(int(sid), {})
            if b["score"] > o.get("best", -1):
                o["best"], o["best_console"], o["best_date"] = b["score"], c, b.get("date")
                o["best_player"] = b.get("player")
    return out


def charts(sid: int, cons: list[str]) -> list[dict]:
    """Own chart entries of a song from all consoles (ids), best first."""
    out = []
    for c in cons:
        for e in load(c).get("charts", {}).get(str(sid), []):
            out.append({**e, "console": c})
    return sorted(out, key=lambda e: -e["score"])
