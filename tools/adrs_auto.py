"""Per-segment ADRS on/off from separated stems (Demucs: vocals + no_vocals).

Every reduced segment gets the same window: azimuth 0, width WIDTH (0.15). Measured windows narrower than
that had little effect on the PS4 (Kaleo/Adele with 0.05-0.10, 28.09.), 0.15 worked (Matilda, Valerie);
Sony's own widths start at ~0.11 as well. Only songs rated "geeignet" in build/adrs_us_scan.json get ADRS.
For a time segment: pan position p = (|R|-|L|)/(|R|+|L|) of every STFT bin in the band, weighted by energy.
The segment gets no reduction when the vocal is too wide (75 % of its energy needs more than MAX_W around
the centre), when the window would also take more than MAX_MUSIC of the music, or when there is hardly any
vocal.
Stems: build/stems/htdemucs/<audio file stem>/vocals.mp3, no_vocals.mp3 (see docs/TECHNIK.md).
"""
import math
from pathlib import Path

import numpy as np

import adrs_band as ab

STEMS = Path(__file__).resolve().parent.parent / "build" / "stems" / "htdemucs"
COVER = 0.75
WIDTH = 0.15
MAX_W = 32 / 128
MAX_MUSIC = 0.50
SCAN = STEMS.parent.parent / "adrs_us_scan.json"


def suitable(song_folder: str) -> bool:
    """Song rated "geeignet" by adrs_us_scan.py (centre window reaches the vocal, spares the music)."""
    import json
    rows = json.loads(SCAN.read_text("utf-8")) if SCAN.exists() else []
    return any(r["song"] == song_folder and r.get("rating") == "geeignet" for r in rows)


def stem_dir(audio: Path) -> Path | None:
    d = STEMS / audio.stem
    return d if (d / "vocals.mp3").exists() or (d / "vocals.wav").exists() else None


def _load(d: Path, name: str):
    f = d / f"{name}.mp3"
    return ab.load(f if f.exists() else d / f"{name}.wav")


class StemShaper:
    def __init__(self, d: Path, low: float, high: float):
        self.v, self.m = _load(d, "vocals"), _load(d, "no_vocals")
        f = np.fft.rfftfreq(ab.NFFT, 1 / ab.SR)
        self.band = (f >= low) & (f <= high)
        self.win = np.hanning(ab.NFFT)[:, None]
        self.log = []

    def _pans(self, x, a, b):
        s, e = int(a * ab.SR), min(len(x), int(b * ab.SR))
        starts = range(s, max(s + 1, e - ab.NFFT), ab.HOP)
        frames = [x[j:j + ab.NFFT] for j in starts if j + ab.NFFT <= len(x)]
        if not frames:  # segment beyond the end of the audio (melody longer than the stem)
            return np.zeros(0), np.zeros(0)
        fr = np.stack(frames) * self.win[None]
        L = np.abs(np.fft.rfft(fr[:, :, 0], axis=1))[:, self.band].ravel()
        R = np.abs(np.fft.rfft(fr[:, :, 1], axis=1))[:, self.band].ravel()
        return (R - L) / (R + L + 1e-12), L ** 2 + R ** 2

    def __call__(self, a: float, b: float):
        pv, ev = self._pans(self.v, a, b)
        pm, em = self._pans(self.m, a, b)
        if ev.sum() <= 0:  # silent vocal stem here
            self.log.append({"start": round(a, 1), "end": round(b, 1), "azimuth": 0.0, "width": 0.0, "music": 0.0,
                             "level_db": -99.0, "off": "kaum Gesang"})
            return 0.0, 0.0
        level = 10 * math.log10(ev.sum() / max(em.sum(), 1e-20))
        o = np.argsort(pv)
        centre = float(pv[o][np.searchsorted(np.cumsum(ev[o]) / ev.sum(), 0.5)])
        d = np.abs(pv)
        o = np.argsort(d)
        spread = float(d[o][min(len(d) - 1, np.searchsorted(np.cumsum(ev[o]) / ev.sum(), COVER))])
        music = float(em[np.abs(pm) <= WIDTH].sum() / em.sum())
        why = ("Stimme zu breit" if spread > MAX_W else "zu viel Musik im Fenster" if music > MAX_MUSIC
               else "kaum Gesang" if level < -12 else "")
        self.log.append({"start": round(a, 1), "end": round(b, 1), "azimuth": round(centre, 3),
                         "width": round(spread, 3), "music": round(music, 2), "level_db": round(level, 1),
                         "off": why})
        return (0.0, 0.0) if why else (0.0, WIDTH)
