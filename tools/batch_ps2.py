"""Convert all PS2-only SingStar songs (not in the PS3 library, not as UltraStar) into PS4 packages.

  python batch_ps2.py [--out build/batch_ps2] [--jobs 3] [--only ID,ID] [--upload]

Songs per disc come from the PAK directories (movie.ipu + music.mib + melody present); duplicates across discs
are taken once. Skipped: songs of the PS3 library (same id, or same artist + title: PS3 version wins),
UltraStar songs (same artist + title), Die grossten Solokunstler (melodies only in an encrypted .chc).
Result: OUT/pkgs/EP9000-CUSA00033_00-<LABEL>.pkg (full names - never rename), OUT/report.md/.json, OUT/logs/.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import songid  # noqa: E402
import local_config  # noqa: E402
from local_config import host  # noqa: E402
from ps2_inventory import key  # noqa: E402
from ps2_to_ps4 import Disc  # noqa: E402

TOOLS = Path(__file__).parent
PS2_ROOT = local_config.path("ps2_root")
EXPORT = local_config.path("ps3_export_dir")
PS4_FTP = f"ftp://{host('ps4')}:2121/data/pkg/"
SKIP_DISCS = {"SingStar Die grossten Solokunstler (Germany)": "Melodien nur verschlüsselt (melodies_10.chc)",
              "SingStar Chartbreaker (Germany)": "alle Songs in der PS3-Bibliothek",
              "SingStar Made in Germany (Germany)": "Melodien nur verschlüsselt (melodies_10.chc)"}


def iso_dir(d: Path) -> Path | None:
    hits = [p for p in d.glob("*_ISO")] + [p for p in d.iterdir() if p.is_dir() and (p / "PACK_EE.PAK").exists()]
    return hits[0] if hits else None


def candidates() -> list[dict]:
    xml = EXPORT / "songs_4_0.xml"  # PS3 library: songs that are there are skipped (optional)
    ps3 = xml.read_text("utf-8", errors="replace") if xml.exists() else ""
    ps3_ids = {int(i) for i in re.findall(r'<SONG ID="(\d+)"', ps3)}
    ps3_keys = {key(m.group(2)) + key(m.group(1)) for m in
                re.finditer(r"<TITLE>([^<]*)</TITLE>.*?<PERFORMANCE_NAME>([^<]*)", ps3, re.S)}
    ids = TOOLS.parent / "song_ids.json"
    us_keys = {key(k) for k in (json.loads(ids.read_text("utf-8")) if ids.exists() else {})}
    rows, seen = [], set()
    for d in sorted(p for p in PS2_ROOT.iterdir() if p.is_dir()):
        iso = iso_dir(d)
        if iso is None:
            continue
        if d.name in SKIP_DISCS:
            print(f"Disc übersprungen: {d.name} ({SKIP_DISCS[d.name]})")
            continue
        disc = Disc(iso)
        meta = disc.songs()
        if disc.iop:
            ids = {int(m.group(1)) for p in disc.iop for e in p.entries
                   for m in [re.match(r"(\d+).movie\.ipu$", e["name"])] if m}
        else:
            ids = {int(p.name) for p in iso.glob("IOP*/*") if p.name.isdigit() and (p / "movie.ipu").exists()}
        lang = "DE" if "Deutsch" in d.name else "EN"
        for sid in sorted(ids):
            if sid in seen or sid not in meta:
                continue
            seen.add(sid)
            a = meta[sid]
            song = f"{a.get('PERFORMANCE_NAME', '?')} - {a['TITLE']}"
            row = {"id": sid, "label": songid.label_for(sid), "song": song, "disc": d.name, "iso": str(iso),
                   "lang": lang, "artist": a.get("PERFORMANCE_NAME", "?"), "title": a["TITLE"]}
            k = key(a["TITLE"]) + key(a.get("PERFORMANCE_NAME", ""))
            if sid in ps3_ids or k in ps3_keys:
                row["skip"] = "in der PS3-Bibliothek"
            elif key(a.get("PERFORMANCE_NAME", "")) + key(a["TITLE"]) in us_keys:
                row["skip"] = "als UltraStar vorhanden"
            rows.append(row)
    return rows


def grab(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else ""


def convert(row: dict, out: Path) -> dict:
    work = out / "work" / row["label"]
    t0, text = time.time(), ""
    try:
        r1 = subprocess.run([sys.executable, str(TOOLS / "ps2_to_ps4.py"), row["iso"], str(row["id"]),
                             str(work / "root"), "--lang", row["lang"]],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        text = r1.stdout + r1.stderr
        if r1.returncode:
            raise RuntimeError(text.strip().splitlines()[-1] if text.strip() else "ps2_to_ps4 failed")
        r2 = subprocess.run([sys.executable, str(TOOLS / "build_dlc.py"), str(work / "root"), "auto",
                             row["song"][:120], str(work)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        text += r2.stdout + r2.stderr
        if r2.returncode:
            raise RuntimeError(text.strip().splitlines()[-1])
        pkg = work / f"EP9000-CUSA00033_00-{row['label']}.pkg"
        shutil.move(str(pkg), out / "pkgs" / pkg.name)
        shutil.rmtree(work / "root", ignore_errors=True)
        row.update({"ok": True, "video": grab(r"video: (.*)$", text), "loudness": grab(r"audio: (.*)$", text),
                    "adrs": grab(r"ADRS: (.*)$", text), "demucs": "Demucs" in text,
                    "mb": round((out / "pkgs" / pkg.name).stat().st_size / 2 ** 20)})
    except Exception as ex:  # noqa: BLE001
        row.update({"ok": False, "error": str(ex)[:300]})
    row["seconds"] = round(time.time() - t0)
    (out / "logs" / f"{row['label']}.log").write_text(text, "utf-8")
    return row


def report(rows: list, out: Path) -> None:
    old = out / "report.json"
    if old.exists():
        new = {r["id"] for r in rows}
        rows = [r for r in json.loads(old.read_text("utf-8")) if r["id"] not in new] + rows
    old.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if r.get("ok") is False]
    skip = [r for r in rows if "skip" in r]
    lines = [f"# PS2-Discs -> PS4: {len(ok)} Pakete, {len(bad)} Fehler, {len(skip)} übersprungen", "",
             f"Gesamtgröße: {sum(r['mb'] for r in ok) / 1024:.1f} GB", "",
             "| ID | Label | Song | Disc | Video | Lautheit | ADRS | MB |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(ok, key=lambda r: r["song"].lower()):
        lines.append(f"| {r['id']} | {r['label'][:6]} | {r['song']} | {r['disc'].replace('SingStar ', '')} | "
                     f"{r['video']} | {r['loudness']} | {r['adrs']}{' (Demucs)' if r['demucs'] else ''} | {r['mb']} |")
    if bad:
        lines += ["", "## Fehler", ""] + [f"- {r['id']} {r['song']}: {r['error']}" for r in bad]
    if skip:
        lines += ["", "## Übersprungen", ""] + [f"- {r['id']} {r['song']} ({r['disc']}): {r['skip']}" for r in skip]
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")


def main():
    global PS2_ROOT, EXPORT
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # song titles with any characters in logs
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=TOOLS.parent / "build" / "batch_ps2")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--only", help="comma-separated song ids")
    ap.add_argument("--ps2-root", type=Path, help=f"extracted PS2 discs (default {PS2_ROOT})")
    ap.add_argument("--export", type=Path, help=f"PS3 library export (default {EXPORT})")
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()
    PS2_ROOT, EXPORT = a.ps2_root or PS2_ROOT, a.export or EXPORT
    for d in ("pkgs", "logs", "work"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    rows = candidates()
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        rows = [r for r in rows if r["id"] in want]
    todo = [r for r in rows if "skip" not in r]
    print(f"{len(todo)} Songs, {len(rows) - len(todo)} übersprungen, {a.jobs} parallel", flush=True)
    done = 0

    def run(r):
        nonlocal done
        convert(r, a.out)
        done += 1
        print(f"[{done}/{len(todo)}] {'ok ' if r.get('ok') else 'FEHLER'} {r['id']} {r['song']} ({r['seconds']} s)"
              + ("" if r.get("ok") else f": {r['error']}"), flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(run, todo))
    report(rows, a.out)
    print(f"-> {a.out / 'report.md'}", flush=True)
    if a.upload:
        for pkg in sorted((a.out / "pkgs").glob("*.pkg")):
            r = subprocess.run(["curl", "-s", "-T", str(pkg), PS4_FTP], capture_output=True)
            print(f"{'hochgeladen' if r.returncode == 0 else 'FEHLER'} {pkg.name}", flush=True)


if __name__ == "__main__":
    main()
