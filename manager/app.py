"""SingStar Song-Manager: local web app (http://127.0.0.1:5077) for the PC song library and the PS3/PS4.

  python manager/app.py            (or manager/start.bat)
"""
import json
import os
import re
import shutil
import sys
import threading
import subprocess
import time
import webbrowser
from pathlib import Path

if sys.platform == "win32":
    # The manager runs without a console (start menu / pythonw): every child program (ping, ffmpeg, converters,
    # PkgTool …) would otherwise pop up its own console window. subprocess.run & co. all go through Popen.
    # Children must be console programs with a hidden console (CREATE_NO_WINDOW) so that their own children
    # (to_ps3.py -> us_to_ps4.py -> ffmpeg) inherit it; a pythonw child has none and each ffmpeg opens a window.
    if sys.executable.lower().endswith("pythonw.exe"):
        _py = Path(sys.executable).with_name("python.exe")
        if _py.exists():
            sys.executable = str(_py)
    class _NoWindowPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)
    subprocess.Popen = _NoWindowPopen

from flask import Flask, abort, jsonify, request, send_file

import consoles
import covers
import discpack
import startpatch
import editions
import library
import lyrics
import ps3versions
import ps4names
import pull
import ps3write
import store
import usdb
import userdata
import usdbdl
import usdbinfo
import usdbupdates

app = Flask(__name__, static_folder=None)
cfg = library.load_config()
state = {"songs": None, "built": 0}
lock = threading.Lock()


def settings_apply():
    """(Re)load config.json + settings: hosts and storage folders."""
    new = library.load_config()
    cfg.clear()
    cfg.update(new)
    st = store.load("settings", {})
    cfg["consoles"] = consoles.migrate(new, st)
    # vocal separation for the vocal reduction (ADRS): read by us_to_ps4.py / ps2_to_ps4.py in every build
    os.environ["SINGSTAR_ADRS"] = st.get("adrs", "full")


def songs() -> dict[int, dict]:
    with lock:
        if state["songs"] is None:
            state["songs"], state["built"] = library.build(cfg), time.time()
        return state["songs"]


def reload_pc():
    with lock:
        state["songs"] = None
    songs()


def song_or_404(sid: int) -> dict:
    s = songs().get(sid)
    if not s:
        abort(404)
    return s


def decisions() -> dict:
    return store.load("decisions", {"dupes": {}})


def ps3_of(ps4: int) -> int:
    """Inverse of songid.ps4_id: own songs 45xxx (PS4) -> 60xxx (PS3), official ids stay."""
    return 60000 + (ps4 - library.songid.CUSTOM_BASE) if ps4 >= library.songid.CUSTOM_BASE else ps4


def console_state() -> list[tuple[dict, dict]]:
    """(console, last scan) for every enabled console that was read at least once."""
    out = []
    for c in consoles.active(cfg):
        d = consoles.load(c["id"])
        if d:
            out.append((c, d))
    return out


def console_ids() -> list[str]:
    return [c["id"] for c in consoles.all_consoles(cfg)]


def merged() -> list[dict]:
    """Library rows. row["on"] = {console id: "installed"|"pending"|"no" (PS4) / "yes"|"no" (PS3)} for every enabled
    console that was read; songs that are only on consoles get rows with only_on = [console ids]."""
    cons = console_state()
    ps4s = [(c["id"], {int(k) for k in d["installed"]}, set(d["pending"])) for c, d in cons if c["type"] == "ps4"]
    disc = {c["id"]: discpack.state(c["id"]) for c, _ in cons if c["type"] == "ps4" and c.get("install") == "disc"}
    disc = {cid: (set(st["uploaded"]), set(st["songs"])) for cid, st in disc.items()}
    ps3s = [(c["id"], set(d["dirs"])) for c, d in cons if c["type"] == "ps3"]
    dec = decisions()["dupes"]
    wished = {library.norm(w["artist"]) + "|" + library.norm(w["title"]) for w in store.load("wishlist", [])}
    out, seen_ps3 = [], set()
    user = userdata.per_song(console_ids())
    for s in songs().values():
        row = {k: s[k] for k in ("id", "ps3_id", "label", "artist", "title", "meta", "dupes", "editions", "issues")}
        row["sources"] = sorted(s["sources"])
        row["cover"] = covers.available(s)
        row["new"] = s["id"] < 0
        p = s["pkg"]
        row["pkg"] = {"source": p["source"], "mb": p["mb"], "name": Path(p["file"]).name} if p else None
        keep = dec.get(s["key"])
        row["dupe_state"] = None if not s["dupes"] else ("undecided" if keep is None else
                                                         "both" if keep == "both" else
                                                         "keep" if keep == s["id"] else "remove")
        row["wished"] = s["key"] in wished
        row["ps3src"] = ps3write.ps3_source(s)
        row["user"] = user.get(s["id"])
        u = s.get("usdb")
        row["usdb"] = {k: u.get(k) for k in ("id", "rating", "votes", "songcheck", "golden")} if u else None
        on = {}
        for cid, inst, pend in ps4s:
            on[cid] = ("installed" if s["id"] in inst
                       else "pending" if p and Path(p["file"]).name in pend else "no")
            if cid in disc and on[cid] != "installed":  # songs without PKG (disc pack in download0)
                up, want = disc[cid]
                on[cid] = ("disc" if s["id"] in up and s["id"] in want else "queued" if s["id"] in want
                           else "leaving" if s["id"] in up else "no")
        if s["ps3_id"]:
            seen_ps3.add(s["ps3_id"])
            for cid, dirs in ps3s:
                on[cid] = "yes" if s["ps3_id"] in dirs else "no"
        row["on"] = on
        out.append(row)
    # songs on consoles without a song on the PC (PS4: names from the song db; PS3: from songs_4_0.xml)
    known, extra = set(songs()), {}

    def console_row(sid, ps3_id, label, artist, title, meta):
        return extra.setdefault(sid, {
            "id": sid, "ps3_id": ps3_id, "label": label, "artist": artist, "title": title, "meta": meta,
            "dupes": [], "editions": [], "issues": [], "sources": [], "cover": False, "pkg": None, "new": False,
            "dupe_state": None, "wished": False, "ps3src": None, "user": user.get(sid), "only_on": []})
    for c, d in cons:
        if c["type"] == "ps4":
            names = ps4names.names(c["id"])
            for sid, label in d["installed"].items():
                sid = int(sid)
                if sid in known:
                    continue
                n = names.get(sid, {})
                r = console_row(sid, ps3_of(sid), label, n.get("artist", "?"), n.get("title", f"unbekannt ({label})"),
                                {"hinweis": "Demo" if n.get("demo") else ""})
                r["label"] = r["label"] or label
                r["only_on"].append(c["id"])
        else:
            for psid, m in d["songs"].items():
                psid = int(psid)
                sid = library.songid.ps4_id(psid)
                if psid in seen_ps3 or sid in known:
                    continue
                r = console_row(sid, psid, "", m["artist"], m["title"], {"origin": m["gamever"]})
                r["only_on"].append(c["id"])
    for r in extra.values():
        r["on"] = {cid: "installed" if r["id"] in inst else "no" for cid, inst, _ in ps4s}
        r["on"].update({cid: "yes" if r["ps3_id"] in dirs else "no" for cid, dirs in ps3s})
        r["only_on"] = [cid for cid, st in r["on"].items() if st in ("installed", "yes")] or r["only_on"]
        r["only_console"] = r["only_on"][0]
        out.append(r)
    return out


@app.get("/")
def index():
    r = send_file(Path(__file__).parent / "index.html", max_age=0)
    r.headers["Cache-Control"] = "no-store"  # always the current UI after updates
    return r


@app.get("/i18n.js")
def i18n_js():
    r = send_file(Path(__file__).parent / "i18n.js", max_age=0)
    r.headers["Cache-Control"] = "no-store"
    return r


def consoles_info() -> list[dict]:
    """All configured consoles with their last scan (for the header, the consoles tab and the settings)."""
    out = []
    for c in consoles.all_consoles(cfg):
        cid, d = c["id"], consoles.load(c["id"])
        x = {"id": cid, "type": c["type"], "name": c["name"], "host": c["host"], "port": c["port"],
             "enabled": c.get("enabled", True), "online": consoles.online.get(cid, False),
             "user_time": userdata.load(cid)["time"], "time": None,
             "queued": len(store.load("deploy_pending", {}).get(cid, []))}
        if c["type"] == "ps4":
            x["install"] = c.get("install", "pkg")
            if x["install"] == "disc":
                st = discpack.state(cid)
                x["disc"] = {"songs": len(st["songs"]), "uploaded": len(st["uploaded"]), "time": st["time"],
                             "size": st["size"], "pending": discpack.pending(cid), "crf": discpack.crf()}
        if d:
            x.update(time=d["time"], free=d.get("free"))
            if c["type"] == "ps4":
                inst = {int(k) for k in d["installed"]}
                x["installed"], x["pending"] = len(inst), len(d["pending"])
                lab = [(n, re.search(r"-([0-9A-Z]{16})\.pkg$", n)) for n in d["pending"]]
                x["cleanup"] = [n for n, m in lab if m and library.songid.id_from_label(m.group(1)) in inst]
                x["nodialog"] = d.get("nodialog")
            else:
                x["songs"] = len(d["dirs"])
                by3 = {s["ps3_id"]: s["id"] for s in songs().values() if s.get("ps3_id") and ps3write.ps3_source(s)}
                x["unlisted"] = [by3[i] for i in d.get("unlisted", []) if i in by3]  # library ids, ready to enter
        out.append(x)
    return out


@app.get("/api/library")
def api_library():
    return jsonify({"songs": merged(), "built": state["built"], "consoles": consoles_info(), "count": len(songs())})


@app.get("/api/status")
def api_status():
    """Cheap poll for the UI: console online flags and cache times."""
    times = {}
    for c in consoles.all_consoles(cfg):
        d = consoles.load(c["id"])
        times[c["id"]] = d and d["time"]
    return jsonify({"online": consoles.online, "times": times, "built": state["built"], "checked": consoles.checked,
                    "user": state.get("user_time")})


@app.post("/api/rescan/pc")
def api_rescan_pc():
    if request.args.get("editions"):
        editions.build()
    reload_pc()
    return jsonify(ok=True)


@app.post("/api/scan/<console>")
def api_scan(console):
    if console not in console_ids():
        abort(404)
    try:
        consoles.scan(cfg, console)
        consoles.online[console] = True
        return jsonify(ok=True)
    except Exception as e:  # noqa: BLE001
        consoles.online[console] = False
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 502


@app.get("/api/song/<int:sid>")
def api_song(sid):
    s = song_or_404(sid)
    d = {k: v for k, v in s.items() if k != "key"}
    us = s["sources"].get("ultrastar", {})
    d["can_edit"] = bool(us.get("txt"))
    d["media"] = [k for k in ("us", "usvideo", "ps3disc", "ps3", "ps3ver") if media_path(s, k)]
    if s.get("pkg") and Path(s["pkg"]["file"]).exists():
        d["media"].append("pkg")  # unpacked only when played
    d["charts"] = userdata.charts(sid, console_ids())
    return jsonify(d)


@app.get("/api/cover/<int:sid>")
def api_cover(sid):
    c = covers.cover(song_or_404(sid))
    return send_file(c, max_age=86400) if c else abort(404)


def media_path(s: dict, kind: str) -> Path | None:
    """us = UltraStar audio (timing master), usvideo = UltraStar video, ps3 = PS3 library video."""
    if kind in ("us", "usvideo"):
        us = s["sources"].get("ultrastar", {})
        folder = Path(us.get("folder", ""))
        if not us.get("txt"):
            return None
        if kind == "usvideo":
            v = us.get("video")
            return Path(v) if v and Path(v).exists() else None
        h = library.us_header(folder)
        a = h.get("MP3") or h.get("AUDIO")
        return folder / a if a and (folder / a).exists() else None
    d = media_dir(s, kind)
    for n in ("video.mp4", "preview.mp4"):
        if d and (d / n).exists():
            return d / n
    return None


PKG_MEDIA = Path(__file__).parent / "cache" / "pkgmedia"
_pkg_lock = threading.Lock()


def media_dir(s: dict, kind: str, extract: bool = True) -> Path | None:
    """Folder with video.mp4 + melody*.xml: ps3 = PS3 library, ps3disc = imported disc, ps3ver = stored PS3 version
    (made for the PS3, e.g. PS2 songs), pkg = our PS4 package (unpacked on first use into cache/pkgmedia, last 5 kept)."""
    if kind in ("ps3", "ps3disc"):
        d = s["sources"].get("ps3lib" if kind == "ps3" else "ps3disc", {}).get("dir")
        return Path(d) if d else None
    if kind == "ps3ver":
        d = ps3versions.stored(ps3_of(s["id"])) if s["id"] > 0 else None
        return d if d and (d / "video.mp4").exists() else None
    if kind == "pkg" and s.get("pkg") and Path(s["pkg"]["file"]).exists():
        pkg, out = Path(s["pkg"]["file"]), PKG_MEDIA / str(s["id"])
        if (out / "video.mp4").exists() and (out / "video.mp4").stat().st_mtime >= pkg.stat().st_mtime:
            return out
        if not extract:
            return out
        with _pkg_lock:
            if not ((out / "video.mp4").exists() and (out / "video.mp4").stat().st_mtime >= pkg.stat().st_mtime):
                import subprocess
                tmp = PKG_MEDIA / f"_x{s['id']}"
                shutil.rmtree(tmp, ignore_errors=True)
                subprocess.run(["dotnet", str(library.ROOT / "tools" / "PkgTool" / "PkgTool.Core.dll"), "pkg_extract",
                                str(pkg), str(tmp)], capture_output=True, check=True)
                src = next(tmp.glob(f"uroot/Prod_Sku_*/{s['id']}"))
                shutil.rmtree(out, ignore_errors=True)
                out.mkdir(parents=True)
                for f in list(src.glob("melody*.xml")) + [src / "video.mp4"]:
                    shutil.move(str(f), out / f.name)
                shutil.rmtree(tmp, ignore_errors=True)
                for old in sorted((x for x in PKG_MEDIA.iterdir() if x.is_dir() and not x.name.startswith("_")),
                                  key=lambda x: x.stat().st_mtime)[:-5]:
                    shutil.rmtree(old, ignore_errors=True)
        return out
    return None


@app.get("/api/media/<int:sid>/<kind>")
def api_media(sid, kind):
    p = media_path(song_or_404(sid), kind)
    return send_file(p, conditional=True) if p else abort(404)


@app.get("/api/lyrics/<int:sid>/<kind>")
def api_lyrics(sid, kind):
    s = song_or_404(sid)
    if kind == "us" and s["sources"].get("ultrastar", {}).get("txt"):
        return jsonify(lyrics.ultrastar(Path(s["sources"]["ultrastar"]["txt"])))
    d = media_dir(s, kind)
    if d:
        mel = sorted(Path(d).glob("melody*.xml"), key=lambda p: len(p.name))
        if mel:
            return jsonify(lyrics.melody(mel[-1]))
    abort(404)


EDITABLE = {"artist": "ARTIST", "title": "TITLE", "year": "YEAR", "genre": "GENRE", "language": "LANGUAGE",
            "gap": "GAP", "videogap": "VIDEOGAP"}


@app.post("/api/song/<int:sid>/edit")
def api_edit(sid):
    s = song_or_404(sid)
    us = s["sources"].get("ultrastar", {})
    if not us.get("txt"):
        return jsonify(ok=False, error="Nur UltraStar-Songs sind bearbeitbar"), 400
    txt = Path(us["txt"])
    body = request.get_json(force=True)
    raw = txt.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text, enc = raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        text, enc = raw.decode("cp1252"), "cp1252"
    old_head = library.us_header(txt.parent)
    lines = text.splitlines(keepends=True)
    changed = []
    for key, tag in EDITABLE.items():
        if key not in body or body[key] is None:
            continue
        val = str(body[key]).strip()
        if val == old_head.get(tag, ""):
            continue
        idx = next((i for i, ln in enumerate(lines) if ln.upper().startswith(f"#{tag}:")), None)
        nl = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
        if idx is not None:
            if val:
                lines[idx] = f"#{tag}:{val}{nl}"
            else:
                del lines[idx]
        elif val:
            last = max((i for i, ln in enumerate(lines) if ln.startswith("#")), default=-1)
            lines.insert(last + 1, f"#{tag}:{val}{nl}")
        changed.append(f"{tag}: {old_head.get(tag, '')!r} → {val!r}")
    if not changed:
        return jsonify(ok=True, changed=[])
    bdir = store.DATA / "backups" / "ultrastar"
    bdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(txt, bdir / f"{txt.stem}_{time.strftime('%Y%m%d-%H%M%S')}.txt")
    txt.write_bytes((b"\xef\xbb\xbf" if bom else b"") + "".join(lines).encode(enc, errors="replace"))
    # keep the song id when artist/title change (song_ids.json is keyed by "#ARTIST - #TITLE")
    new_head = library.us_header(txt.parent)
    old_key = f"{old_head.get('ARTIST', '')} - {old_head.get('TITLE', '')}"
    new_key = f"{new_head.get('ARTIST', '')} - {new_head.get('TITLE', '')}"
    if old_key != new_key and sid > 0:
        reg_p = library.path(cfg["song_ids"])
        reg = library.song_ids(cfg)
        reg.pop(old_key, None)
        reg[new_key] = sid
        reg_p.write_text(json.dumps(dict(sorted(reg.items())), ensure_ascii=False, indent=1), "utf-8")
    store.log("edit", f"{new_key}: " + "; ".join(changed))
    reload_pc()
    return jsonify(ok=True, changed=changed)


def best_source(s: dict, want: str | None = None) -> str | None:
    usable = [k for k in library.SOURCE_ORDER if k in s["sources"] and not s["sources"][k].get("skip")
              and k != "ps4pkg"  # taken-over PS4 packages are finished packages, nothing to build
              and not (k == "ultrastar" and not s["sources"][k].get("txt"))]
    if want in usable:
        return want
    return usable[0] if usable else None


def start_build(items: list, title: str | None = None, targets: list[str] | None = None) -> consoles.BuildJob:
    """targets: console ids the new songs go to once their packages are built (see deploy)."""
    job = consoles.BuildJob(cfg, items, title)

    def after():
        reload_pc()
        if targets:
            job.nexts = deploy([s["id"] for s, _ in items], targets, job.title)
            job.next = job.nexts[0] if job.nexts else None
    job.after = after
    return job.start()


def start_deploy(cid: str, ids: list[int]) -> int | None:
    c, ss = consoles.get(cfg, cid), songs()
    if c["type"] == "ps4":
        files = [ss[i]["pkg"]["file"] for i in ids if i in ss and ss[i]["pkg"]]
        return consoles.UploadJob(cfg, files, cid).start().id if files else None
    items = [ss[i] for i in ids if i in ss and ps3write.ps3_source(ss[i])]
    if not items:
        return None
    job = ps3write.PS3WriteJob(cfg, items, [cid])
    job.after = reload_pc
    return job.start().id


def deploy(ids: list[int], cids: list[str], why: str = "") -> list[int]:
    """Bring songs onto the chosen consoles right after adding them (disc import, USDB): PS4 with PKG -> upload to
    /data/pkg, PS4 with disc pack -> into its song list (uploaded when SingStar runs), PS3 -> transfer.
    Consoles that are offline get the songs noted in data/deploy_pending.json and receive them when online."""
    ss, jobs = songs(), []
    pend = store.load("deploy_pending", {})
    for cid in cids:
        try:
            c = consoles.get(cfg, cid)
        except KeyError:
            continue
        want = [i for i in ids if i in ss and (ss[i]["pkg"] if c["type"] == "ps4" else ps3write.ps3_source(ss[i]))]
        if not want:
            continue
        if c["type"] == "ps4" and c.get("install") == "disc":
            st = discpack.state(cid)
            st["songs"] = list(dict.fromkeys(st["songs"] + want))
            discpack.save_state(cid, st)
            store.log("deploy", f"{c['name']}: {len(want)} neue Songs fürs Disc-Pack vorgemerkt ({why})", console=cid)
        elif consoles.online.get(cid) and not deploy_busy(cid):
            j = start_deploy(cid, want)
            if j:
                jobs.append(j)
        else:
            pend[cid] = list(dict.fromkeys(pend.get(cid, []) + want))
            store.log("deploy", f"{c['name']}: {len(want)} neue Songs vorgemerkt ({why}) – "
                                + ("übertragen über „Konsolen & Verlauf“ → „Vorgemerkte übertragen“" if c["type"] == "ps3"
                                   else "werden übertragen, sobald die Konsole online ist"), console=cid)
    store.save("deploy_pending", pend)
    return jobs


def deploy_busy(cid: str) -> bool:
    return any(not j.finished and (getattr(j, "cid", None) == cid or cid in getattr(j, "cids", []))
               for j in consoles.Job.all.values())


def deploy_tick(cid: str):
    """Monitor round, console online: transfer songs that were noted while it was off."""
    pend = store.load("deploy_pending", {})
    if not pend.get(cid) or deploy_busy(cid) or consoles.get(cfg, cid)["type"] == "ps3":
        return  # PS3: only on request ("Vorgemerkte übertragen"), it may be in use for singing
    ids = pend.pop(cid)
    store.save("deploy_pending", pend)
    store.log("deploy", f"{consoles.name(cfg, cid)} ist online: {len(ids)} vorgemerkte Songs werden übertragen",
              console=cid)
    start_deploy(cid, ids)


consoles.on_tick.append(deploy_tick)


@app.post("/api/deploy/run")
def api_deploy_run():
    """Transfer the songs noted for a console now (PS3: only this way, never automatically)."""
    cid = request.get_json(force=True).get("console")
    if cid not in console_ids():
        abort(404)
    pend = store.load("deploy_pending", {})
    ids = pend.pop(cid, [])
    if not ids:
        return jsonify(ok=False, error="Nichts vorgemerkt"), 400
    if deploy_busy(cid):
        return jsonify(ok=False, error="Für diese Konsole läuft schon ein Auftrag"), 409
    store.save("deploy_pending", pend)
    return jsonify(ok=True, job=start_deploy(cid, ids))


@app.post("/api/song/<int:sid>/rebuild")
def api_rebuild(sid):
    s = song_or_404(sid)
    src = best_source(s, request.get_json(force=True).get("source"))
    if not src:
        return jsonify(ok=False, error="Keine verwendbare Quelle für diesen Song"), 400
    return jsonify(ok=True, job=start_build([(s, src)]).id)


@app.post("/api/build")
def api_build():
    """Build PS4 packages for many songs: {"ids": [...], "missing_only": true}."""
    b = request.get_json(force=True)
    ss = songs()
    items, skipped = [], []
    for i in b.get("ids", []):
        s = ss.get(i)
        if not s:
            continue
        if b.get("missing_only", True) and s["pkg"]:
            continue
        src = best_source(s)
        (items.append((s, src)) if src else skipped.append(i))
    if not items:
        return jsonify(ok=False, error="Nichts zu bauen" + (f" ({len(skipped)} ohne verwendbare Quelle)" if skipped else "")), 400
    return jsonify(ok=True, job=start_build(items).id, count=len(items), skipped=skipped)


IMPORT_EXT = (".iso", ".7z", ".zip", ".rar")


@app.get("/api/import/list")
def api_import_list():
    d = Path(request.args.get("dir", "")).expanduser()
    if not d.is_dir():
        return jsonify(ok=False, error="Ordner nicht gefunden"), 400
    ps3_root, ps2_root = library.path(cfg["ps3_imports"]), library.path(cfg["ps2_root"])
    ps3_done = {p.name.lower() for p in ps3_root.glob("*")} if ps3_root.is_dir() else set()
    ps2_done = {p.name.lower() for p in ps2_root.glob("*") if p.is_dir() and any(p.glob("*_ISO"))}
    import disc_import
    files = []
    for f in sorted(list(d.glob("*")) + list(d.glob("*/*"))):
        if f.is_file() and f.suffix.lower() in IMPORT_EXT and "singstar" in f.name.lower()                 and f.stat().st_size > 2**29:
            name = disc_import.disc_name(f)
            in_ps2 = ps2_root in f.parents  # PS2 archives live in the PS2 folder, PS3 elsewhere
            files.append({"path": str(f), "name": name, "gb": round(f.stat().st_size / 2**30, 1),
                          "imported": name.lower() in (ps2_done if in_ps2 else ps3_done)})
    return jsonify(ok=True, files=files)


@app.post("/api/import")
def api_import():
    b = request.get_json(force=True)
    paths = [p for p in b.get("paths", []) if Path(p).is_file()]
    if not paths:
        return jsonify(ok=False, error="Keine Datei gewählt"), 400
    job = consoles.ImportJob(cfg, paths)
    targets = [c for c in b.get("targets", []) if c in console_ids()]

    def after(j):
        reload_pc()
        names = {r["name"] for r in j.results}
        items = []
        for s in songs().values():
            src = best_source(s)
            d = s["sources"].get(src or "", {})
            if src in ("ps3disc", "ps2") and (d.get("disc") in names or any(n in str(d.get("export", "")) for n in names)
                                              or any(n in d.get("disc", "") for n in names)):
                items.append((s, src))
        todo = [(s, src) for s, src in items if not s["pkg"]]
        if b.get("build") and todo:
            nxt = start_build(todo, f"{len(todo)} neue Songs von der Disc bauen", targets)
            j.log.append(f"Paketbau gestartet: {len(todo)} Songs")
            j.next = nxt.id
            ready = [s["id"] for s, _ in items if s["pkg"]]  # already built earlier: transfer right away
        else:
            ready = [s["id"] for s, _ in items]
        if targets and ready:
            j.nexts = deploy(ready, targets, f"Disc-Import {', '.join(sorted(names))}")
            j.next = j.next or (j.nexts[0] if j.nexts else None)
    job.after = after
    return jsonify(ok=True, job=job.start().id)


def targets(b: dict, kind: str) -> list[str]:
    """Console ids of the requested type from the request body ("consoles"); default: all enabled of that type."""
    ok = [c["id"] for c in consoles.active(cfg, kind)]
    want = b.get("consoles")
    return [c for c in want if c in ok] if want else ok


@app.post("/api/song/<int:sid>/replace_ps4")
def api_replace(sid):
    s = song_or_404(sid)
    jobs = []
    for cid in targets(request.get_json(force=True, silent=True) or {}, "ps4"):
        d = consoles.load(cid)
        if s["pkg"] and d and str(sid) in d["installed"]:
            jobs.append(consoles.ReplaceJob(cfg, s, cid).start().id)
    if not jobs:
        return jsonify(ok=False, error="Song ist laut letztem Stand auf keiner gewählten PS4 installiert"), 400
    return jsonify(ok=True, job=jobs[0], jobs=jobs)


@app.post("/api/ps4/upload")
def api_upload():
    b = request.get_json(force=True)
    ss = songs()
    files = [ss[i]["pkg"]["file"] for i in b.get("ids", []) if i in ss and ss[i]["pkg"]]
    if not files:
        return jsonify(ok=False, error="Keine Pakete ausgewählt"), 400
    cids = [c for c in targets(b, "ps4") if consoles.get(cfg, c).get("install", "pkg") == "pkg"]
    if not cids:
        return jsonify(ok=False, error="Keine PS4 mit Installation über PKG gewählt"), 400
    jobs = [consoles.UploadJob(cfg, files, cid).start().id for cid in cids]
    return jsonify(ok=True, job=jobs[0], jobs=jobs)


def disc_running(cid: str) -> consoles.Job | None:
    return next((j for j in consoles.Job.all.values() if isinstance(j, discpack.DiscPackJob) and j.cid == cid
                 and not j.finished), None)


def start_disc(cid: str) -> int:
    job = disc_running(cid)
    if job:
        return job.id
    job = discpack.DiscPackJob(cfg, cid, songs())
    job.after = reload_pc
    return job.start().id


@app.post("/api/ps4/discpack")
def api_discpack():
    """Disc pack of a PS4 in install mode "disc": {console, add: [ids], remove: [ids], upload: bool}.
    Changes are kept and uploaded now if the PS4 is reachable, otherwise automatically as soon as it is."""
    b = request.get_json(force=True)
    cid = b.get("console")
    if cid not in console_ids() or consoles.get(cfg, cid).get("install") != "disc":
        return jsonify(ok=False, error="Diese PS4 ist nicht auf Installation per Disc-Pack eingestellt"), 400
    st = discpack.state(cid)
    inst = {int(k) for k in (consoles.load(cid) or {}).get("installed", {})}
    ss = songs()
    add = [i for i in b.get("add", []) if i in ss and ss[i]["pkg"] and i not in inst]
    skipped = len(b.get("add", [])) - len(add)
    st["songs"] = [i for i in dict.fromkeys(st["songs"] + add) if i not in set(b.get("remove", []))]
    discpack.save_state(cid, st)
    if not discpack.pending(cid) and not b.get("upload"):
        return jsonify(ok=True, queued=False, skipped=skipped)
    try:
        f = consoles.connect(consoles.get(cfg, cid), timeout=6)
        try:
            running = discpack.reachable(f)
        finally:
            f.close()
    except Exception:  # noqa: BLE001  console off
        running = False
    if not running:
        return jsonify(ok=True, queued=True, skipped=skipped,
                       note="vorgemerkt – wird übertragen, sobald die PS4 erreichbar ist")
    return jsonify(ok=True, job=start_disc(cid), skipped=skipped)


@app.post("/api/ps4/nodialog")
def api_nodialog():
    b = request.get_json(force=True)
    cid = b.get("console")
    if cid not in console_ids():
        abort(404)
    try:
        return jsonify(ok=True, notes=startpatch.set_on(cfg, cid, bool(b.get("on", True))))
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 502


@app.post("/api/ps4/discsetup")
def api_discsetup():
    cid = request.get_json(force=True).get("console")
    if cid not in console_ids():
        abort(404)
    try:
        return jsonify(ok=True, notes=discpack.setup(cfg, cid))
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 502


def auto_discpack(cid: str):
    """After a scan: the disc pack has open changes -> upload them (target on the user partition, SingStar need
    not run)."""
    c = consoles.get(cfg, cid)
    if c["type"] == "ps4" and c.get("install") == "disc" and discpack.pending(cid) and not disc_running(cid):
        store.log("discpack", f"{c['name']}: vorgemerkte Disc-Pack-Änderungen werden übertragen", console=cid)
        start_disc(cid)


consoles.on_scan.append(auto_discpack)
_disc_probe: dict[str, float] = {}


def disc_tick(cid: str):
    """Monitor round, console online: open disc pack changes -> every 30 s look whether the upload target is
    reachable and upload then. Only while something is pending (GoldHEN FTP serves one client at a time)."""
    c = consoles.get(cfg, cid)
    if c["type"] != "ps4" or c.get("install") != "disc" or not discpack.pending(cid) or disc_running(cid) \
            or any(not j.finished for j in consoles.Job.all.values() if getattr(j, "cid", None) == cid):
        return
    if time.time() - _disc_probe.get(cid, 0) < 30:
        return
    _disc_probe[cid] = time.time()
    f = consoles.connect(c, timeout=6)
    try:
        running = discpack.reachable(f)
    finally:
        f.close()
    if running:
        store.log("discpack", f"{c['name']}: vorgemerkte Disc-Pack-Änderungen werden übertragen", console=cid)
        start_disc(cid)


consoles.on_tick.append(disc_tick)


@app.post("/api/ps4/cleanup")
def api_cleanup():
    b = request.get_json(force=True)
    names, cid = b.get("names", []), b.get("console") or "ps4"
    if cid not in console_ids():
        abort(404)
    try:
        done = consoles.delete_pending(cfg, names, cid)
        consoles.scan(cfg, cid)
        return jsonify(ok=True, deleted=done)
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=str(e)), 502


@app.post("/api/ps3/write")
def api_ps3_write():
    """Build PS3 versions where needed and write the songs to the PS3 (lists changed once, with backups)."""
    ids = request.get_json(force=True).get("ids", [])
    ss = songs()
    items = [ss[i] for i in ids if i in ss and ps3write.ps3_source(ss[i])]
    if not items:
        return jsonify(ok=False, error="Keiner der Songs hat eine Quelle für die PS3 (UltraStar, PS3-Disc oder PS2)"), 400
    cids = targets(request.get_json(force=True), "ps3")
    if not cids:
        return jsonify(ok=False, error="Keine PS3 eingerichtet oder gewählt"), 400
    job = ps3write.PS3WriteJob(cfg, items, cids)
    job.after = reload_pc
    return jsonify(ok=True, job=job.start().id, count=len(items), skipped=len(ids) - len(items))


@app.post("/api/pull")
def api_pull():
    """Copy console-only songs to the PC: {console id: [ps3 ids (PS3) or labels (PS4)]}."""
    b = request.get_json(force=True)
    jobs = []
    for c in consoles.active(cfg):
        if not b.get(c["id"]):
            continue
        j = (pull.PullPS3Job(cfg, [int(x) for x in b[c["id"]]], c["id"]) if c["type"] == "ps3"
             else pull.PullPS4Job(cfg, [str(x) for x in b[c["id"]]], c["id"]))
        j.after = reload_pc
        jobs.append(j.start().id)
    return jsonify(ok=bool(jobs), jobs=jobs, error=None if jobs else "nichts ausgewählt")


def console_only(cid: str) -> list[int]:
    d = consoles.load(cid) or {}
    ss = songs()
    if consoles.get(cfg, cid)["type"] == "ps4":
        return sorted(int(k) for k in d.get("installed", {}) if int(k) not in ss)
    known3 = {s["ps3_id"] for s in ss.values() if s.get("ps3_id")}
    return sorted(int(x) for x in d.get("dirs", []) if int(x) not in known3)


def report_console_only(console: str):
    """After a scan: log songs that appeared on a console but are not on the PC (once per song)."""
    now = console_only(console)
    seen = store.load("console_only_seen", {})
    new = [i for i in now if str(i) not in seen.get(console, {})]
    if new:
        store.log("console-only", f"{consoles.name(cfg, console)}: {len(new)} Song(s) nur auf der Konsole, "
                                  "nicht am PC – in der Bibliothek „nur auf Konsole“ → "
                                  "„Auf den PC holen“", songs=new[:200], console=console)
    seen[console] = {str(i): True for i in now}
    store.save("console_only_seen", seen)


consoles.on_scan.append(report_console_only)


def fetch_userdata(console: str):
    """After a scan: favourites/statistics/best scores from the console (in the background, PS3 FTP is slow)."""
    def go():
        try:
            c = consoles.get(cfg, console)
            ftp = consoles.RetryFtp(c, timeout=60, tries=4)
            try:
                if userdata.fetch(ftp, console, c["type"]):
                    state["user_time"] = time.time()
            finally:
                ftp.close()
        except Exception as e:  # noqa: BLE001
            store.log("error", f"{consoles.name(cfg, console)}: Favoriten/Statistik nicht lesbar: {e}")
    threading.Thread(target=go, daemon=True).start()


consoles.on_scan.append(fetch_userdata)


@app.post("/api/ps3/fixer")
def api_fixer():
    cid = request.args.get("console") or "ps3"
    if cid not in console_ids():
        abort(404)
    return jsonify(ok=True, job=consoles.FixerJob(cfg, cid).start().id)


@app.get("/api/jobs")
def api_jobs():
    return jsonify([j.state() for j in sorted(consoles.Job.all.values(), key=lambda j: -j.id)][:20])


@app.get("/api/jobs/<int:jid>")
def api_job(jid):
    return jsonify((consoles.Job.all.get(jid) or abort(404)).state())


@app.post("/api/jobs/<int:jid>/cancel")
def api_job_cancel(jid):
    (consoles.Job.all.get(jid) or abort(404)).cancelled = True
    return jsonify(ok=True)


@app.post("/api/decision")
def api_decision():
    b = request.get_json(force=True)
    s = song_or_404(int(b["id"]))
    d = decisions()
    if b.get("keep") is None:
        d["dupes"].pop(s["key"], None)
    else:
        d["dupes"][s["key"]] = b["keep"]
    store.save("decisions", d)
    return jsonify(ok=True)


@app.route("/api/wishlist", methods=["GET", "POST", "DELETE"])
def api_wishlist():
    wl = store.load("wishlist", [])
    if request.method == "POST":
        b = request.get_json(force=True)
        item = {"id": int(time.time() * 1000), "artist": b.get("artist", "").strip(),
                "title": b.get("title", "").strip(), "note": b.get("note", "").strip(), "added": time.time(),
                "usdb": b.get("usdb")}
        if not item["artist"] and not item["title"]:
            return jsonify(ok=False, error="Interpret oder Titel angeben"), 400
        wl.append(item)
        store.save("wishlist", wl)
    elif request.method == "DELETE":
        wl = [w for w in wl if w["id"] != int(request.args["id"])]
        store.save("wishlist", wl)
    keys = {}
    for s in songs().values():
        keys.setdefault(library.norm(s["artist"]) + "|" + library.norm(s["title"]), s["id"])
    for w in wl:
        w["have"] = keys.get(library.norm(w["artist"]) + "|" + library.norm(w["title"]))
    return jsonify(wl)


@app.post("/api/wishlist/<int:wid>")
def api_wish_update(wid):
    wl = store.load("wishlist", [])
    for w in wl:
        if w["id"] == wid:
            w.update({k: v for k, v in request.get_json(force=True).items() if k in ("usdb", "note")})
    store.save("wishlist", wl)
    return jsonify(ok=True)


@app.post("/api/usdb/search")
def api_usdb():
    b = request.get_json(force=True)
    try:
        return jsonify(ok=True, results=usdb.search(b.get("artist", ""), b.get("title", "")))
    except usdb.UsdbError as e:
        return jsonify(ok=False, error=str(e)), 400
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=f"USDB nicht erreichbar: {e}"), 502


@app.post("/api/usdb/download")
def api_usdb_download():
    """Load songs from USDB into the UltraStar folder: {"ids": [usdb ids], "build": bool, "video": bool}."""
    b = request.get_json(force=True)
    ids = list(dict.fromkeys(int(i) for i in b.get("ids", []) if str(i).isdigit()))
    if not ids:
        return jsonify(ok=False, error="Keine USDB-Songs gewählt"), 400
    force = bool(b.get("force"))
    if force:  # update: keep the current .txt (own GAP/text edits) before it is replaced
        known = usdbupdates.local_songs(cfg)
        bdir = store.DATA / "backups" / "ultrastar"
        bdir.mkdir(parents=True, exist_ok=True)
        for i in ids:
            for txt in (known[i].glob("*.txt") if i in known else []):
                shutil.copy2(txt, bdir / f"{txt.stem}_vor-USDB-Update_{time.strftime('%Y%m%d-%H%M%S')}.txt")
    job = usdbdl.USDBDownloadJob(cfg, ids, video=b.get("video", True), force=force)
    targets = [c for c in b.get("targets", []) if c in console_ids()]

    def after(j):
        if j.folders:  # quality info for the new songs (rating, songcheck, comments), version = now
            usdbinfo.USDBInfoJob(cfg, list(j.folders), refresh=True)._run()  # _run: marks it finished
            root = library.path(cfg["ultrastar_dir"])
            usdbupdates.mark_downloaded([root / n for n in j.folders])
        wl = store.load("wishlist", [])
        for w in wl:
            if (w.get("usdb") or {}).get("id") in ids:
                w["downloaded"] = time.time()
        store.save("wishlist", wl)
        reload_pc()
        names = set(j.folders)
        new = [s for s in songs().values() if Path(s["sources"].get("ultrastar", {}).get("folder", "")).name in names]
        # a console target needs the build too: new UltraStar songs get their song id (PS4 45xxx / PS3 60xxx) there
        if (b.get("build") or targets) and j.folders:
            items = [(s, "ultrastar") for s in new if (force or not s["pkg"])
                     and not s["sources"]["ultrastar"].get("duet")]
            if items:
                j.next = start_build(items, f"{len(items)} neue USDB-Songs als PS4-Paket bauen", targets).id
                j.log.append(f"Paketbau gestartet: {len(items)} Songs")
            ready = [s["id"] for s in new if s["pkg"] and not force]  # loaded again but already built
            if targets and ready:
                j.nexts = deploy(ready, targets, "USDB")
    job.after = after
    return jsonify(ok=True, job=job.start().id)


@app.post("/api/usdb/check")
def api_usdb_check():
    """Look for newer USDB versions of downloaded songs now."""
    try:
        found = usdbupdates.check(cfg)
    except usdb.UsdbError as e:
        return jsonify(ok=False, error=str(e)), 400
    reload_pc()
    return jsonify(ok=True, found=found, last_check=store.load(usdbupdates.STATE, {}).get("last_check"))


@app.get("/api/usdb/check")
def api_usdb_check_state():
    return jsonify(store.load(usdbupdates.STATE, {}))


@app.post("/api/usdb/info")
def api_usdb_info():
    """Fetch USDB quality info for all UltraStar songs from USDB (missing only, or all with refresh)."""
    job = usdbinfo.USDBInfoJob(cfg, refresh=bool(request.get_json(force=True).get("refresh")))
    job.after = reload_pc
    return jsonify(ok=True, job=job.start().id)


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        b = request.get_json(force=True)
        st = store.load("settings", {})
        if isinstance(b.get("consoles"), list):
            try:
                st["consoles"] = clean_consoles(b["consoles"])
            except ValueError as e:
                return jsonify(ok=False, error=str(e)), 400
            st.pop("ps4", None)
            st.pop("ps3", None)
        move = None
        if isinstance(b.get("paths"), dict):
            old_paths = dict(st.get("paths", {}))
            st["paths"] = {k: v.strip() for k, v in b["paths"].items()
                           if k in (*library.PATH_KEYS, "pkg_root") and isinstance(v, str) and v.strip()}
            old_root = Path(old_paths.get("pkg_root") or library.ROOT / "build")
            new_root = Path(st["paths"].get("pkg_root") or library.ROOT / "build")
            if b.get("move_pkgs") and old_root.resolve() != new_root.resolve():
                move = (old_root, new_root)
        if b.get("adrs") in ("full", "nodemucs", "off"):
            st["adrs"] = b["adrs"]
        if "disc_crf" in b:
            st["disc_crf"] = int(b["disc_crf"]) if str(b["disc_crf"]).isdigit() else None
        if b.get("lang") in ("de", "en"):
            st["lang"] = b["lang"]
        if "ps3_keep" in b:
            st["ps3_keep"] = bool(b["ps3_keep"])
        if b.get("ps3_dir"):
            st["ps3_dir"] = b["ps3_dir"].strip()
        store.save("settings", st)
        sec = store.load("secrets", {})
        if "usdb_user" in b:
            sec["usdb_user"] = b["usdb_user"].strip()
        if b.get("usdb_pass"):
            sec["usdb_pass"] = b["usdb_pass"]
        store.save("secrets", sec)
        usdb._session = None
        settings_apply()
        reload_pc()
        if move:
            job = consoles.MoveJob(*move)
            job.after = reload_pc
            job.start()
            return jsonify(ok=True, job=job.id)
    sec = store.load("secrets", {})
    p3 = ps3versions.settings()
    paths = {k: str(library.path(cfg[k])) for k in library.PATH_KEYS}
    paths["pkg_root"] = cfg["pkg_root"]
    return jsonify({"consoles": consoles_info(), "disc_crf": discpack.crf(), "adrs": store.load("settings", {}).get("adrs", "full"), "usdb_user": sec.get("usdb_user", ""),
                    "usdb_pass_set": bool(sec.get("usdb_pass")), "ps3_keep": p3["keep"], "ps3_dir": p3["dir"],
                    "ps3_usage": ps3versions.usage(), "paths": paths,
                    "lang": store.load("settings", {}).get("lang", "de")})


@app.get("/api/tools")
def api_tools():
    import fetch_tools
    return jsonify(fetch_tools.status())


@app.post("/api/tools/fetch")
def api_tools_fetch():
    return jsonify(ok=True, job=consoles.FetchToolsJob().start().id)


def clean_consoles(items: list) -> list[dict]:
    """Validate the console list from the settings dialog. Ids stay stable (cache, backups, favourites);
    a new console gets "ps4"/"ps3" if free (matches the data from the time with one console each), else ps4-2 …"""
    out, used = [], {str(x.get("id")) for x in items if x.get("id")}
    for x in items:
        t = x.get("type")
        if t not in consoles.TYPES:
            raise ValueError(f"Unbekannter Konsolentyp: {t}")
        host = str(x.get("host", "")).strip()
        if not host:
            raise ValueError("Jede Konsole braucht eine IP-Adresse")
        cid = str(x.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9_-]{1,30}", cid) or any(o["id"] == cid for o in out):
            cid, n = t, 1
            while cid in used:
                n += 1
                cid = f"{t}-{n}"
            used.add(cid)
        try:
            port = int(x.get("port") or consoles.DEFAULT_PORT[t])
        except ValueError:
            raise ValueError(f"Port ungültig: {x.get('port')}") from None
        c = {"id": cid, "type": t, "name": str(x.get("name") or "").strip() or f"{t.upper()} {host}",
             "host": host, "port": port, "enabled": bool(x.get("enabled", True))}
        if t == "ps4":  # how songs get onto this PS4: PKG (/data/pkg + GoldHEN package installer) or disc pack (GoldHEN patch)
            c["install"] = x.get("install") if x.get("install") in ("pkg", "disc") else "pkg"
        out.append(c)
    return out


@app.get("/api/history")
def api_history():
    return jsonify(store.history())


if __name__ == "__main__":
    settings_apply()
    port = cfg.get("http_port", 5077)
    consoles.monitor(cfg, interval=10)
    usdbupdates.background(cfg, on_found=reload_pc)
    threading.Thread(target=songs, daemon=True).start()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, threaded=True)
