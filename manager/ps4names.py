"""Names of songs installed on the PS4, from SingStar's song db (LevelDB download0/songdb, keys SA08<id>.0 = JSON).

The db is only reachable while SingStar runs (/mnt/sandbox/CUSA00033_000/download0/songdb). A scan copies it to
cache/ps4_songdb/ when available; otherwise the last copy (or the dump in backup/download0_now/songdb) is used.
"""
import json
import re
import struct
import sys
from pathlib import Path

import library

sys.path.insert(0, str(library.ROOT / "tools"))
from leveldb_log import records, varint  # noqa: E402
import leveldb_table  # noqa: E402

CACHE = Path(__file__).parent / "cache" / "ps4_songdb"
FALLBACK = library.ROOT / "backup" / "download0_now" / "songdb"
REMOTE = "/mnt/sandbox/CUSA00033_000/download0/songdb"


def _log_entries(path: Path):
    for rec in records(path.read_bytes()):
        seq, count = struct.unpack_from("<QI", rec, 0)
        i = 12
        for _ in range(count):
            tag = rec[i]
            i += 1
            kl, i = varint(rec, i)
            key = rec[i:i + kl]
            i += kl
            val = None
            if tag == 1:
                vl, i = varint(rec, i)
                val = rec[i:i + vl]
                i += vl
            yield seq, key, val
            seq += 1


def read_db(folder: Path) -> dict[int, dict]:
    """{song id: {artist, title}} from the SA08 records (tables first, then the newer write-ahead logs)."""
    latest: dict[bytes, tuple[int, bytes | None]] = {}
    for f in sorted(folder.glob("*.ldb")) + sorted(folder.glob("*.sst")):
        for key, seq, typ, val in leveldb_table.entries(str(f)):
            if key.startswith(b"SA08") and seq >= latest.get(key, (-1, None))[0]:
                latest[key] = (seq, val if typ else None)
    for f in sorted(folder.glob("*.log")):
        for seq, key, val in _log_entries(f):
            if key.startswith(b"SA08") and seq >= latest.get(key, (-1, None))[0]:
                latest[key] = (seq, val)
    out = {}
    for key, (_, val) in latest.items():
        if not val:
            continue
        try:
            j = json.loads(val.decode("utf-8", "replace"))
        except ValueError:
            m = re.search(rb'"artist":"([^"]*)".*?"title":"([^"]*)".*?"id":(\d+)', val)
            if not m:
                continue
            j = {"artist": m.group(1).decode("utf-8", "replace"), "title": m.group(2).decode("utf-8", "replace"),
                 "id": int(m.group(3))}
        if "id" in j:
            out[int(j["id"])] = {"artist": j.get("artist", "?"), "title": j.get("title", "?"),
                                 "demo": bool(j.get("demosong")), "disc": bool(j.get("isDiscSong"))}
    return out


def _cache(cid: str) -> Path:
    return CACHE.with_name(f"{cid}_songdb")  # "ps4" -> cache/ps4_songdb as before


def fetch(f, cid: str = "ps4") -> bool:
    """Copy the song db from the running game (FTP session f); False if SingStar is not running."""
    try:
        names = [n.rstrip("/").split("/")[-1] for n in f.nlst(REMOTE)]
    except Exception:  # noqa: BLE001
        return False
    files = [n for n in names if n.endswith((".log", ".ldb", ".sst")) or n.startswith(("MANIFEST", "CURRENT"))]
    if not files:
        return False
    dst = _cache(cid)
    tmp = dst.with_name(dst.name + "_new")
    tmp.mkdir(parents=True, exist_ok=True)
    for n in files:
        with open(tmp / n, "wb") as fh:
            f.retrbinary(f"RETR {REMOTE}/{n}", fh.write)
    import shutil
    shutil.rmtree(dst, ignore_errors=True)
    tmp.rename(dst)
    return True


def names(cid: str = "ps4") -> dict[int, dict]:
    for folder in (_cache(cid), FALLBACK if cid == "ps4" else None):
        if folder is None:
            continue
        if folder.is_dir():
            try:
                return read_db(folder)
            except Exception:  # noqa: BLE001
                continue
    return {}
