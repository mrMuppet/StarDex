"""Which SingStar edition (disc) a song comes from -> manager/data/editions.json {ps4 id: [edition, ...]}.

Sources:
- Toolbox exports "<toolbox_exports>/<Artist> - <Title> [<serial>].SST3|SSTD": the header holds the song
  id, the file name the serial of the disc it was exported from. Serial -> name: PS3 from the Toolbox keys.db
  (BCES00381|SingStar ABBA (Europe)|...), PS2 from SYSTEM.CNF of the extracted PS2 discs (SCES_525.65).
- PS2 discs: build/ps2_choice.json (disc per PS2-only song).
- UltraStar songs without a disc origin: "UltraStar"; own PS3 songs (600xx) without export: "Eigener Song (PS3)".

  python manager/editions.py
"""
import json
import re
from pathlib import Path

import library
import local_config  # tools/, on sys.path via library

EXPORTED = local_config.path("toolbox_exports")
KEYS_DB = local_config.path("toolbox_keys_db")
PS2_ROOT = local_config.path("ps2_root")
OUT = Path(__file__).parent / "data" / "editions.json"


def clean(name: str) -> str:
    """'SingStar Die Eiskoenigin - Voellig unverfroren (Germany)' -> without region/version suffixes."""
    name = re.sub(r"\s*\((Europe|Germany|USA|Spain|France|Italy|Australia|Asia|Europe, Australia|v[\d.]+|"
                  r"En,[^)]*)\)", "", name)
    return name.replace("Eiskoenigin", "Eiskönigin").replace("Voellig", "Völlig").strip()


def serial_names() -> dict[str, str]:
    names = {}
    if KEYS_DB.exists():
        for serial, name in re.findall(r"([A-Z]{4}\d{5})\|([^|]+)", KEYS_DB.read_bytes().decode("latin-1")):
            names.setdefault(serial[-5:], clean(name))
    for d in PS2_ROOT.iterdir() if PS2_ROOT.exists() else []:
        if not d.is_dir():
            continue
        for cnf in list(d.glob("*/SYSTEM.CNF")) + list(d.glob("SYSTEM.CNF")) + list(d.glob("*/*/SYSTEM.CNF")):
            m = re.search(rb"S[CL][EU]S_(\d{3})\.(\d{2})", cnf.read_bytes())
            if m:
                names[(m.group(1) + m.group(2)).decode()] = clean(d.name) + " (PS2)"
                break
    return names


def build() -> dict[int, list[str]]:
    cfg = library.load_config()
    names = serial_names()
    ed: dict[int, list[str]] = {}

    def add(sid: int, name: str):
        lst = ed.setdefault(sid, [])
        if name not in lst:
            lst.append(name)

    for f in EXPORTED.glob("*.SST*") if EXPORTED.exists() else []:
        m = re.search(rb"[\x00-\x0f](\d{1,5})\x00\d+\x00", f.open("rb").read(64))
        serial = re.findall(r"\[(\d{5})\]", f.name)
        if m and serial:
            add(library.songid.ps4_id(int(m.group(1))), names.get(serial[-1], f"Disc {serial[-1]}"))
    ch = library.path(cfg["ps2_choice"])
    if ch.exists():
        for r in json.loads(ch.read_text("utf-8")):
            disc = re.sub(r"\(?Germany\)?", "", r["disc"]).strip()
            add(r["id"], f"SingStar {disc} (PS2)".replace("  ", " "))
    queen = library.ROOT / "build" / "queen_pak_index.json"  # SingStar Queen (PS2), see docs/TECHNIK.md
    if queen.exists():
        for r in json.loads(queen.read_text("utf-8")):
            add(int(r["id"]), "SingStar Queen (PS2)")
    for name, sid in library.song_ids(cfg).items():
        if sid not in ed:
            add(sid, "UltraStar")
    exp = library.path(cfg["ps3_export_dir"]) / "songs_4_0.xml"
    if exp.exists():
        for ps3, m in library.parse_songs_xml(exp.read_bytes()).items():
            sid = library.songid.ps4_id(ps3)
            if sid not in ed:
                add(sid, "Eigener Song (PS3)" if ps3 >= 60000 else f"unbekannt ({m['gamever'] or 'PS3-Bibliothek'})")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({str(k): v for k, v in sorted(ed.items())}, ensure_ascii=False, indent=0), "utf-8")
    return ed


def load() -> dict[int, list[str]]:
    if not OUT.exists():
        return build()
    return {int(k): v for k, v in json.loads(OUT.read_text("utf-8")).items()}


if __name__ == "__main__":
    e = build()
    from collections import Counter
    print(len(e), "Songs;", Counter(x for v in e.values() for x in v).most_common(40))
