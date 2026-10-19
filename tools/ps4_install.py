"""Set up the SingStar disc-song loader on a PS4 with GoldHEN and upload Pack0.psarc.

  python ps4_install.py PS4_IP [Pack0.psarc]      patch + upload + link (link only while SingStar runs)
  python ps4_install.py PS4_IP --check            show the state, change nothing

Steps (GoldHEN FTP on port 2121 and BinLoader on port 9090 must be on):
  1. GoldHEN game patch for SingStar (CUSA00033 v01.10): entry in /data/GoldHEN/patches/xml/CUSA00033.xml (an existing
     file is kept and saved to ./backup first) and switched on. Needs the game_patch plugin and the plugin loader.
  2. Pack0.psarc -> /user/av_contents/video/ss/Pack0.psarc (works with SingStar closed, no size limit).
  3. Link download0/Pack0.psarc -> that file, made by the payload dl0link.elf. download0 only exists while SingStar
     runs: if it is closed, start SingStar and run the script again.
Then restart SingStar: the songs appear with the filter "Songs on disc".
"""
import ftplib
import io
import re
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "lib" if (HERE / "lib").is_dir() else HERE
sys.path.insert(0, str(LIB))
import ps4_discpack  # noqa: E402

FTP_PORT, LOADER_PORT = 2121, 9090
DL0 = "/mnt/sandbox/CUSA00033_000/download0"
EXT = "/user/av_contents/video/ss"
PACK = "Pack0.psarc"
PATCH_XML = "/data/GoldHEN/patches/xml/CUSA00033.xml"
PATCH_SETTINGS = "/data/GoldHEN/patches/settings"
PAYLOAD = next((p for p in (HERE / "ps4" / "dl0link.elf", HERE / "payload" / "dl0link.elf") if p.exists()), None)


def patch_hash(name: str, title: str = "SingStar", app_ver: str = "01.10", elf: str = "eboot.bin") -> str:
    """GoldHEN game_patch switch file name: djb2 (h*33 ^ c, 64 bit) over Title+Name+AppVer+xml path+AppElf."""
    h = 5381
    for c in (title + name + app_ver + PATCH_XML + elf).encode("utf-8"):
        h = ((h * 33) ^ c) & 0xFFFFFFFFFFFFFFFF
    return f"0x{h:016x}"


def retr(f: ftplib.FTP, path: str) -> bytes | None:
    buf = io.BytesIO()
    try:
        f.retrbinary(f"RETR {path}", buf.write)
    except ftplib.all_errors:
        return None
    return buf.getvalue()


def link_state(f: ftplib.FTP) -> str | None:
    """"link", "file" (real Pack0.psarc in download0), "missing", None = SingStar not running.
    The FTP server follows the link and cannot find the target (only the game sees /av_contents): NLST lists the
    link, SIZE fails."""
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


def install_patch(f: ftplib.FTP, host: str) -> None:
    name = ps4_discpack.PATCH_NAME
    meta = re.search(r"    <Metadata.*?</Metadata>\n", ps4_discpack.patch_xml(), re.S).group(0)
    old = retr(f, PATCH_XML)
    xml = old.decode("utf-8", "replace") if old else ""
    if f'Name="{name}"' in xml:
        print("patch: already in CUSA00033.xml")
    else:
        if xml.strip():
            bak = HERE / "backup" / f"CUSA00033_{host}_{time.strftime('%Y%m%d_%H%M%S')}.xml"
            bak.parent.mkdir(exist_ok=True)
            bak.write_bytes(old)
            xml = xml.replace("</Patch>", meta + "</Patch>", 1)
            print(f"patch: added to the existing CUSA00033.xml (old file saved: {bak})")
        else:
            xml = ps4_discpack.patch_xml()
            print("patch: CUSA00033.xml written")
        f.storbinary(f"STOR {PATCH_XML}", io.BytesIO(xml.encode("utf-8")))
    f.storbinary(f"STOR {PATCH_SETTINGS}/{patch_hash(name)}.txt", io.BytesIO(b"1\n"))
    print("patch: switched on")
    for other in re.findall(r'Name="([^"]+)"', xml):  # other patches of the same loader address must be off
        if other != name and "Pack0.psarc" in other:
            f.storbinary(f"STOR {PATCH_SETTINGS}/{patch_hash(other)}.txt", io.BytesIO(b"0\n"))
            print(f"patch: switched off older variant '{other}'")
    ini = (retr(f, "/data/GoldHEN/plugins.ini") or b"").decode("utf-8", "replace")
    if "game_patch" not in ini:
        print("WARNING: game_patch.prx is not listed in /data/GoldHEN/plugins.ini - install the GoldHEN game_patch "
              "plugin, otherwise the patch does nothing")


def upload(f: ftplib.FTP, pack: Path) -> None:
    for d in ("/user/av_contents", "/user/av_contents/video", EXT):
        try:
            f.mkd(d)
        except ftplib.all_errors:
            pass  # exists
    size = pack.stat().st_size
    names = [n.rstrip("/").split("/")[-1] for n in f.nlst(EXT)]
    print(f"upload: {pack.name} ({size / 2**20:.0f} MB) -> {EXT}/{PACK}")
    sent = [0]

    def progress(block):
        sent[0] += len(block)
        print(f"\r  {sent[0] * 100 // size:3d} %", end="", flush=True)

    with open(pack, "rb") as fh:
        f.storbinary(f"STOR {EXT}/{PACK}.new", fh, blocksize=1 << 20, callback=progress)
    print()
    if f.size(f"{EXT}/{PACK}.new") != size:
        raise SystemExit("upload: size on the PS4 does not match - try again")
    if PACK in names:
        if PACK + ".old" in names:
            f.delete(f"{EXT}/{PACK}.old")
        f.rename(f"{EXT}/{PACK}", f"{EXT}/{PACK}.old")
    f.rename(f"{EXT}/{PACK}.new", f"{EXT}/{PACK}")
    if PACK in names:
        f.delete(f"{EXT}/{PACK}.old")
    print("upload: done")


def send_payload(host: str) -> None:
    if PAYLOAD is None:
        raise SystemExit("dl0link.elf not found (expected in ps4/)")
    with socket.create_connection((host, LOADER_PORT), timeout=10) as s:
        s.sendall(PAYLOAD.read_bytes())
    print(f"link: payload {PAYLOAD.name} sent to port {LOADER_PORT}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    check = "--check" in sys.argv
    if not args:
        sys.exit(__doc__)
    host = args[0]
    pack = Path(args[1]) if len(args) > 1 else None
    if pack and not pack.is_file():
        sys.exit(f"{pack} not found")
    f = ftplib.FTP()
    try:
        f.connect(host, FTP_PORT, timeout=30)
        f.login()
    except (OSError, ftplib.all_errors) as e:
        sys.exit(f"no FTP connection to {host}:{FTP_PORT} ({e}) - is GoldHEN running with FTP on?")
    try:
        if check:
            xml = (retr(f, PATCH_XML) or b"").decode("utf-8", "replace")
            on = (retr(f, f"{PATCH_SETTINGS}/{patch_hash(ps4_discpack.PATCH_NAME)}.txt") or b"").strip()
            print(f"patch: {'in CUSA00033.xml' if ps4_discpack.PATCH_NAME in xml else 'missing'}, "
                  f"switch {on.decode() or 'not set'}")
            try:
                print(f"pack: {f.size(f'{EXT}/{PACK}') / 2**20:.0f} MB in {EXT}")
            except ftplib.all_errors:
                print("pack: none uploaded")
            print(f"link: {link_state(f) or 'unknown (SingStar not running)'}")
            return
        install_patch(f, host)
        if pack:
            upload(f, pack)
        state = link_state(f)
    finally:
        f.close()
    if state == "link":
        print("link: in place")
    elif state is None:
        print("link: SingStar is not running - start SingStar and run this script again (without the pack it only "
              "does the patch check and the link): python ps4_install.py " + host)
        return
    else:
        send_payload(host)
        time.sleep(3)
        f = ftplib.FTP()
        f.connect(host, FTP_PORT, timeout=30)
        f.login()
        try:
            state = link_state(f)
        finally:
            f.close()
        if state != "link":
            sys.exit(f"link: not created (state: {state}) - see README, 'Problems'")
        print("link: created")
    print("\nDone. Restart SingStar (close it completely and start it again); the songs are listed with the filter "
          "'Songs on disc'.")


if __name__ == "__main__":
    main()
