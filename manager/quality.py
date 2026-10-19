"""Problem list per song ("Baustellen"): [{"level": "error"|"warn"|"info", "code", "text"}]."""
import re

import store


def written() -> dict:
    """PS3 songs replaced/added by the manager (ps3write.py): {ps3 id: {time, source}}."""
    return store.load("ps3_written", {})

GAP_WARN_MS = 50      # UltraStar #GAP rounding error reported by us_to_ps4.py
MIN_HEIGHT = 400      # below: low-resolution video (PS3 standard is 720x404)
BOOST_WARN_DB = 8     # loudness raised by more than this: noisy source likely


def _gain(loud: str) -> float | None:
    m = re.search(r"\(([+-][\d.]+) dB\)", loud or "")
    if m:
        return float(m.group(1))
    m = re.search(r"(-?[\d.]+) LUFS -> (-?[\d.]+) LUFS", loud or "")
    return float(m.group(2)) - float(m.group(1)) if m else None


def issues(s: dict) -> list[dict]:
    out = []

    def add(level, code, text):
        out.append({"level": level, "code": code, "text": text})

    reports = [p.get("report", {}) for p in s["pkgs"].values()]
    us = s["sources"].get("ultrastar") or {}
    if us.get("new"):
        add("warn", "new", "Neuer UltraStar-Song, noch nicht umgewandelt"
            + (" (Duett – Konverter unterstützt P1/P2 noch nicht)" if us.get("duet") else ""))
    elif not s["pkg"]:
        why = next((r.get("skip") or r.get("error") for r in reports if r.get("skip") or r.get("error")), "")
        add("error", "nopkg", "Kein PS4-Paket" + (f": {why}" if why else ""))
    for r in reports:
        if r.get("error"):
            add("error", "build", f"Letzter Bau fehlgeschlagen: {r['error'][:160]}")
    us = s["sources"].get("ultrastar")
    if us and not us.get("exists"):
        add("warn", "usmissing", "UltraStar-Ordner fehlt")
    if us and us.get("exists") and not us.get("cover"):
        add("warn", "nocover", "UltraStar-Song ohne Cover")
    rep = (s["pkg"] or {}).get("report", {})
    m = re.match(r"([+-]?\d+) ms", rep.get("gap_error", ""))
    if m and abs(int(m.group(1))) >= GAP_WARN_MS:
        add("warn", "timing", f"Timing-Rundungsfehler {rep['gap_error']} (GAP prüfen)")
    size = rep.get("size") or s["meta"].get("size") or ""
    src_video = rep.get("video", "")
    m = re.match(r"(\d+)x(\d+)", size) or re.match(r"(\d+)x(\d+) ->", src_video)
    if m and int(m.group(2)) < MIN_HEIGHT:
        add("info", "lowres", f"Video nur {m.group(1)}×{m.group(2)}")
    g = _gain(rep.get("loudness", ""))
    if g is not None and g > BOOST_WARN_DB:
        add("info", "quiet", f"Ton um {g:+.1f} dB angehoben (leise Quelle)")
    lib = s["sources"].get("ps3lib", {})
    if (lib.get("hyphens") or 0) > 0.6 and str(lib.get("id")) not in written():
        add("warn", "syllables", "PS3-Fassung (Toolbox): Silbentrennung fehlerhaft, Songtext ohne Leerzeichen"
            + (" – mit „Auf PS3 ersetzen“ aus UltraStar neu übertragen" if "ultrastar" in s["sources"] else ""))
    u = s.get("usdb")
    if u and u.get("update"):
        import datetime
        when = datetime.datetime.fromtimestamp(u["update"]["lastchange"]).strftime("%d.%m.%Y")
        add("warn", "usdbupdate", f"Neue Version bei USDB vom {when} – im Detailfenster „Neu von USDB laden“")
    if u:
        if u.get("votes", 0) >= 3 and u.get("rating", 5) < 3:
            add("warn", "usdbrating", f"USDB-Bewertung nur {u['rating']:g} Sterne ({u['votes']} Stimmen)")
        if u.get("problem_hints"):
            add("info", "usdbcomments", f"USDB-Kommentare melden Probleme ({len(u['problem_hints'])}): "
                + "; ".join(c["text"][:70] for c in u["problem_hints"][:2]))
        if u.get("gap_hints"):
            add("info", "usdbgap", "USDB-Kommentar nennt anderen GAP: "
                + ", ".join(f"{g['gap']} ms ({g['user']})" for g in u["gap_hints"][:3]) + " – im Timing-Regler prüfen")
    if s.get("dupes"):
        add("warn", "dupe", "Mögliche Dublette von ID " + ", ".join(map(str, s["dupes"])))
    if s["id"] > 0 and (not s.get("editions") or any(e.startswith("unbekannt") for e in s["editions"])):
        add("info", "noedition", "Edition unbekannt")
    return out
