"""Estimate SingStar ADRS-like parameters from a separated vocal stem (+ instrumental stem).

  python vocal_adrs.py VOCALS.mp3 [INSTRUMENTAL.mp3]

Per 5 s window where the vocal is active: azimuth (-1 left .. +1 right, from L/R energy), width (share of
side energy in the vocal), frequency band (5th..95th percentile of vocal spectral energy, 100 Hz..20 kHz),
and how much of that band the instrumental occupies (overlap = how much music a centre/band filter would hit).
"""
import subprocess
import sys

import numpy as np

SR = 24000


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)


def band(x):
    spec = np.abs(np.fft.rfft(x.mean(axis=1) * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = (f >= 100)
    c = np.cumsum(spec[m]); c /= c[-1]
    return f[m][np.searchsorted(c, 0.05)], f[m][np.searchsorted(c, 0.95)]


def main(vp, ip=None):
    v = load(vp)
    ins = load(ip) if ip else None
    win = 5 * SR
    rows = []
    for s in range(0, len(v) - win, win):
        seg = v[s:s + win]
        rms = np.sqrt((seg ** 2).mean())
        if rms < 0.01:
            continue
        l, r = np.sqrt((seg[:, 0] ** 2).mean()), np.sqrt((seg[:, 1] ** 2).mean())
        az = (r - l) / (r + l)
        mid, side = (seg[:, 0] + seg[:, 1]) / 2, (seg[:, 0] - seg[:, 1]) / 2
        width = np.sqrt((side ** 2).mean()) / max(1e-9, np.sqrt((mid ** 2).mean()))
        lo, hi = band(seg)
        ov = None
        if ins is not None and s + win <= len(ins):
            iseg = ins[s:s + win]
            imid = (iseg[:, 0] + iseg[:, 1]) / 2
            sp = np.abs(np.fft.rfft(imid)) ** 2
            f = np.fft.rfftfreq(len(imid), 1 / SR)
            ov = sp[(f >= lo) & (f <= hi)].sum() / sp[f >= 20].sum()
        rows.append((s / SR, az, width, lo, hi, ov))
    for t, az, w, lo, hi, ov in rows:
        print(f"{t:6.0f}s  azimuth {az:+.3f}  width {w:.3f}  band {lo:6.0f}-{hi:6.0f} Hz"
              + (f"  instrumental energy in band {ov:.0%}" if ov is not None else ""))
    a = np.array([r[1:5] for r in rows])
    print(f"\nsummary: azimuth {a[:,0].mean():+.3f} (sd {a[:,0].std():.3f}), width {a[:,1].mean():.3f} "
          f"(sd {a[:,1].std():.3f}), band median {np.median(a[:,2]):.0f}-{np.median(a[:,3]):.0f} Hz, "
          f"active windows {len(rows)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
