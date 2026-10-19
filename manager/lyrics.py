"""Timed lyric lines for the browser preview: UltraStar .txt and SingStar melody.xml.

Returns [{"t": start s, "e": end s, "words": [[start s, end s, text], ...]}, ...] (first voice only).
"""
import re
from pathlib import Path

import library


def ultrastar(txt: Path, gap_ms: float | None = None) -> dict:
    head, lines, cur = {}, [], []
    for row in library.read_text(txt).splitlines():
        if row.startswith("#"):
            k, _, v = row[1:].partition(":")
            head[k.strip().upper()] = v.strip()
        elif row.strip() in ("P2", "P 2"):
            break
        elif row[:1] in ":*FRG":
            m = re.match(r"[:*FRG] +(-?\d+) +(\d+) +(-?\d+) ?(.*)$", row)
            if m:
                cur.append((int(m.group(1)), int(m.group(2)), m.group(4)))
        elif row.startswith("-") or row.startswith("E"):
            if cur:
                lines.append(cur)
            cur = []
            if row.startswith("E"):
                break
    if cur:
        lines.append(cur)
    bpm = float(head.get("BPM", "300").replace(",", "."))
    gap = float(head.get("GAP", "0").replace(",", ".")) if gap_ms is None else gap_ms
    beat = 60 / (bpm * 4)
    out = []
    for ln in lines:
        words = [[gap / 1000 + s * beat, gap / 1000 + (s + d) * beat, t] for s, d, t in ln]
        out.append({"t": words[0][0], "e": words[-1][1], "words": words})
    return {"lines": out, "gap": gap, "bpm": bpm, "videogap": float(head.get("VIDEOGAP", "0").replace(",", "."))}


def melody(xml: Path) -> dict:
    s = xml.read_text("utf-8", errors="replace")
    tempo = float(re.search(r'Tempo="([\d.]+)"', s).group(1))
    res = re.search(r'Resolution="(\w+)"', s)
    div = {"Semiquaver": 4, "Demisemiquaver": 8}.get(res.group(1) if res else "Semiquaver", 4)
    tick = 60 / tempo / div
    s = s.split("<TRACK", 2)
    body = "<TRACK".join(s[:2]) if len(s) > 2 else "<TRACK".join(s)  # first voice only
    t, out = 0.0, []
    for sent in re.findall(r"<SENTENCE[^>]*>(.*?)</SENTENCE>", body, re.S):
        words = []
        for tag in re.findall(r"<NOTE\b([^>]*)>", sent):
            a = dict(re.findall(r'(\w+)="([^"]*)"', tag))
            d = int(a.get("Duration", 0)) * tick
            if a.get("MidiNote", "0") != "0" and a.get("Lyric"):
                ly = a["Lyric"].replace("&amp;", "&")  # "Feel -" = syllable, word goes on
                words.append([t, t + d, ly[:-2] if ly.endswith(" -") else ly.rstrip() + " "])
            t += d
        if words:
            out.append({"t": words[0][0], "e": words[-1][1], "words": words})
    return {"lines": out}
