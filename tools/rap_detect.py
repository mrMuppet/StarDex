"""Find rap passages in UltraStar songs that are not marked as rap (R/G): lines whose notes nearly all
share one pitch. That is how Sony writes rap too (one pitch per rap line, Rap="Yes").

A line counts as monotone when it has >= MIN_NOTES normal/golden notes and >= SHARE of its sung time sits
on a single pitch (+-1 semitone). Isolated monotone lines inside a sung song are ignored unless the
neighbouring line is monotone too (a single held-note chant is not rap), or the song has a rap run anyway.

  python rap_detect.py [SONG_DIR ...]      default: all songs, prints candidates
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from us_to_ps4 import parse  # noqa: E402

import local_config  # noqa: E402
US_ROOT = local_config.path("ultrastar_dir")
MIN_NOTES = 4
SHARE = 0.85
MIN_RATE = 4.0      # syllables per second: rap is dense (sung monotone lines in ballads: ~2/s)
MAX_NOTE = 0.40     # s: no held notes in rap (0.30 missed Holland lines with one 0.38 s note)


def monotone(line, tick: float = 0.0) -> bool:
    """tick (s per UltraStar beat) > 0 also checks syllable rate and note length."""
    notes = [n for n in line if n["kind"] in (":", "*")]
    if len(notes) < MIN_NOTES or any(n["kind"] in ("R", "G") for n in line):
        return False
    dur = Counter()
    for n in notes:
        dur[n["pitch"]] += max(1, n["len"])
    top = max(dur, key=dur.get)
    near = sum(v for p, v in dur.items() if abs(p - top) <= 1)
    if near / sum(dur.values()) < SHARE:
        return False
    if tick:
        span = (line[-1]["start"] + line[-1]["len"] - line[0]["start"]) * tick
        if len(line) / span < MIN_RATE or max(n["len"] for n in line) * tick > MAX_NOTE:
            return False
    return True


def rap_lines(lines, tick: float = 0.0) -> set[int]:
    mono = [monotone(ln, tick) for ln in lines]
    keep = set()
    for i, m in enumerate(mono):
        if m and ((i > 0 and mono[i - 1]) or (i + 1 < len(mono) and mono[i + 1])):
            keep.add(i)
    if keep:  # a song with a rap run: single monotone lines are rap as well
        keep |= {i for i, m in enumerate(mono) if m}
    return keep


def main(dirs):
    for d in dirs:
        try:
            head, lines, duet = parse(next(Path(d).glob("*.txt")))
        except Exception:  # noqa: BLE001
            continue
        if duet:
            continue
        r = rap_lines(lines, 60.0 / (float(head["BPM"].replace(",", ".")) * 4))
        if r:
            words = sum(len(lines[i]) for i in r)
            total = sum(len(ln) for ln in lines)
            print(f"{len(r):3d}/{len(lines):3d} Zeilen ({words / total:4.0%} der Noten)  {Path(d).name}")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(p for p in US_ROOT.iterdir() if p.is_dir()))
