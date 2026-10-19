"""USDB (usdb.animux.de) search for the wishlist. USDB needs a login for searching; the user enters
name/password in the app settings (stored locally in data/secrets.json, only sent to usdb.animux.de).

No official API: the login form posts user/pass/login to the start page (PHPSESSID cookie); the result list
(?link=list) has one row per song: <tr class="list_trN" data-songid="ID"> with the cells
Sample | Cover | Interpret | Titel | Genre | Jahr | Edition | Goldene Noten | Sprache | Creator | Bewertung (star
images) | Aufrufe. The page nests tables, so only rows with data-songid are read.
"""
import html
import re
import threading

import requests

import store

# USDB allows one login session per user: downloads and info fetches run one after the other (RLock: the
# info fetch runs inside the download job's thread)
JOBS = threading.RLock()

BASE = "https://usdb.animux.de/"
COLS = ("sample", "cover", "artist", "title", "genre", "year", "edition", "golden", "language", "creator",
        "rating", "views")
_session: requests.Session | None = None


class UsdbError(Exception):
    pass


def _login() -> requests.Session:
    global _session
    sec = store.load("secrets", {})
    if not sec.get("usdb_user") or not sec.get("usdb_pass"):
        raise UsdbError("USDB-Zugangsdaten fehlen (Einstellungen)")
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (SingStar-Song-Manager, private)"
    s.post(BASE, data={"user": sec["usdb_user"], "pass": sec["usdb_pass"], "login": "Login"}, timeout=20)
    _session = s
    return s


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def parse(page: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<tr class="list_tr\d" data-songid="(\d+)".*?</tr>', page, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", m.group(0), re.S)
        if len(tds) < len(COLS):
            continue
        c = dict(zip(COLS, tds))
        sid = int(m.group(1))
        stars = c["rating"].count("images/star.png") + 0.5 * c["rating"].count("half_star")
        out.append({"id": sid, "artist": _text(c["artist"]), "title": _text(c["title"]),
                    "genre": _text(c["genre"]), "year": _text(c["year"]), "edition": _text(c["edition"]),
                    "golden": _text(c["golden"]), "language": _text(c["language"]), "creator": _text(c["creator"]),
                    "rating": stars, "views": int(_text(c["views"]) or 0) if _text(c["views"]).isdigit() else 0,
                    "url": f"{BASE}?link=detail&id={sid}"})
    return out


PAGE = 100  # USDB returns at most 100 rows per request, more via "start"


def search(artist: str = "", title: str = "", limit: int = 1000) -> list[dict]:
    """All matches (best rated first), page by page up to `limit`."""
    s = _session or _login()
    out, seen = [], set()
    for start in range(0, limit, PAGE):
        data = {"interpret": artist, "title": title, "limit": str(PAGE), "start": str(start), "details": "1",
                "order": "rating", "ud": "desc"}
        r = s.post(BASE + "?link=list", data=data, timeout=20)
        if "not logged in" in r.text.lower():
            s = _login()
            r = s.post(BASE + "?link=list", data=data, timeout=20)
            if "not logged in" in r.text.lower():
                raise UsdbError("USDB-Anmeldung fehlgeschlagen (Name/Passwort in den Einstellungen prüfen)")
        page = [x for x in parse(r.text) if x["id"] not in seen]
        seen.update(x["id"] for x in page)
        out += page
        if len(page) < PAGE:
            break
    return out[:limit]


SENTIMENT = {"add.png": "positiv", "remove.png": "negativ", "neutral.png": "neutral"}
PROBLEM_WORDS = re.compile(r"(?i)(\bway off\b|\bnotes? (?:are |is )?(?:completely )?off\b|\bfalsch|\bwrong\b|\bfehler|"
                           r"\bbroken\b|\bkaputt|stimmt nicht|passt nicht|\bmissing\b|fehlt|out of sync|asynchron|"
                           r"too early|too late|zu früh|zu spät|überarbeitet werden|needs? (?:some )?work)")
GAP_HINT = re.compile(r"(?i)#?\bGAP\b\D{0,25}?(\d{3,6})")


def detail(sid: int) -> dict:
    """Quality info from the song page: rating + votes, views, golden notes, songcheck, upload date, creator,
    BPM/GAP and the user comments (date, user, positive/neutral/negative, text)."""
    s = _session or _login()
    r = s.get(BASE, params={"link": "detail", "id": sid}, timeout=20)
    if "not logged in" in r.text.lower():
        s = _login()
        r = s.get(BASE, params={"link": "detail", "id": sid}, timeout=20)
    page = r.text
    fields = {}
    for label, value in re.findall(r'<tr class="list_tr\d"><td>([^<]{2,40})</td><td>(.*?)</td></tr>', page, re.S):
        fields[_text(label)] = value
    rate = fields.get("Bewertung", "")
    votes = re.search(r"<b>(\d+)</b>", rate)
    out = {"id": sid, "url": f"{BASE}?link=detail&id={sid}",
           "rating": rate.count("images/star.png") + 0.5 * rate.count("half_star"),
           "votes": int(votes.group(1)) if votes else 0,
           "views": int(_text(fields.get("Aufrufe", "0")) or 0) if _text(fields.get("Aufrufe", "0")).isdigit() else 0,
           "golden": _text(fields.get("Goldene Noten", "")).startswith("Ja"),
           "songcheck": _text(fields.get("Songcheck", "")).startswith("Ja"),
           "date": _text(fields.get("Datum", "")), "creator": _text(fields.get("Hochgeladen von", "")),
           "edition": _text(fields.get("Edition", "")), "language": _text(fields.get("Sprache", "")),
           "bpm": _text(fields.get("BPM", "")), "gap": _text(fields.get("GAP", ""))}
    comments = []
    block = page[page.find("Kommentare von Benutzern"):] if "Kommentare von Benutzern" in page else ""
    for head, body in re.findall(r'<tr class="list_tr\d"><td>(\d\d\.\d\d\.\d\d - \d\d:\d\d \|.*?)</td></tr>'
                                 r'\s*<tr class="list_tr\d"><td>(.*?)</td></tr>', block, re.S):
        img = re.search(r"images/(\w+\.png)", head)
        date, _, user = _text(head).partition("|")
        text = _text(re.sub(r"<img[^>]*quote[^>]*>.*?</font>", " ", body, flags=re.S))
        comments.append({"date": date.strip(), "user": user.strip(),
                         "mood": SENTIMENT.get(img.group(1) if img else "", "neutral"), "text": text})
    out["comments"] = comments
    out["problem_hints"] = [c for c in comments if c["mood"] == "negativ" or PROBLEM_WORDS.search(c["text"])]
    out["gap_hints"] = [{"gap": int(m.group(1)), **c} for c in comments for m in [GAP_HINT.search(c["text"])] if m]
    return out
