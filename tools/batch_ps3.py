"""Convert the SingStar PS3 library (Toolbox export) into installable SingStar PS4 packages, with a report.

  python batch_ps3.py [--export DIR] [--out build/batch_ps3] [--jobs 3] [--only ID,ID,...] [--upload]

Takes every official song (id < 40000) plus the custom songs that have no UltraStar counterpart (the three
duets). Official ids stay, custom 600xx -> 45xxx (songid.ps4_id). Official songs that also exist as UltraStar
version share the id and replace it (official version wins, decision 28.09.).
Per song: ps3_to_ps4.py auto (loudness, aspect fix, song end, tempo, rap block, preview) -> build_dlc.py auto.
Result: OUT/pkgs/EP9000-CUSA00033_00-<LABEL>.pkg (full names - never rename), OUT/report.md/.json, OUT/logs/.
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

TOOLS = Path(__file__).parent
EXPORT = local_config.path("ps3_export_dir")
PS4_FTP = f"ftp://{host('ps4')}:2121/data/pkg/"
SKIP = {28105: "video.mp4 beschädigt (neu aus der Toolbox exportieren)"}
EXTRA_CUSTOM = {60066, 60095, 60008}  # duets without an UltraStar conversion (P1/P2 not supported there)


def songs(export: Path) -> list[dict]:
    xml = (export / "songs_4_0.xml").read_text("utf-8", errors="replace")
    out = []
    for m in re.finditer(r'<SONG ID="(\d+)".*?</SONG>', xml, re.S):
        sid = int(m.group(1))
        if sid >= 40000 and sid not in EXTRA_CUSTOM:
            continue
        title = re.search(r"<TITLE>(.*?)</TITLE>", m.group(0), re.S).group(1)
        artist = re.search(r"<PERFORMANCE_NAME>(.*?)</PERFORMANCE_NAME>", m.group(0), re.S).group(1)
        ps4 = songid.ps4_id(sid) if sid >= 40000 else sid
        row = {"id": sid, "ps4": ps4, "label": songid.label_for(ps4), "song": f"{artist} - {title}"}
        if sid in SKIP and export == EXPORT:  # SKIP = broken files of the Toolbox export only
            row["skip"] = SKIP[sid]
        out.append(row)
    return out


def grab(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else ""


def convert(row: dict, export: Path, out: Path) -> dict:
    work = out / "work" / row["label"]
    t0 = time.time()
    text = ""
    try:
        r1 = subprocess.run([sys.executable, str(TOOLS / "ps3_to_ps4.py"), str(export), str(work / "root"), "auto",
                             f"{row['id']}={row['ps4']}", "--name", row["song"][:100]],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        text = r1.stdout + r1.stderr
        if r1.returncode:
            raise RuntimeError(text.strip().splitlines()[-1] if text.strip() else "ps3_to_ps4 failed")
        r2 = subprocess.run([sys.executable, str(TOOLS / "build_dlc.py"), str(work / "root"), "auto",
                             row["song"][:120], str(work)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        text += r2.stdout + r2.stderr
        if r2.returncode:
            raise RuntimeError(text.strip().splitlines()[-1])
        pkg = work / f"EP9000-CUSA00033_00-{row['label']}.pkg"
        shutil.move(str(pkg), out / "pkgs" / pkg.name)
        shutil.rmtree(work / "root", ignore_errors=True)
        root_xml = text
        row.update({"ok": True, "video": grab(r"video: (.*)$", text), "loudness": grab(r"audio: (.*)$", text),
                    "melody": grab(r"melody: (.*)$", root_xml),
                    "mb": round((out / "pkgs" / pkg.name).stat().st_size / 2 ** 20)})
    except Exception as ex:  # noqa: BLE001
        row.update({"ok": False, "error": str(ex)[:300]})
    row["seconds"] = round(time.time() - t0)
    (out / "logs" / f"{row['label']}.log").write_text(text, "utf-8")
    return row


def report(rows: list, out: Path) -> None:
    old = out / "report.json"
    if old.exists():  # partial re-runs (--only) update the full report
        new = {r["id"] for r in rows}
        rows = [r for r in json.loads(old.read_text("utf-8")) if r["id"] not in new] + rows
    old.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if r.get("ok") is False]
    skip = [r for r in rows if "skip" in r]
    lines = [f"# PS3-Bibliothek -> PS4: {len(ok)} Pakete, {len(bad)} Fehler, {len(skip)} übersprungen", "",
             f"Gesamtgröße: {sum(r['mb'] for r in ok) / 1024:.1f} GB", "",
             "| ID | Label | Song | Video | Lautheit | Melodie | MB |", "|---|---|---|---|---|---|---|"]
    for r in sorted(ok, key=lambda r: r["song"].lower()):
        lines.append(f"| {r['ps4']} | {r['label'][:6]} | {r['song']} | {r['video']} | {r['loudness']} | "
                     f"{r['melody']} | {r['mb']} |")
    if bad:
        lines += ["", "## Fehler", ""] + [f"- {r['id']} {r['song']}: {r['error']}" for r in bad]
    if skip:
        lines += ["", "## Übersprungen", ""] + [f"- {r['id']} {r['song']}: {r['skip']}" for r in skip]
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # song titles with any characters in logs
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", type=Path, default=EXPORT)
    ap.add_argument("--out", type=Path, default=TOOLS.parent / "build" / "batch_ps3")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--only", help="comma-separated PS3 song ids")
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()
    for d in ("pkgs", "logs", "work"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    rows = songs(a.export)
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        rows = [r for r in rows if r["id"] in want]
    todo = [r for r in rows if "skip" not in r]
    labels = [r["label"] for r in todo]
    if len(labels) != len(set(labels)):
        sys.exit("doppelte Labels")
    print(f"{len(todo)} Songs, {len(rows) - len(todo)} übersprungen, {a.jobs} parallel", flush=True)
    done = 0

    def run(r):
        nonlocal done
        convert(r, a.export, a.out)
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
