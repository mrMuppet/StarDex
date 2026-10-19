"""Inventory of the PS2 SingStar discs: which songs exist only there (not in the PS3 library, not as UltraStar).

  python ps2_inventory.py        -> build/ps2_only.json + summary

Song lists are plain XML inside PACK_EE.PAK (newer discs) or EE/export/songs*.xml (SingStar Germany).
Songs already in the PS3 library (same id, or same artist + title) are skipped: the PS3 version wins
(better video, decision 28.09.).
"""
import collections
import glob
import json
import os
import re
import unicodedata
from pathlib import Path

import local_config  # noqa: E402
PS2_ROOT = str(local_config.path("ps2_root"))
EXPORT = str(local_config.path("ps3_export_dir"))
BUILD = Path(__file__).resolve().parent.parent / "build"


def key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def disc_songs(d: str) -> dict:
    """{id: (artist, title)} of the songs really on this disc. The song lists in PACK_EE.PAK also name songs of
    other discs (disc swapping); a song is on the disc when its melody is (melody comments carry the title)."""
    files = (glob.glob(d + "/*_ISO/PACK_EE.PAK") + glob.glob(d + "/*/PACK_EE.PAK")
             + glob.glob(d + "/*_ISO/EE/export/songs*.xml"))
    listed, on_disc = {}, set()
    for f in files:
        t = open(f, "rb").read().decode("latin-1")
        for m in re.finditer(r"<SONG\b([^>]*)>", t):
            a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            if "ID" in a and "TITLE" in a:
                listed[int(a["ID"])] = (a.get("PERFORMANCE_NAME", "?"), a["TITLE"])
        for m in re.finditer(r"<!--\s*Title:\s*(.*?)\s*-->", t):
            on_disc.add(key(m.group(1)))
    for f in glob.glob(d + "/*_ISO/EE/export/*/melody.xml"):  # SingStar (Germany): loose files
        on_disc.add(key(re.search(r"<!--\s*Title:\s*(.*?)\s*-->", open(f, encoding="latin-1").read()).group(1)))
    return {i: v for i, v in listed.items() if key(v[1]) in on_disc}


def main():
    ps3 = open(EXPORT + "/songs_4_0.xml", encoding="utf-8", errors="replace").read()
    ps3_ids = {int(i) for i in re.findall(r'<SONG ID="(\d+)"', ps3)}
    ps3_keys = {key(m.group(3)) + key(m.group(2))
                for m in re.finditer(r'<SONG ID="(\d+)".*?<TITLE>([^<]*)</TITLE>.*?<PERFORMANCE_NAME>([^<]*)',
                                     ps3, re.S)}
    ids = BUILD.parent / "song_ids.json"
    us_keys = {key(k) for k in (json.loads(ids.read_text("utf-8")) if ids.exists() else {})}
    discs, first = {}, {}
    for d in sorted(glob.glob(PS2_ROOT + "/*/")):
        name = os.path.basename(os.path.normpath(d))
        discs[name] = disc_songs(d)
        for i, v in discs[name].items():
            first.setdefault(i, (v, name))
    only = {}
    same_name, as_us = [], []
    for i, (v, disc) in first.items():
        if i in ps3_ids:
            continue
        k = key(v[0]) + key(v[1])
        if k in ps3_keys:
            same_name.append(f"{i} {v[0]} - {v[1]}")
            continue
        entry = {"artist": v[0], "title": v[1], "disc": disc, "ultrastar": k in us_keys}
        if entry["ultrastar"]:
            as_us.append(f"{v[0]} - {v[1]}")
        only[str(i)] = entry
    (BUILD / "ps2_only.json").write_text(json.dumps(only, ensure_ascii=False, indent=1), "utf-8")
    print("Songs pro Disc:", {k: len(v) for k, v in discs.items()})
    print(f"verschiedene Songs: {len(first)}, schon in PS3-Bibliothek (ID): {sum(i in ps3_ids for i in first)}, "
          f"gleicher Titel in PS3-Bibliothek: {len(same_name)}, nur PS2: {len(only)}")
    print("nur PS2, aber als UltraStar vorhanden:", as_us)
    print("nur PS2 pro Disc:", dict(collections.Counter(v["disc"] for v in only.values())))


if __name__ == "__main__":
    main()
