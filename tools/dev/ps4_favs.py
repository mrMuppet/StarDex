"""Set/remove SingStar PS4 favourites from outside (SingStar must be running; restart it afterwards).

  python ps4_favs.py add ID [ID ...]      mark songs as favourite
  python ps4_favs.py remove ID [ID ...]   remove favourites
  python ps4_favs.py list                 current favourites
  add --dry-run: build the log file locally only (build/pins/_favlog/)

Format (found 01.10. by comparing backups): per user /download0/<user>/pinDB (LevelDB), per favourite 5 keys:
  SI00<id>.0                          {"id","pinnedTitleKey","pinnedDate","pinnedArtistKey"}
  AI00<artistKey>.<id>                {"id"}      artistKey/titleKey/releaseYear from the song db (SA08<id>.0)
  TI00<titleKey>.<id>                 {"id"}
  RI00<year 4>.<id 10>.<id>           {"id"}
  DPI0<pinnedDate ns>.<id>            {"id"}
The game keeps the db open, so we do not touch its files: a NEW write-ahead log with a high file number is put
next to them. LevelDB replays every log >= the manifest's log number on open, so the batch is applied when
SingStar starts the next time (sequence numbers above everything in the db).
"""
import ftplib
import io
import json
import re
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/
import ps4_pins  # noqa: E402

HOST, PORT = ps4_pins.HOST, ps4_pins.PORT
BASE = ps4_pins.BASE
SONGDB = f"{BASE}/songdb"
OUT = ps4_pins.OUT / "_favlog"

_T = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0x82F63B78 if _c & 1 else _c >> 1
    _T.append(_c)


def crc32c(b: bytes) -> int:
    c = 0xFFFFFFFF
    for x in b:
        c = _T[(c ^ x) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFF


def masked(c: int) -> int:
    return ((((c >> 15) | (c << 17)) & 0xFFFFFFFF) + 0xA282EAD8) & 0xFFFFFFFF


def varint(n: int) -> bytes:
    out = bytearray()
    while n >= 0x80:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def batch(seq: int, ops: list[tuple[bytes, bytes | None]]) -> bytes:
    b = struct.pack("<QI", seq, len(ops))
    for k, v in ops:
        b += (b"\x01" + varint(len(k)) + k + varint(len(v)) + v) if v is not None else (b"\x00" + varint(len(k)) + k)
    return b


def log_file(batches: list[bytes]) -> bytes:
    """LevelDB log: 32 KiB blocks, records FULL(1)/FIRST(2)/MIDDLE(3)/LAST(4) with masked crc32c."""
    out, BLOCK = bytearray(), 32768
    for data in batches:
        first = True
        while True:
            left = BLOCK - len(out) % BLOCK
            if left < 7:
                out += b"\x00" * left
                left = BLOCK
            n = min(len(data), left - 7)
            frag, data = data[:n], data[n:]
            typ = (1 if first else 4) if not data else (2 if first else 3)
            out += struct.pack("<IHB", masked(crc32c(bytes([typ]) + frag)), len(frag), typ) + frag
            first = False
            if not data:
                break
    return bytes(out)


def connect() -> ftplib.FTP:
    f = ftplib.FTP()
    f.connect(HOST, PORT, timeout=30)
    f.login()
    f.voidcmd("TYPE I")
    return f


def fetch_db(f, remote: str, local: Path) -> None:
    local.mkdir(parents=True, exist_ok=True)
    for old in local.iterdir():
        old.unlink()
    for n in ps4_pins.ls(f, remote):
        with open(local / n, "wb") as fh:
            f.retrbinary(f"RETR {remote}/{n}", fh.write)


def state(f, user: str) -> dict:
    """Current pinDB + song db (keys, max sequence, file numbers)."""
    work = ps4_pins.OUT / "_live"
    fetch_db(f, f"{BASE}/{user}/pinDB", work / "pinDB")
    fetch_db(f, SONGDB, work / "songdb")
    pins = ps4_pins.entries(work / "pinDB")
    songs = {}
    for k, v in ps4_pins.entries(work / "songdb").items():
        if k.startswith("SA08") and v:
            try:
                j = json.loads(v.decode("utf-8", "replace"))
                songs[int(j["id"])] = j
            except (ValueError, KeyError):
                pass
    seqs = max_seq(work / "pinDB")
    nums = [int(m.group(1)) for p in (work / "pinDB").iterdir() for m in [re.match(r"(\d+)\.(log|ldb|sst)$", p.name)] if m]
    return {"pins": pins, "songs": songs, "max_seq": seqs, "max_file": max(nums + [0])}


def max_seq(folder: Path) -> int:
    best = 0
    for p in sorted(folder.glob("*.ldb")) + sorted(folder.glob("*.sst")):
        for _k, seq, _t, _v in ps4_pins.leveldb_table.entries(str(p)):
            best = max(best, seq)
    for p in sorted(folder.glob("*.log")):
        for rec in ps4_pins.records(p.read_bytes()):
            seq, count = struct.unpack_from("<QI", rec, 0)
            best = max(best, seq + count - 1)
    return best


def fav_ops(song: dict, add: bool, pinned: dict | None = None) -> list[tuple[bytes, bytes | None]]:
    sid = int(song["id"])
    val = json.dumps({"id": sid}, separators=(",", ":")).encode()
    date = pinned["pinnedDate"] if pinned else time.time_ns()
    keys = [f"AI00{song['artistKey']}.{sid}", f"TI00{song['titleKey']}.{sid}",
            f"RI00{int(song.get('releaseYear') or 0):04d}.{sid:010d}.{sid}", f"DPI0{date}.{sid}"]
    si = json.dumps({"id": sid, "pinnedTitleKey": song["titleKey"], "pinnedDate": date,
                     "pinnedArtistKey": song["artistKey"]}, separators=(",", ":"), ensure_ascii=False).encode()
    ops = [(f"SI00{sid}.0".encode(), si if add else None)]
    ops += [(k.encode("utf-8"), val if add else None) for k in keys]
    return ops


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args or args[0] not in ("add", "remove", "list"):
        sys.exit(__doc__)
    f = connect()
    try:
        users = [u for u in ps4_pins.ls(f, BASE) if u.isdigit()]
        if not users:
            sys.exit("download0 nicht erreichbar - SingStar starten")
        user = users[0]
        st = state(f, user)
        favs = {int(k[4:].split(".")[0]): json.loads(v) for k, v in st["pins"].items() if k.startswith("SI00") and v}
        if args[0] == "list":
            for sid, p in sorted(favs.items(), key=lambda x: x[1]["pinnedArtistKey"]):
                print(sid, p["pinnedArtistKey"])
            print(len(favs), "Favoriten")
            return
        ops = []
        for a in args[1:]:
            sid = int(a)
            song = st["songs"].get(sid)
            if not song:
                print(f"{sid}: nicht in der Song-DB - übersprungen")
                continue
            if args[0] == "add" and sid in favs:
                print(f"{sid}: schon Favorit")
                continue
            if args[0] == "remove" and sid not in favs:
                print(f"{sid}: kein Favorit")
                continue
            ops += fav_ops(song, args[0] == "add", favs.get(sid))
            print(f"{sid}: {song['artist']} - {song['title']} -> {'Favorit' if args[0] == 'add' else 'entfernt'}")
        if not ops:
            return
        seq = st["max_seq"] + 100
        num = max(st["max_file"] + 500, 900)
        name = f"{num:06d}.log"
        data = log_file([batch(seq, ops)])
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_bytes(data)
        # self check: our reader must read back exactly these operations
        back = [r for r in ps4_pins.records(data)]
        assert len(back) == 1 and struct.unpack_from("<QI", back[0], 0) == (seq, len(ops))
        print(f"{name}: {len(ops)} Einträge, Sequenz ab {seq} (DB bisher bis {st['max_seq']})")
        if dry:
            print(f"--dry-run: nur lokal geschrieben ({OUT / name})")
            return
        f.storbinary(f"STOR {BASE}/{user}/pinDB/{name}", io.BytesIO(data))
        print("hochgeladen - SingStar jetzt beenden und neu starten, dann Favoriten prüfen")
    finally:
        f.close()


if __name__ == "__main__":
    main()
