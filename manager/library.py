"""PC-side song library: merges UltraStar folders, the PS3 library export and the PS2 disc songs by PS4 song id.

The PS4 id is the common key: official ids are the same on PS2/PS3/PS4, own PS3 songs 600xx become 45xxx
(tools/songid.ps4_id), UltraStar songs have their id in song_ids.json.
"""
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import songid  # noqa: E402

import editions  # noqa: E402
import quality  # noqa: E402

NS = "{http://www.singstargame.com}"
SOURCE_ORDER = ("ultrastar", "ps3disc", "ps3lib", "ps2", "ps4pkg")  # preferred package source (disc video > Toolbox export)
DATA = Path(__file__).parent / "data"


def ps2_index(cfg: dict, force: bool = False) -> list[dict]:
    """All songs on the extracted PS2 discs (batch_ps2.candidates, incl. skip reasons), cached until the set
    of disc folders changes (a scan reads every disc, ~1 min)."""
    root = path(cfg.get("ps2_root") or "ps2")
    if not root.is_dir():
        return []
    sig = sorted(d.name for d in root.iterdir() if d.is_dir())
    cache = DATA / "ps2_index.json"
    if cache.exists() and not force:
        c = json.loads(cache.read_text("utf-8"))
        if c.get("sig") == sig:
            return c["rows"]
    import batch_ps2
    batch_ps2.PS2_ROOT, batch_ps2.EXPORT = root, path(cfg["ps3_export_dir"])
    rows = [{k: r[k] for k in ("id", "artist", "title", "disc", "skip", "iso", "lang") if k in r}
            for r in batch_ps2.candidates()]
    DATA.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"sig": sig, "rows": rows}, ensure_ascii=False), "utf-8")
    return rows


def ps3_discs(cfg: dict) -> list[dict]:
    """Imported PS3 discs (tools/disc_import.py): <ps3_imports>/<Disc>/export + disc.json."""
    root = path(cfg.get("ps3_imports") or "imports/ps3")
    dirs = sorted(root.iterdir()) if root.is_dir() else []
    console = path(cfg["console_imports"]) / "PS3"  # songs taken over from the PS3 (pull.py)
    out = []
    for d in dirs + ([console] if console.is_dir() else []):
        if (d / "export" / "songs_4_0.xml").exists():
            info = json.loads((d / "disc.json").read_text("utf-8")) if (d / "disc.json").exists() else {}
            out.append({"dir": d / "export", "name": info.get("edition") or d.name, "info": info})
    return out


PATH_KEYS = ("ultrastar_dir", "ps3_export_dir", "ps3_imports", "ps2_root", "console_imports")
PKG_SUBDIRS = {"ultrastar": "batch", "ps3disc": "batch_ps3disc", "ps3lib": "batch_ps3", "ps2": "batch_ps2"}


def load_config() -> dict:
    """config.json, overridden by the storage folders from the settings (data/settings.json "paths").
    On the first start config.json is created from config.example.json (folders under songs/ in the project)."""
    cfg_p = Path(__file__).parent / "config.json"
    if not cfg_p.exists():
        cfg_p.write_text((Path(__file__).parent / "config.example.json").read_text("utf-8"), "utf-8")
        for k in PATH_KEYS:
            path(json.loads(cfg_p.read_text("utf-8"))[k]).mkdir(parents=True, exist_ok=True)
    cfg = json.loads(cfg_p.read_text("utf-8"))
    try:
        paths = json.loads((DATA / "settings.json").read_text("utf-8")).get("paths", {})
    except (OSError, ValueError):
        paths = {}
    for k in PATH_KEYS:
        if paths.get(k):
            cfg[k] = paths[k]
    cfg["pkg_root"] = paths.get("pkg_root") or str(ROOT / "build")
    cfg["pkg_dirs"] = {k: str(Path(cfg["pkg_root"]) / v) for k, v in PKG_SUBDIRS.items()}
    cfg["pkg_dirs"]["ps4pkg"] = str(path(cfg["console_imports"]) / "PS4")  # packages taken over from the PS4
    return cfg


def path(cfg_value: str) -> Path:
    p = Path(cfg_value)
    return p if p.is_absolute() else ROOT / p


def song_ids(cfg: dict) -> dict:
    """song_ids.json ({"#ARTIST - #TITLE": id}); empty until the first UltraStar song gets an id."""
    p = path(cfg["song_ids"])
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def norm(text: str) -> str:
    """Comparison key for artist/title: lower case, no accents, no punctuation, no feat./version suffixes."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", t)
    t = re.sub(r"\b(feat|ft|featuring)\b.*", "", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def ps3_id_for(ps4: int) -> int:
    """Inverse of songid.ps4_id for own songs (45xxx on the PS4 <-> 60xxx on the PS3, as tools/to_ps3.py)."""
    return ps4 - songid.CUSTOM_BASE + 60000 if ps4 >= songid.CUSTOM_BASE else ps4


TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "´": "'", "`": "'", "“": '"', "”": '"',
                            "„": '"', "–": "-", "—": "-", "…": "...", " ": " "})  # as us_to_ps4.read_txt


def read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc).translate(TYPOGRAPHY)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1").translate(TYPOGRAPHY)


def us_header(folder: Path) -> dict:
    txts = sorted(folder.glob("*.txt"))
    if not txts:
        return {}
    head = {}
    for line in read_text(txts[0]).splitlines():
        if not line.startswith("#"):
            break
        k, _, v = line[1:].partition(":")
        head[k.strip().upper()] = v.strip()
    return head


def hyphen_ratio(song_dir: Path) -> float | None:
    """Share of syllables marked 'word goes on' (Lyric="xx -"). Official songs: 0.1-0.4; the Toolbox wrote it
    for nearly every syllable of own songs (0.8-0.9) -> lyrics shown without spaces."""
    for n in ("melody_4.xml", "melody.xml"):
        p = song_dir / n
        if p.exists():
            ly = re.findall(r'Lyric="([^"]+)"', p.read_bytes().decode("utf-8", "replace"))
            return round(sum(x.endswith(" -") for x in ly) / len(ly), 2) if ly else None
    return None


def library_txt(folder: Path) -> str:
    txts = sorted(folder.glob("*.txt"))
    return read_text(txts[0]) if txts else ""


def parse_songs_xml(data: bytes) -> dict[int, dict]:
    """songs_*.xml (PS3 export or PS3 console) -> {ps3 id: {artist, title, gamever}}."""
    out = {}
    for s in ET.fromstring(data).iter(NS + "SONG"):
        sid = int(s.get("ID"))
        out[sid] = {"title": (s.findtext(NS + "TITLE") or "").strip(),
                    "artist": (s.findtext(NS + "PERFORMANCE_NAME") or "").strip(),
                    "gamever": (s.findtext(NS + "ORIG_GAMEVER") or "").strip(),
                    "type": s.get("PERFORMANCE_TYPE", "")}
        v = s.find(NS + "VIDEO")
        if v is not None and v.get("HEIGHT"):
            out[sid]["size"] = f'{v.get("WIDTH")}x{v.get("HEIGHT")}'
            out[sid]["length"] = float(v.get("LENGTH") or 0)
        g = s.find(NS + "INFO")
        if g is not None:
            out[sid]["genres"] = [x.text for x in g.findall(NS + "GENRE") if x.text]
            out[sid]["year"] = (g.findtext(NS + "RELEASE_DATE") or "")[:4]
            out[sid]["language"] = g.findtext(NS + "VOXLANGUAGE") or ""
    return out


def pkg_index(cfg: dict) -> dict[str, dict[int, dict]]:
    """{source: {ps4 id: {file, mb, report}}} from the batch output folders."""
    out = {}
    for src, d in cfg["pkg_dirs"].items():
        d = path(d)
        reports = {}
        if (d / "report.json").exists():
            for r in json.loads((d / "report.json").read_text("utf-8", errors="replace")):
                if r.get("label"):
                    reports[r["label"]] = r
        pk = {}
        for f in (d / "pkgs").glob("*-CUSA00033_*-*.pkg"):
            label = f.stem.split("-")[-1]
            try:
                sid = songid.id_from_label(label)
            except ValueError:
                continue
            pk[sid] = {"file": str(f), "label": label, "mb": round(f.stat().st_size / 2**20),
                       "report": reports.get(label, {})}
        out[src] = pk
    return out


def build(cfg: dict) -> dict[int, dict]:
    songs: dict[int, dict] = {}

    def song(sid: int, artist: str, title: str) -> dict:
        s = songs.get(sid)
        if s is None:
            s = songs[sid] = {"id": sid, "label": songid.label_for(sid) if sid > 0 else "",
                              "ps3_id": ps3_id_for(sid) if sid > 0 else None,
                              "artist": artist, "title": title, "sources": {}, "pkgs": {}, "meta": {}}
        return s

    # PS3 library export (PC copy)
    exp = path(cfg["ps3_export_dir"])
    if (exp / "songs_4_0.xml").exists():
        for ps3, m in parse_songs_xml((exp / "songs_4_0.xml").read_bytes()).items():
            s = song(songid.ps4_id(ps3), m["artist"], m["title"])
            s["ps3_id"] = ps3
            s["sources"]["ps3lib"] = {"id": ps3, "gamever": m["gamever"], "dir": str(exp / str(ps3))}
            if ps3 >= 60000:  # own Toolbox songs: check the word separation of the melody
                s["sources"]["ps3lib"]["hyphens"] = hyphen_ratio(exp / str(ps3))
            s["meta"].setdefault("type", m["type"])
            if m["gamever"]:
                s["meta"]["origin"] = m["gamever"]
            for k in ("size", "year", "language"):
                if m.get(k):
                    s["meta"].setdefault(k, m[k])
            if m.get("genres"):
                s["meta"].setdefault("genre", ", ".join(m["genres"]))

    # imported PS3 discs (original disc video, preferred over the Toolbox export)
    disc_editions: dict[int, list[str]] = {}
    for disc in ps3_discs(cfg):
        for ps3, m in parse_songs_xml((disc["dir"] / "songs_4_0.xml").read_bytes()).items():
            if not (disc["dir"] / str(ps3)).is_dir():
                continue  # listed on the disc but media on another disc (disc swap)
            s = song(songid.ps4_id(ps3), m["artist"], m["title"])
            s["ps3_id"] = ps3
            s["sources"].setdefault("ps3disc", {"id": ps3, "dir": str(disc["dir"] / str(ps3)),
                                                "export": str(disc["dir"]), "disc": disc["name"]})
            disc_editions.setdefault(s["id"], []).append(disc["name"])
            for k in ("size", "year", "language"):
                if m.get(k):
                    s["meta"].setdefault(k, m[k])
            if m.get("genres"):
                s["meta"].setdefault("genre", ", ".join(m["genres"]))

    # packages taken over from the PS4 (pull.py): unpacked PS4 pack folders
    for prod in sorted((path(cfg["console_imports"]) / "PS4" / "packs").glob("*/uroot/Prod_Sku_*")):
        sx = next(iter(sorted(prod.glob("songs_*.xml"))), None)
        if not sx:
            continue
        for m in re.finditer(r'<SONG ID="(\d+)".*?</SONG>', sx.read_text("utf-8", errors="replace"), re.S):
            t = re.search(r"<TITLE>(.*?)</TITLE>", m.group(0), re.S)
            a = re.search(r"<PERFORMANCE_NAME>(.*?)</PERFORMANCE_NAME>", m.group(0), re.S)
            s = song(int(m.group(1)), a.group(1) if a else "?", t.group(1) if t else "?")
            s["sources"]["ps4pkg"] = {"pack": str(prod), "id": int(m.group(1))}
            disc_editions.setdefault(s["id"], []).append("von der PS4 übernommen")

    # PS2 discs (all songs; skipped ones only as edition info)
    meta2 = {r["id"]: r for r in json.loads(path(cfg["ps2_choice"]).read_text("utf-8"))}         if path(cfg["ps2_choice"]).exists() else {}
    for r in ps2_index(cfg):
        disc = re.sub(r"\s*\((Germany|Europe|Europe, Australia|v[\d.]+)\)", "", r["disc"]).strip() + " (PS2)"
        disc_editions.setdefault(r["id"], []).append(disc)
        if r.get("skip") and r["id"] not in songs:
            continue
        s = song(r["id"], r["artist"], r["title"])
        s["sources"]["ps2"] = {"disc": r["disc"], "iso": r.get("iso"), "lang": r.get("lang", "EN"),
                               **({"skip": r["skip"]} if r.get("skip") else {})}
        for k in ("year", "genre", "type"):
            if meta2.get(r["id"], {}).get(k):
                s["meta"].setdefault(k, meta2[r["id"]][k])

    # UltraStar (wins for artist/title spelling)
    # song_ids.json is keyed by "#ARTIST - #TITLE" of the .txt, not by folder name
    ids = song_ids(cfg)
    us = path(cfg["ultrastar_dir"])
    folders = {}
    for folder in sorted(p for p in us.iterdir() if p.is_dir()) if us.is_dir() else []:
        h = us_header(folder)
        folders[f"{h.get('ARTIST', '')} - {h.get('TITLE', '')}"] = (folder, h)
    new_id = 0
    for name in list(ids) + [k for k in folders if k not in ids]:
        folder, h = folders.get(name, (us / name, {}))
        if name in ids:
            sid = ids[name]
        else:  # folder not converted yet: temporary negative id
            new_id -= 1
            sid = new_id
        artist, _, title = name.partition(" - ")
        s = song(sid, artist, title)
        s["artist"], s["title"] = artist, title
        src = {"folder": str(folder), "exists": folder.is_dir(), "name": name}
        if sid < 0:
            s["label"], s["ps3_id"] = "", None
            src["new"] = True
            src["duet"] = bool(h) and any(x in library_txt(folder) for x in ("\nP1", "\nP 1"))
        if folder.is_dir():
            covers = sorted((p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")),
                            key=lambda p: ("[co]" not in p.name.lower() and "cover" not in p.name.lower(), p.name))
            if covers:
                src["cover"] = str(covers[0])
            for k, mk in (("YEAR", "year"), ("GENRE", "genre"), ("LANGUAGE", "language")):
                if h.get(k):
                    s["meta"][mk] = h[k]
            if h.get("VIDEO"):
                src["video"] = str(folder / h["VIDEO"])
            txt = sorted(folder.glob("*.txt"))
            if txt:
                src["txt"] = str(txt[0])
            if (folder / "usdb.json").exists():  # quality info from USDB (manager/usdbinfo.py)
                try:
                    s["usdb"] = json.loads((folder / "usdb.json").read_text("utf-8"))
                except ValueError:
                    pass
        s["sources"]["ultrastar"] = src

    # built PS4 packages
    for src, pk in pkg_index(cfg).items():
        for sid, p in pk.items():
            if sid in songs:
                songs[sid]["pkgs"][src] = p
            else:
                s = song(sid, "?", p["report"].get("song", p["label"]))
                s["pkgs"][src] = p

    # preferred package + duplicate hints (same artist/title under different ids)
    by_key: dict[str, list[int]] = {}
    for s in songs.values():
        s["pkg"] = next((s["pkgs"][k] | {"source": k} for k in SOURCE_ORDER if k in s["pkgs"]), None)
        s["key"] = norm(s["artist"]) + "|" + norm(s["title"])
        if s["id"] > 0:  # new (unconverted) UltraStar folders have no stable id yet
            by_key.setdefault(s["key"], []).append(s["id"])
    for s in songs.values():
        s["dupes"] = [i for i in by_key.get(s["key"], []) if i != s["id"]]
    ed = editions.load()
    for s in songs.values():
        s["editions"] = list(ed.get(s["id"], []))
        for e in disc_editions.get(s["id"], []):
            if e not in s["editions"] and not any(x.startswith("unbekannt") for x in [e]):
                s["editions"].append(e)
        if len(s["editions"]) > 1:
            s["editions"] = [e for e in s["editions"] if not e.startswith("unbekannt")]
        s["issues"] = quality.issues(s)
    return songs
