"""Set up the download0 link once: /download0/Pack0.psarc -> /av_contents/video/ss/Pack0.psarc.

SingStar's disc-song loader only accepts /download0/ paths, download0 is a fixed 1 GiB image. The image is a
plain UFS2, so Pack0.psarc inside it is turned into a symlink to the big user partition
(FTP: /user/av_contents/video/ss/Pack0.psarc). See docs/TECHNIK.md. Needs GoldHEN (FTP) and the remote
control (tools/dev/remote/ps4ctl.bat) for closing/starting SingStar.

  python tools/dl0_link.py            check, and create the link if missing
  python tools/dl0_link.py --check    only report

Steps: SingStar running -> replace download0/Pack0.psarc by an empty file (frees its blocks in the image) ->
close SingStar -> download download0.dat (copy kept as build/dl0_link/download0.dat.before) -> make the empty file a
fast symlink (ufs_symlink.py) -> upload -> start SingStar -> check.
"""
import ftplib
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "manager"))
import ufs_symlink  # noqa: E402

PS4CTL = ROOT / "tools" / "dev" / "remote" / "ps4ctl.bat"
IMAGE = "/user/download/CUSA00033/download0.dat"
DL0 = "/mnt/sandbox/CUSA00033_000/download0"
PACK = "Pack0.psarc"
TARGET = "/av_contents/video/ss/Pack0.psarc"      # as the game sees it
EXT_DIR = "/user/av_contents/video/ss"            # same folder via FTP
WORK = ROOT / "build" / "dl0_link"


def host():
    return json.loads((ROOT / "tools" / "dev" / "remote" / "ps4ctl.json").read_text(encoding="utf-8"))["host"]


def ftp():
    f = ftplib.FTP()
    f.connect(host(), 2121, timeout=60)
    f.login()
    f.voidcmd("TYPE I")
    return f


def ps4ctl(*args):
    r = subprocess.run([str(PS4CTL), "--timeout", "250", *args], capture_output=True, text=True, encoding="utf-8")
    print("  ps4ctl", " ".join(args), "->", (r.stdout or r.stderr).strip())
    if r.returncode:
        sys.exit(f"ps4ctl {' '.join(args)} fehlgeschlagen")


def link_state(f):
    """Same rule as manager/discpack.link_state: link = listed, but SIZE fails (target only in the game's view)."""
    try:
        names = [n.rstrip("/").split("/")[-1] for n in f.nlst(DL0)]
    except ftplib.all_errors:
        return None
    if PACK not in names:
        return "missing"
    try:
        f.size(f"{DL0}/{PACK}")
        return "file"
    except ftplib.all_errors:
        return "link"


def main():
    ps4ctl("start")
    time.sleep(5)
    f = ftp()
    st = link_state(f)
    print("Zustand:", st)
    if st == "link" or "--check" in sys.argv:
        f.close()
        return
    if st is None:
        sys.exit("download0 nicht erreichbar, obwohl SingStar laufen sollte")
    # 1. leere Datei an die Stelle von Pack0.psarc (gibt bei einer echten Datei deren Blöcke im Image frei)
    try:
        f.mkd(EXT_DIR)
    except ftplib.all_errors:
        pass
    if st == "file":
        size = f.size(f"{DL0}/{PACK}")
        print(f"  echte Datei in download0 ({size / 2**20:.0f} MB) wird geleert – Pack bitte nach {EXT_DIR} hochladen")
    f.storbinary(f"STOR {DL0}/{PACK}", io.BytesIO(b""))
    f.close()
    # 2. Spiel schließen, Image holen
    ps4ctl("close")
    WORK.mkdir(parents=True, exist_ok=True)
    img = WORK / "download0.dat"
    f = ftp()
    with open(img, "wb") as fh:
        f.retrbinary(f"RETR {IMAGE}", fh.write, 1 << 20)
    f.close()
    shutil.copyfile(img, WORK / "download0.dat.before")
    print(f"  Image geladen ({img.stat().st_size / 2**20:.0f} MB), Sicherung download0.dat.before")
    # 3. Symlink setzen
    fs = ufs_symlink.Ufs2(str(img), writable=True)
    ufs_symlink.make_link(fs, PACK, TARGET, write=True)
    fs.f.close()
    # 4. hochladen (Spiel ist geschlossen)
    f = ftp()
    with open(img, "rb") as fh:
        f.storbinary(f"STOR {IMAGE}", fh, 1 << 20)
    if f.size(IMAGE) != img.stat().st_size:
        sys.exit("Größe nach dem Hochladen stimmt nicht – Sicherung download0.dat.before zurückspielen!")
    f.close()
    # 5. starten, prüfen
    ps4ctl("start")
    time.sleep(5)
    f = ftp()
    st = link_state(f)
    f.close()
    print("Zustand danach:", st)
    if st != "link":
        sys.exit("Verweis nicht erkannt – Sicherung build/dl0_link/download0.dat.before prüfen")


if __name__ == "__main__":
    main()
