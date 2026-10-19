"""Favourites test on the PS4: back up and compare SingStar's per-user LevelDBs (pinDB = favourites "songpins",
songstatsdb) while the game runs. Only reads from the PS4.

  python ps4_pins.py backup NAME     copy download0/<user>/{pinDB,songstatsdb} to build/pins/NAME/
  python ps4_pins.py dump NAME       print all records of a backup
  python ps4_pins.py diff A B        records that differ between two backups
"""
import ftplib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leveldb_log import records, varint  # noqa: E402
import leveldb_table  # noqa: E402
from local_config import host  # noqa: E402

HOST, PORT = host("ps4"), 2121
BASE = "/mnt/sandbox/CUSA00033_000/download0"
OUT = Path(__file__).parent.parent / "build" / "pins"
DBS = ("pinDB", "songstatsdb")


def ls(f, d):
    return [n.rstrip("/").split("/")[-1] for n in f.nlst(d)]


def backup(name: str) -> None:
    f = ftplib.FTP()
    f.connect(HOST, PORT, timeout=30)
    f.login()
    f.voidcmd("TYPE I")
    try:
        users = [u for u in ls(f, BASE) if u.isdigit()]
        if not users:
            sys.exit("download0 nicht erreichbar - läuft SingStar?")
        for u in users:
            for db in DBS:
                dst = OUT / name / u / db
                dst.mkdir(parents=True, exist_ok=True)
                for n in ls(f, f"{BASE}/{u}/{db}"):
                    with open(dst / n, "wb") as fh:
                        f.retrbinary(f"RETR {BASE}/{u}/{db}/{n}", fh.write)
                print(f"{u}/{db}: {len(list(dst.iterdir()))} Dateien")
    finally:
        f.close()


def entries(folder: Path) -> dict[str, bytes | None]:
    """key -> value (None = deleted), tables first, then logs (newer)."""
    latest: dict[bytes, tuple[int, bytes | None]] = {}
    for p in sorted(folder.glob("*.ldb")) + sorted(folder.glob("*.sst")):
        if p.read_bytes()[-8:] != bytes.fromhex("57fb808b247547db"):
            continue  # not a finished table (e.g. compaction in progress while the game runs)
        for key, seq, typ, val in leveldb_table.entries(str(p)):
            if seq >= latest.get(key, (-1, None))[0]:
                latest[key] = (seq, val if typ else None)
    for p in sorted(folder.glob("*.log")):
        for rec in records(p.read_bytes()):
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
                latest[key] = (seq, val)
                seq += 1
    return {k.decode("latin-1"): v for k, (_, v) in sorted(latest.items())}


def all_entries(name: str) -> dict[str, bytes | None]:
    out = {}
    for db_dir in sorted((OUT / name).glob("*/*")):
        for k, v in entries(db_dir).items():
            out[f"{db_dir.parent.name}/{db_dir.name}: {k}"] = v
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "backup":
        backup(sys.argv[2])
    elif cmd == "dump":
        for k, v in all_entries(sys.argv[2]).items():
            print(k, "=", v)
    elif cmd == "diff":
        a, b = all_entries(sys.argv[2]), all_entries(sys.argv[3])
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                print(("NEU   " if k not in a else "WEG   " if k not in b else "ANDERS"), k, "=", b.get(k, a.get(k)))
    else:
        sys.exit(__doc__)
