"""How much of the lead vocal and of the music a given ADRS window (azimuth +- width, band) reaches.

Per STFT bin: pan position p = (|R|-|L|)/(|R|+|L|) (the game's azimuth scale: Complicated, It's My Life
work with their values). Vocal = sung frames minus instrumental frames (melody timing); music = the
instrumental frames. 'vocal' = share of vocal energy inside the window, 'music' = share of music
energy inside the window (what gets lost when the reduction is on).

  python adrs_fit.py calibrate          Sony's PS3 songs: reach of Sony's own settings + songs Sony left out
"""
import glob
import json
import re
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import adrs_band as ab  # noqa: E402

EDGES = np.linspace(-1, 1, 81)
CENT = (EDGES[:-1] + EDGES[1:]) / 2


def pan_energy(x, intervals, lo, hi):
    """Energy histograms over pan position (band lo..hi) for vocal (sung - instrumental) and music."""
    n = (len(x) - ab.NFFT) // ab.HOP
    t = (np.arange(n) * ab.HOP + ab.NFFT / 2) / ab.SR
    sung, near = np.zeros(n, bool), np.zeros(n, bool)
    for a, b in intervals:
        sung |= (t >= a + .03) & (t <= b - .03)
        near |= (t >= a - ab.GAP) & (t <= b + ab.GAP)
    inst = ~near & (t > 1) & (t < t[-1] - 1)
    f = np.fft.rfftfreq(ab.NFFT, 1 / ab.SR)
    band = (f >= lo) & (f <= hi)
    w = np.hanning(ab.NFFT)
    H, C = {"s": np.zeros(80), "i": np.zeros(80)}, {"s": 0, "i": 0}
    for i in range(0, n, 256):
        idx = np.arange(i, min(n, i + 256))
        if not (sung[idx].any() or inst[idx].any()):
            continue
        fr = np.stack([x[j * ab.HOP:j * ab.HOP + ab.NFFT] for j in idx]) * w[None, :, None]
        L = np.abs(np.fft.rfft(fr[:, :, 0], axis=1))[:, band]
        R = np.abs(np.fft.rfft(fr[:, :, 1], axis=1))[:, band]
        p, e = (R - L) / (R + L + 1e-12), L ** 2 + R ** 2
        for k, sel in (("s", sung[idx]), ("i", inst[idx])):
            if sel.any():
                H[k] += np.histogram(p[sel], EDGES, weights=e[sel])[0]
                C[k] += int(sel.sum())
    if C["s"] < 50 or C["i"] < 50:
        return None
    music = H["i"] / C["i"]
    vocal = np.maximum(H["s"] / C["s"] - music, 0)
    return vocal / max(vocal.sum(), 1e-20), music / max(music.sum(), 1e-20)


def reach(hists, azimuth, width):
    vocal, music = hists
    m = np.abs(CENT - azimuth) <= max(width, 0.0125)
    return float(vocal[m].sum()), float(music[m].sum())


def sony_sets(melody):
    t = open(melody, encoding="utf-8", errors="replace").read()
    sets = [dict(re.findall(r'(\w+)="([^"]*)"', a)) for a in re.findall(r"<ADRS ([^>]*)/>", t)]
    return [s for s in sets if float(s["Width"]) > 0], 'shouldHaveAdrs="Yes"' in t


def calib_one(d):
    mels = sorted(glob.glob(d + "/melody*.xml"))
    if not mels:
        return None
    mel = mels[0]
    sets, should = sony_sets(mel)
    if not Path(d, "video.mp4").exists() or not (sets or should):
        return None
    if sets:
        az = st.median(float(s["Azimuth"]) for s in sets)
        wd = st.median(float(s["Width"]) for s in sets)
        lo = st.median(float(s["LowShelf"]) for s in sets)
        hi = st.median(float(s["HighShelf"]) for s in sets)
    else:
        az, wd, lo, hi = 0.0, 0.15, 312.5, 6250
    try:
        h = pan_energy(ab.load(Path(d, "video.mp4")), ab.sung_intervals(mel), lo, hi)
    except Exception as ex:  # noqa: BLE001
        return {"id": Path(d).name, "error": str(ex)}
    if h is None:
        return None
    v, m = reach(h, az, wd)
    v0, m0 = reach(h, 0.0, 0.15)
    peak = float(CENT[np.argmax(h[0])])
    return {"id": Path(d).name, "sony": bool(sets), "az": az, "width": wd, "lo": lo, "hi": hi,
            "vocal": v, "music": m, "vocal_c15": v0, "music_c15": m0, "peak": peak}


def calibrate():
    dirs = [d for d in sorted(glob.glob(ab.EXPORT + "/*")) if Path(d).is_dir()]
    with ProcessPoolExecutor(6) as ex:
        rows = [r for r in ex.map(calib_one, dirs) if r and "error" not in r]
    out = Path(__file__).resolve().parent.parent / "build" / "adrs_fit.json"
    out.write_text(json.dumps(rows, indent=1))
    yes = [r for r in rows if r["sony"]]
    no = [r for r in rows if not r["sony"]]
    q = lambda v: "/".join(f"{x:.0%}" for x in np.percentile(v, [10, 25, 50, 75, 90]))
    print(f"-> {out}\nSony set ADRS ({len(yes)} songs), reach of Sony's own window, p10/25/50/75/90:")
    print(f"  vocal {q([r['vocal'] for r in yes])}   music {q([r['music'] for r in yes])}")
    print(f"  |Sony azimuth - vocal peak|: median {np.median([abs(r['az'] - r['peak']) for r in yes]):.3f}")
    print(f"Centre window 0 +- 0.15, band 312-6250:")
    print(f"  Sony used ADRS  ({len(yes)}): vocal {q([r['vocal_c15'] for r in yes])}  music {q([r['music_c15'] for r in yes])}")
    print(f"  Sony left out   ({len(no)}): vocal {q([r['vocal_c15'] for r in no])}  music {q([r['music_c15'] for r in no])}")


if __name__ == "__main__":
    calibrate()
