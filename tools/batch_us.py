"""Convert all UltraStar songs into installable SingStar PS4 packages, with a report.

  python batch_us.py [--root DIR] [--out build/batch] [--jobs 3] [--only TEXT] [--upload]

Per song: us_to_ps4.py (--adrs auto, rap from rap_songs.json) -> build_dlc.py auto. Song ids are assigned
up front, one after the other (song_ids.json), so the parallel conversions never race for a new id.
Skipped: duets (P1/P2, not supported yet), folders without audio. Errors are caught per song.
Result: OUT/pkgs/EP9000-CUSA00033_00-<LABEL>.pkg (full content-id names - never rename them),
OUT/report.md + OUT/report.json, OUT/logs/<song>.log.
--upload: FTP the packages to /data/pkg/ on the PS4 afterwards (install there with the GoldHEN package installer, whole folder at once).
"""
import argparse
import json
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
from us_to_ps4 import find_file, parse, song_id_for  # noqa: E402

TOOLS = Path(__file__).parent
US_ROOT = local_config.path("ultrastar_dir")
PS4_FTP = f"ftp://{host('ps4')}:2121/data/pkg/"


def prepare(folder: Path) -> dict:
    try:
        head, lines, duet = parse(next(folder.glob("*.txt")))
    except Exception as ex:  # noqa: BLE001
        return {"song": folder.name, "skip": f"txt nicht lesbar: {ex}"}
    if duet:
        return {"song": folder.name, "skip": "Duett (P1/P2) noch nicht unterstützt"}
    if not find_file(folder, head.get("MP3") or head.get("AUDIO"), (".mp3", ".ogg", ".m4a", ".wav", ".flac")):
        return {"song": folder.name, "skip": "keine Audiodatei"}
    sid = song_id_for(head["ARTIST"], head["TITLE"], None)
    return {"song": folder.name, "id": sid, "label": songid.label_for(sid)}


def grab(pattern: str, text: str, default=""):
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else default


def convert(folder: Path, row: dict, out: Path) -> dict:
    work = out / "work" / row["label"]
    log = out / "logs" / f"{row['label']}.log"
    t0 = time.time()
    try:
        r1 = subprocess.run([sys.executable, str(TOOLS / "us_to_ps4.py"), str(folder), str(work / "root"),
                             "--id", str(row["id"]), "--adrs", "auto"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        text = r1.stdout + r1.stderr
        if r1.returncode:
            raise RuntimeError(text.strip().splitlines()[-1] if text.strip() else "us_to_ps4 failed")
        r2 = subprocess.run([sys.executable, str(TOOLS / "build_dlc.py"), str(work / "root"), "auto",
                             folder.name[:120], str(work)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        text += r2.stdout + r2.stderr
        if r2.returncode:
            raise RuntimeError(text.strip().splitlines()[-1])
        pkg = work / f"EP9000-CUSA00033_00-{row['label']}.pkg"
        shutil.move(str(pkg), out / "pkgs" / pkg.name)
        shutil.rmtree(work / "root", ignore_errors=True)  # keep only the package (space)
        row.update({
            "ok": True,
            "video": grab(r"video: (copied|encoded)", text),
            "fps": grab(r"@ ([\d.]+) fps", text),
            "size": grab(r"video (\d+x\d+)", text),
            "loudness": grab(r"audio: (.*? LUFS -> .*?LUFS)", text),
            "preview": grab(r"preview/medley at [\d.]+ s \((.*)\)$", text),
            "adrs": grab(r"ADRS auto: (\d+/\d+) segments", text) or
                    ("nicht geeignet" if "not rated suitable" in text else "keine Stems" if "no stems" in text else ""),
            "rap": grab(r"rap: (\d+) of \d+ lines", text),
            "gap_error": grab(r"\(error ([+-]\d+ ms)\)", text),
            "mb": round((out / "pkgs" / pkg.name).stat().st_size / 2 ** 20),
        })
    except Exception as ex:  # noqa: BLE001
        text = locals().get("text", "")
        row.update({"ok": False, "error": str(ex)[:300]})
    row["seconds"] = round(time.time() - t0)
    log.write_text(locals().get("text", ""), "utf-8")
    return row


def report(rows: list, out: Path) -> None:
    old = out / "report.json"
    if old.exists():  # re-runs of single songs (--only) update the full report
        new = {r["song"] for r in rows}
        rows = [r for r in json.loads(old.read_text("utf-8")) if r["song"] not in new] + rows
    (out / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if r.get("ok") is False]
    skip = [r for r in rows if "skip" in r]
    lines = [f"# UltraStar -> PS4: {len(ok)} Pakete, {len(bad)} Fehler, {len(skip)} übersprungen", "",
             f"Gesamtgröße: {sum(r['mb'] for r in ok) / 1024:.1f} GB", "",
             "| ID | Label | Song | Video | fps | Lautheit | Vorschau | ADRS | Rap | MB |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(ok, key=lambda r: r["song"].lower()):
        lines.append(f"| {r['id']} | {r['label'][:6]} | {r['song']} | {r['video']} {r['size']} | {r['fps']} | "
                     f"{r['loudness']} | {r['preview']} | {r['adrs']} | {r['rap']} | {r['mb']} |")
    if bad:
        lines += ["", "## Fehler", ""] + [f"- {r['song']}: {r['error']}" for r in bad]
    if skip:
        lines += ["", "## Übersprungen", ""] + [f"- {r['song']}: {r['skip']}" for r in skip]
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")


def upload(out: Path) -> None:
    for pkg in sorted((out / "pkgs").glob("*.pkg")):
        r = subprocess.run(["curl", "-s", "-T", str(pkg), PS4_FTP], capture_output=True)
        print(f"{'hochgeladen' if r.returncode == 0 else 'FEHLER'} {pkg.name}", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # song titles with any characters in logs
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=US_ROOT)
    ap.add_argument("--out", type=Path, default=TOOLS.parent / "build" / "batch")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--only", help="only folders containing this text, or @FILE: one folder name per line")
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()
    for d in ("pkgs", "logs", "work"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    if a.only and a.only.startswith("@"):
        names = set(Path(a.only[1:]).read_text("utf-8").splitlines())
        folders = sorted(p for p in a.root.iterdir() if p.is_dir() and p.name in names)
    else:
        folders = sorted(p for p in a.root.iterdir() if p.is_dir() and (not a.only or a.only in p.name))
    rows = [prepare(f) for f in folders]  # sequential: assigns new song ids safely
    todo = [(f, r) for f, r in zip(folders, rows) if "skip" not in r]
    labels = [r["label"] for _, r in todo]
    if len(labels) != len(set(labels)):
        sys.exit("doppelte Song-IDs - song_ids.json prüfen")
    print(f"{len(todo)} Songs, {len(rows) - len(todo)} übersprungen, {a.jobs} parallel", flush=True)
    done = 0

    def run(item):
        nonlocal done
        r = convert(item[0], item[1], a.out)
        done += 1
        print(f"[{done}/{len(todo)}] {'ok ' if r.get('ok') else 'FEHLER'} {r['song']} ({r['seconds']} s)"
              + ("" if r.get("ok") else f": {r['error']}"), flush=True)
        return r

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(run, todo))
    report(rows, a.out)
    print(f"-> {a.out / 'report.md'}", flush=True)
    if a.upload:
        upload(a.out)


if __name__ == "__main__":
    main()
