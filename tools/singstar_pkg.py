"""Convert UltraStar songs into installable SingStar PS4 song packages (fake DLC .pkg, one per song).

  python singstar_pkg.py ULTRASTAR_DIR [ULTRASTAR_DIR ...] [-o pkgs] [--upload PS4_IP]

ULTRASTAR_DIR: a song folder (txt + mp3/video + cover) or a folder with many of them (searched recursively).
Result: one EP9000-CUSA00033_00-130XXX0000000000.pkg per song in -o (default ./pkgs). NEVER rename these files -
the PS4 needs the full content-id name. Songs that were already built and are unchanged are skipped.
Song ids (45300 and up) are kept in song_ids.json; keep that file, otherwise a song gets a new id on the next build.
Duets (P1/P2) are not supported yet and are skipped.
--upload: copy the new packages via GoldHEN FTP (port 2121) to /data/pkg/ on the PS4; install them there with the
GoldHEN package installer.

Needs Python 3.10+, ffmpeg/ffprobe on PATH and the .NET runtime (any version from 3.1, e.g. .NET 8) for PkgTool.
"""
import argparse
import ftplib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "lib" if (HERE / "lib").is_dir() else HERE
sys.path.insert(0, str(LIB))
import build_dlc  # noqa: E402
from singstar_pack import newest, song_dirs  # noqa: E402
from us_to_ps4 import parse  # noqa: E402


def build(src: Path, work: Path, out: Path) -> tuple[Path | None, str]:
    """UltraStar folder -> .pkg in out. Returns (pkg, message)."""
    try:
        head, _, duet = parse(next(src.glob("*.txt")))
    except Exception as e:  # noqa: BLE001
        return None, f"FAILED: cannot read the txt ({e})"
    if duet:
        return None, "skipped (duet)"
    tmp = work / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    r = subprocess.run([sys.executable, str(LIB / "us_to_ps4.py"), str(src), str(tmp / "root"), "--rap", "off"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        lines = [ln for ln in (r.stderr or r.stdout).strip().splitlines() if ln.strip()]
        return None, "FAILED: " + (lines[-1] if lines else f"exit code {r.returncode}")
    title = f"{head['ARTIST']} - {head['TITLE']}"[:127]
    try:
        b = subprocess.run([sys.executable, str(LIB / "build_dlc.py"), str(tmp / "root"), "auto", title,
                            str(tmp / "out")], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if b.returncode != 0:
            lines = [ln for ln in (b.stderr or b.stdout).strip().splitlines() if ln.strip()]
            return None, "FAILED (package): " + (lines[-1] if lines else f"exit code {b.returncode}")
        pkg = next((tmp / "out").glob("*.pkg"))
        dst = out / pkg.name
        shutil.move(str(pkg), dst)
        return dst, "built"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def upload(host: str, pkgs: list[Path]) -> None:
    f = ftplib.FTP()
    try:
        f.connect(host, 2121, timeout=60)
        f.login()
    except (OSError, ftplib.all_errors) as e:
        sys.exit(f"no FTP connection to {host}:2121 ({e}) - is GoldHEN running with FTP on?")
    try:
        try:
            f.mkd("/data/pkg")
        except ftplib.all_errors:
            pass
        for i, p in enumerate(pkgs, 1):
            try:
                if f.size(f"/data/pkg/{p.name}") == p.stat().st_size:
                    print(f"[{i}/{len(pkgs)}] {p.name}: already on the PS4")
                    continue
            except ftplib.all_errors:
                pass
            with open(p, "rb") as fh:
                f.storbinary(f"STOR /data/pkg/{p.name}", fh, blocksize=1 << 20)
            print(f"[{i}/{len(pkgs)}] {p.name}: uploaded ({p.stat().st_size / 2**20:.0f} MB)", flush=True)
    finally:
        f.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=HERE / "pkgs")
    ap.add_argument("--work", type=Path, default=HERE / "work")
    ap.add_argument("--upload", metavar="PS4_IP")
    a = ap.parse_args()
    for tool in ("ffmpeg", "ffprobe", "dotnet"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found - " + ("install the .NET runtime" if tool == "dotnet"
                                                else "install ffmpeg and put it on PATH"))
    dirs = song_dirs(a.folders)
    if not dirs:
        sys.exit("no UltraStar songs (txt with #TITLE/#ARTIST) found")
    print(f"{len(dirs)} UltraStar songs found")
    a.out.mkdir(parents=True, exist_ok=True)
    a.work.mkdir(parents=True, exist_ok=True)
    index_file = a.work / "pkg_index.json"  # source folder -> package file, to skip unchanged songs
    index = json.loads(index_file.read_text("utf-8")) if index_file.exists() else {}
    built, failed, t0 = [], [], time.time()
    for i, d in enumerate(dirs, 1):
        known = index.get(str(d))
        if known and (a.out / known).exists() and (a.out / known).stat().st_mtime >= newest(d):
            msg, pkg = "unchanged", a.out / known
        else:
            pkg, msg = build(d, a.work, a.out)
            if pkg:
                index[str(d)] = pkg.name
                index_file.write_text(json.dumps(index, ensure_ascii=False, indent=1), "utf-8")
                built.append(pkg)
            else:
                failed.append(f"{d.name}: {msg}")
        print(f"[{i}/{len(dirs)}] {d.name}: {msg}" + (f" -> {pkg.name}" if pkg else ""), flush=True)
    print(f"\n{len(built)} packages built in {a.out} ({(time.time() - t0) / 60:.1f} min)")
    if failed:
        print(f"{len(failed)} not built:")
        for f in failed:
            print("  " + f)
    if a.upload:
        todo = sorted(a.out.glob("EP9000-CUSA00033_00-*.pkg"))
        print(f"\nuploading {len(todo)} packages to {a.upload}:/data/pkg/ ...")
        upload(a.upload, todo)
        print("done - install them on the PS4 with the GoldHEN package installer")


if __name__ == "__main__":
    main()
