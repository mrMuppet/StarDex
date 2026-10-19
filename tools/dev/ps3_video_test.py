"""Test whether SingStar PS3 plays 1080p videos: swap the video of one song on the PS3 and restore it afterwards.

  python ps3_video_test.py prepare            build build/ps3_1080p_test/video.mp4 (1080p picture + PS3 audio)
  python ps3_video_test.py apply  [--xml]     back up the PS3 original, upload the test video
                                              (--xml: also set VIDEO WIDTH/HEIGHT in songs_4_0.xml, backup first)
  python ps3_video_test.py restore            put the original video (and songs_4_0.xml) back

Test song: 257ers - Holland (PS3 60105, 720x404) - the UltraStar video (1920x1080, 25 fps, 212.08 s) is the same
cut, so picture and melody stay in sync. Audio stays the exact PS3 track (stream copy).
"""
import ftplib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/
import local_config  # noqa: E402
from local_config import host  # noqa: E402

SONG = 60105
US_VIDEO = local_config.path("ultrastar_dir") / "257ers - Holland" / "257ers - Holland.mp4"
LOCAL_EXPORT = local_config.path("ps3_export_dir")
OUT = Path(__file__).resolve().parents[2] / "build" / "ps3_1080p_test"
REMOTE = "/dev_hdd0/FileSystem/Export"
HOST = host("ps3")


def ftp() -> ftplib.FTP:
    f = ftplib.FTP()
    f.connect(HOST, 21, timeout=30)
    f.login()
    f.voidcmd("TYPE I")
    return f


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    src_ps3 = LOCAL_EXPORT / str(SONG) / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(US_VIDEO), "-i", str(src_ps3),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart",
                    "-shortest", str(OUT / "video.mp4")], check=True)
    print(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_name,profile,level,width,height,r_frame_rate:format=duration",
                          "-of", "compact", str(OUT / "video.mp4")], capture_output=True, text=True).stdout)


def apply(xml: bool):
    f = ftp()
    try:
        orig = OUT / "video_original_ps3.mp4"
        if not orig.exists():
            with orig.open("wb") as fh:
                f.retrbinary(f"RETR {REMOTE}/{SONG}/video.mp4", fh.write)
            print(f"Original gesichert: {orig} ({orig.stat().st_size} B)")
        with (OUT / "video.mp4").open("rb") as fh:
            f.storbinary(f"STOR {REMOTE}/{SONG}/video.mp4", fh, blocksize=1 << 20)
        print("1080p-Testvideo hochgeladen")
        if xml:
            bak = OUT / "songs_4_0_original.xml"
            if not bak.exists():
                with bak.open("wb") as fh:
                    f.retrbinary(f"RETR {REMOTE}/songs_4_0.xml", fh.write)
            s = bak.read_bytes()  # bytes: keep line endings and encoding exactly
            m = re.search(rb'<SONG ID="%d".*?</SONG>' % SONG, s, re.S)
            song = re.sub(rb'(<VIDEO [^>]*)WIDTH="\d+" HEIGHT="\d+"', rb'\1WIDTH="1920" HEIGHT="1080"', m.group(0), 1)
            new = s[:m.start()] + song + s[m.end():]
            ET.fromstring(new)  # never upload a broken song list
            if new.count(b"<SONG ") != s.count(b"<SONG ") or b'WIDTH="1920" HEIGHT="1080"' not in song:
                sys.exit("Testdatei unplausibel - nichts hochgeladen")
            (OUT / "songs_4_0_test.xml").write_bytes(new)
            with (OUT / "songs_4_0_test.xml").open("rb") as fh:
                f.storbinary(f"STOR {REMOTE}/songs_4_0.xml", fh)
            print("songs_4_0.xml: VIDEO 1920x1080 gesetzt (Original gesichert)")
    finally:
        f.close()


def restore():
    f = ftp()
    try:
        with (OUT / "video_original_ps3.mp4").open("rb") as fh:
            f.storbinary(f"STOR {REMOTE}/{SONG}/video.mp4", fh, blocksize=1 << 20)
        print("Originalvideo zurückgespielt")
        bak = OUT / "songs_4_0_original.xml"
        if bak.exists():
            with bak.open("rb") as fh:
                f.storbinary(f"STOR {REMOTE}/songs_4_0.xml", fh)
            print("songs_4_0.xml zurückgespielt")
    finally:
        f.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prepare":
        prepare()
    elif cmd == "apply":
        apply("--xml" in sys.argv)
    elif cmd == "restore":
        restore()
    else:
        sys.exit(__doc__)
