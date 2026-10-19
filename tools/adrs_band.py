"""Estimate the ADRS frequency band of the lead vocal from the mix alone, using the melody timing.

Idea: the melody says when the lead vocal sings. Average spectrum while singing minus the average spectrum
in instrumental stretches (>= GAP s away from any sung note) = vocal spectrum estimate. From that:
  cum95 : frequency below which 95 % of the vocal's (centre) energy lies
  ratio : highest 1/6-octave band where the vocal still adds >= RATIO of the instrumental level

  python adrs_band.py song MIX.mp4 MELODY.xml       one song, prints the band
  python adrs_band.py calibrate [N]                 compare with Sony's HighShelf in the PS3 library
"""
import glob
import json
import re
import statistics as st
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

SR = 48000
NFFT = 4096
HOP = 2048
GAP = 1.0
RATIO = 0.25
import local_config  # noqa: E402
EXPORT = str(local_config.path("ps3_export_dir"))


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)


def sung_intervals(melody_xml):
    """(start, end) seconds of every sung note of the first track (SingStar melody.xml)."""
    t = open(melody_xml, encoding="utf-8", errors="replace").read()
    head = re.search(r"<MELODY[^>]*>", t).group()
    tempo = float(re.search(r'Tempo="([\d.]+)"', head).group(1))
    per_beat = 8 if "Demisemiquaver" in head else 4
    tick = 60.0 / (tempo * per_beat)
    tracks = [m.start() for m in re.finditer(r"<TRACK\b", t)]
    if len(tracks) > 1:
        t = t[:tracks[1]]
    pos, out = 0, []
    for m in re.finditer(r'<NOTE MidiNote="(\d+)" Duration="(\d+)"', t):
        note, dur = int(m.group(1)), int(m.group(2))
        if note > 0:
            out.append((pos * tick, (pos + dur) * tick))
        pos += dur
    return out


def spectra(x, intervals):
    """Mean power spectra (mid and centre) for sung and instrumental frames."""
    n = (len(x) - NFFT) // HOP
    t = (np.arange(n) * HOP + NFFT / 2) / SR
    sung = np.zeros(n, bool)
    near = np.zeros(n, bool)
    for a, b in intervals:
        sung |= (t >= a + 0.03) & (t <= b - 0.03)
        near |= (t >= a - GAP) & (t <= b + GAP)
    inst = ~near & (t > 1) & (t < t[-1] - 1)
    win = np.hanning(NFFT).astype(np.float32)
    acc = {k: np.zeros(NFFT // 2 + 1) for k in ("ms", "mi", "cs", "ci")}
    cnt = {"s": 0, "i": 0}
    for i in range(0, n, 256):
        idx = np.arange(i, min(n, i + 256))
        sel_s, sel_i = sung[idx], inst[idx]
        if not (sel_s.any() or sel_i.any()):
            continue
        fr = np.stack([x[j * HOP:j * HOP + NFFT] for j in idx]) * win[None, :, None]
        L, R = np.fft.rfft(fr[:, :, 0], axis=1), np.fft.rfft(fr[:, :, 1], axis=1)
        mid = np.abs(L + R) ** 2 / 4
        # centre part: energy the two channels share in phase (what an azimuth-0 filter can reach)
        cen = np.maximum(0, np.real(L * np.conj(R)))
        for key, sel in (("s", sel_s), ("i", sel_i)):
            if sel.any():
                acc["m" + key] += mid[sel].sum(0)
                acc["c" + key] += cen[sel].sum(0)
                cnt[key] += int(sel.sum())
    if cnt["s"] < 50 or cnt["i"] < 50:
        return None
    return {k: v / cnt[k[1]] for k, v in acc.items()}, cnt


def bands(S, I, f):
    """Collapse to 1/6-octave bands 100 Hz .. 20 kHz."""
    edges = 100 * 2 ** (np.arange(0, 46) / 6)
    edges = edges[edges <= 20000]
    s = np.array([S[(f >= a) & (f < b)].mean() for a, b in zip(edges[:-1], edges[1:])])
    i = np.array([I[(f >= a) & (f < b)].mean() for a, b in zip(edges[:-1], edges[1:])])
    return np.sqrt(edges[:-1] * edges[1:]), s, i


def estimate(x, intervals):
    r = spectra(x, intervals)
    if r is None:
        return None
    sp, cnt = r
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    res = {}
    for kind in ("m", "c"):
        fc, s, i = bands(sp[kind + "s"], sp[kind + "i"], f)
        v = np.maximum(s - i, 0)
        c = np.cumsum(v) / max(v.sum(), 1e-20)
        res[kind + "_lo5"] = float(fc[np.searchsorted(c, 0.05)])
        res[kind + "_cum90"] = float(fc[min(len(fc) - 1, np.searchsorted(c, 0.90))])
        res[kind + "_cum95"] = float(fc[min(len(fc) - 1, np.searchsorted(c, 0.95))])
        ok = np.where(v >= RATIO * np.maximum(i, 1e-20))[0]
        ok = ok[fc[ok] > 1000]
        res[kind + "_ratio"] = float(fc[ok.max()]) if len(ok) else 1000.0
    res["frames"] = cnt
    return res


def sony_band(melody_xml):
    t = open(melody_xml, encoding="utf-8", errors="replace").read()
    sets = [dict(re.findall(r'(\w+)="([^"]*)"', a)) for a in re.findall(r"<ADRS ([^>]*)/>", t)]
    sets = [s for s in sets if float(s["Width"]) > 0]
    if not sets:
        return None
    return st.median(float(s["LowShelf"]) for s in sets), st.median(float(s["HighShelf"]) for s in sets)


def calib_one(d):
    mel = sorted(glob.glob(d + "/melody*.xml"))[0]
    sb = sony_band(mel)
    if not sb or not Path(d, "video.mp4").exists():
        return None
    try:
        e = estimate(load(Path(d, "video.mp4")), sung_intervals(mel))
    except Exception as ex:  # noqa: BLE001
        return {"id": Path(d).name, "error": str(ex)}
    if e is None:
        return None
    return {"id": Path(d).name, "sony_lo": sb[0], "sony_hi": sb[1], **e}


def calibrate(limit=None):
    dirs = [d for d in sorted(glob.glob(EXPORT + "/*")) if Path(d).is_dir()]
    dirs = [d for d in dirs if any("<ADRS" in open(m, encoding="utf-8", errors="replace").read()
                                   for m in glob.glob(d + "/melody*.xml")[:1])]
    if limit:
        dirs = dirs[:limit]
    with ProcessPoolExecutor(6) as ex:
        rows = [r for r in ex.map(calib_one, dirs) if r]
    out = Path(__file__).resolve().parent.parent / "build" / "adrs_calibration.json"
    out.write_text(json.dumps(rows, indent=1))
    rows = [r for r in rows if "error" not in r]
    print(f"{len(rows)} songs -> {out}")
    hi = np.array([r["sony_hi"] for r in rows])
    for k in ("m_cum90", "m_cum95", "m_ratio", "c_cum90", "c_cum95", "c_ratio"):
        e = np.array([r[k] for r in rows])
        lr = np.log2(e / hi)
        corr = np.corrcoef(np.log(e), np.log(hi))[0, 1]
        print(f"{k:8s} corr(log) {corr:+.2f}  median ratio {2 ** np.median(lr):.2f}  "
              f"within x1.5 {np.mean(np.abs(lr) < np.log2(1.5)):.0%}  within x2 {np.mean(np.abs(lr) < 1):.0%}")
    lo = np.array([r["sony_lo"] for r in rows])
    for k in ("m_lo5", "c_lo5"):
        e = np.array([r[k] for r in rows])
        print(f"{k:8s} median {np.median(e):.0f} Hz vs Sony {np.median(lo):.0f} Hz, "
              f"corr(log) {np.corrcoef(np.log(e), np.log(np.maximum(lo, 50)))[0, 1]:+.2f}")


if __name__ == "__main__":
    if sys.argv[1] == "calibrate":
        calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        print(json.dumps(estimate(load(sys.argv[2]), sung_intervals(sys.argv[3])), indent=1))
