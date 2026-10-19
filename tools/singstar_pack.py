"""Build Pack0.psarc (SingStar PS4 disc-song loader) from UltraStar song folders.

  python singstar_pack.py ULTRASTAR_DIR [ULTRASTAR_DIR ...] [-o Pack0.psarc] [--work DIR]

ULTRASTAR_DIR: a song folder (txt + mp3/video + cover) or a folder with many of them (searched recursively).
Each song is converted with us_to_ps4.py (melody, 30 s preview, -12 LUFS, video kept up to 1080p) and put into one
Pack0.psarc. Converted songs are kept in --work and reused while the UltraStar folder is unchanged, so adding songs
later only converts the new ones. Song ids (45300 and up) are stored in song_ids.json and stay the same per song.
Duets (P1/P2) are not supported yet and are skipped.

Needs Python 3.10+ and ffmpeg/ffprobe on PATH. Upload: see README (ps4_install.py).
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "lib" if (HERE / "lib").is_dir() else HERE  # release layout: modules in lib/
sys.path.insert(0, str(LIB))
import ps4_discpack  # noqa: E402
import to_ps3  # noqa: E402


def song_dirs(roots: list[Path]) -> list[Path]:
    """Folders with an UltraStar txt (#TITLE and #ARTIST in the head)."""
    found = []
    for root in roots:
        for txt in sorted(root.rglob("*.txt")) if root.is_dir() else []:
            try:
                head = txt.read_bytes()[:4000].decode("utf-8", "replace").upper()
            except OSError:
                continue
            if "#TITLE:" in head and "#ARTIST:" in head and txt.parent not in found:
                found.append(txt.parent)
    return found


def newest(d: Path) -> float:
    return max((p.stat().st_mtime for p in d.iterdir() if p.is_file()), default=0.0)


def convert(src: Path, work: Path) -> tuple[Path | None, str]:
    """UltraStar folder -> song folder for ps4_discpack (cached). Returns (folder, message)."""
    key = re.sub(r"[^\w.-]+", "_", src.name)[:60] + "_" + hashlib.md5(str(src).encode("utf-8")).hexdigest()[:8]
    out = work / "songs" / key
    if (out / "entry.json").exists() and (out / "entry.json").stat().st_mtime >= newest(src):
        return out, "unchanged"
    shutil.rmtree(out, ignore_errors=True)
    tmp = work / "tmp" / key
    shutil.rmtree(tmp, ignore_errors=True)
    r = subprocess.run([sys.executable, str(LIB / "us_to_ps4.py"), str(src), str(tmp), "--rap", "off"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        lines = [ln for ln in (r.stderr or r.stdout).strip().splitlines() if ln.strip()]
        msg = lines[-1] if lines else f"exit code {r.returncode}"
        return None, "skipped (duet)" if "duet" in msg else f"FAILED: {msg}"
    try:
        pack = next(tmp.glob("Prod_Sku_*"))
        sid = int(next(p.name for p in pack.iterdir() if p.is_dir() and p.name.isdigit()))
        to_ps3.pack_to_ps3(pack, sid, out, "ultrastar", ps4_media=True)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(out, ignore_errors=True)
        return None, f"FAILED: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out, "converted"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("Pack0.psarc"))
    ap.add_argument("--work", type=Path, default=HERE / "work", help="cache of converted songs (default: ./work)")
    a = ap.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found - install ffmpeg and put it on PATH")
    dirs = song_dirs(a.folders)
    if not dirs:
        sys.exit("no UltraStar songs (txt with #TITLE/#ARTIST) found")
    print(f"{len(dirs)} UltraStar songs found")
    a.work.mkdir(parents=True, exist_ok=True)
    ok, ids, failed = [], {}, []
    t0 = time.time()
    for i, d in enumerate(dirs, 1):
        out, msg = convert(d, a.work)
        if out:
            e = json.loads((out / "entry.json").read_text("utf-8"))
            sid = e["ps3_id"]
            if sid in ids:
                msg = f"skipped (same song as {ids[sid].name})"
            else:
                ids[sid] = d
                ok.append(out)
        if msg.startswith(("FAILED", "skipped")):
            failed.append(f"{d.name}: {msg}")
        print(f"[{i}/{len(dirs)}] {d.name}: {msg}", flush=True)
    if not ok:
        sys.exit("no song could be converted")
    print(f"building {a.out} with {len(ok)} songs ...", flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    ps4_discpack.build(a.out.resolve(), ok)
    print(f"\n{a.out}: {len(ok)} songs, {a.out.stat().st_size / 2**20:.0f} MB ({(time.time() - t0) / 60:.1f} min)")
    if failed:
        print(f"{len(failed)} not included:")
        for f in failed:
            print("  " + f)
    print("next: python ps4_install.py <PS4-IP> " + str(a.out))


if __name__ == "__main__":
    main()
