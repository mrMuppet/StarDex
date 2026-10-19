"""Rate every UltraStar song for vocal reduction (ADRS): how much of the lead vocal and of the music a
centre window reaches (see adrs_fit.py). Thresholds follow Sony's own choices in the PS3 library
(songs with ADRS: vocal 74 % / music 41 % in the centre window, songs left out: 59 % / 49 %).

  python adrs_us_scan.py [US_ROOT]     -> build/adrs_us_scan.json + table
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import adrs_band as ab  # noqa: E402
from adrs_fit import pan_energy, reach  # noqa: E402
from us_to_ps4 import find_file, parse  # noqa: E402

import local_config  # noqa: E402
US_ROOT = local_config.path("ultrastar_dir")
BAND = (312.5, 6250)     # same band as the calibration against Sony
WIDTH = 0.15


def rate(vocal, music):
    if vocal >= 0.65 and music <= 0.45 and vocal - music >= 0.25:
        return "geeignet"
    if vocal < 0.50 or music >= 0.60 or vocal - music < 0.10:
        return "ungeeignet"
    return "grenzwertig"


def scan(folder: Path):
    try:
        txt = next(folder.glob("*.txt"))
        head, lines, duet = parse(txt)
        if duet:
            return {"song": folder.name, "skip": "Duett"}
        bpm = float(head["BPM"].replace(",", "."))
        tick = 60.0 / (bpm * 4)
        gap = float(head.get("GAP", "0").replace(",", ".")) / 1000
        iv = [(gap + n["start"] * tick, gap + (n["start"] + n["len"]) * tick) for ln in lines for n in ln]
        audio = find_file(folder, head.get("MP3") or head.get("AUDIO"), (".mp3", ".ogg", ".m4a", ".wav", ".flac"))
        x = ab.load(audio)
        mid, side = x.sum(1) / 2, (x[:, 0] - x[:, 1]) / 2
        stereo = float(np.sqrt((side ** 2).mean() / max((mid ** 2).mean(), 1e-20)))
        h = pan_energy(x, iv, *BAND)
        if h is None:
            return {"song": folder.name, "skip": "zu wenig Gesang/Instrumental"}
        res = {"song": folder.name, "stereo": stereo}
        for w in (0.10, 0.15, 0.20):
            v, m = reach(h, 0.0, w)
            res[f"vocal_{w:.2f}"], res[f"music_{w:.2f}"] = v, m
        res["rating"] = rate(res[f"vocal_{WIDTH:.2f}"], res[f"music_{WIDTH:.2f}"])
        return res
    except Exception as ex:  # noqa: BLE001
        return {"song": folder.name, "skip": f"Fehler: {ex}"}


def main(root=US_ROOT):
    folders = sorted(p for p in Path(root).iterdir() if p.is_dir())
    with ProcessPoolExecutor(6) as ex:
        rows = list(ex.map(scan, folders))
    out = Path(__file__).resolve().parent.parent / "build" / "adrs_us_scan.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), "utf-8")
    ok = [r for r in rows if "rating" in r]
    for r in sorted(ok, key=lambda r: r[f"music_{WIDTH:.2f}"] - r[f"vocal_{WIDTH:.2f}"]):
        print(f"{r['rating']:11s} Stimme {r['vocal_0.15']:4.0%}  Musik {r['music_0.15']:4.0%}  "
              f"Stereo {r['stereo']:.2f}  {r['song']}")
    for r in rows:
        if "skip" in r:
            print(f"übersprungen: {r['song']} ({r['skip']})")
    counts = {k: sum(r.get("rating") == k for r in rows) for k in ("geeignet", "grenzwertig", "ungeeignet")}
    print(counts, f"-> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
