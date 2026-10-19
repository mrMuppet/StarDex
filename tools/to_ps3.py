"""Build the PS3 version of a song (SingStar PS3 library format, FileSystem/Export/<id>/).

  python to_ps3.py ultrastar <song_dir> <out_dir> --ps4-id N
  python to_ps3.py ps2 <iso_dir> <song_id> <out_dir> [--lang EN]
  python to_ps3.py ps3disc <export_dir> <song_id> <out_dir>

out_dir gets: video.mp4 (H.264 <= 1280x720 + AAC; SingStar PS3 shows 1080p as black), preview.mp4 (368x208 MPEG-4
Part 2 "mp4v" ~700 kbit/s + AAC, like the official discs), melody_4.xml + melody.xml, cover.jpg (256x256) and
entry.json ({ps3_id, song: <SONG> block in the PS3 layout, artist, title, act_key}).

UltraStar/PS2 run the PS4 converters (us_to_ps4.py --max-height 720 / ps2_to_ps4.py) into a temporary pack and
convert it (pack_to_ps3); PS3 disc songs are copied as they are (only the cover is cut out of the texture page).
PS3 id: official ids stay, own songs 45xxx (PS4) <-> 60xxx (PS3), as in songid.ps4_id.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import songid  # noqa: E402

TOOLS = Path(__file__).parent
PS3_LOUDNESS = -10.0  # official PS3 songs measure -4.7 ... -22.6 LUFS, median around -9.5
PREVIEW_SECONDS = 30


def ps3_id(ps4: int) -> int:
    return 60000 + (ps4 - songid.CUSTOM_BASE) if ps4 >= songid.CUSTOM_BASE else ps4


def run(cmd: list) -> str:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout + p.stderr
    if p.returncode:
        raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else f"{cmd[1]} failed")
    return out


def probe(video: Path) -> dict:
    j = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=width,height,r_frame_rate,nb_read_packets:format=duration", "-of", "json", video]))
    st = j["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"w": int(st["width"]), "h": int(st["height"]), "fps": int(num) / int(den),
            "frames": int(st["nb_read_packets"]), "len": float(j["format"]["duration"])}


def ps3_media(v: dict) -> str:
    return (f'\n    <MELODY REVISION="1.0"/>\n    <MUSIC REVISION="1.0"/>'
            f'\n    <VIDEO FRAME_RATE="{v["fps"]:.6f}" FRAME_COUNT="{v["frames"]}" LENGTH="{v["len"]:.6f}" '
            f'WIDTH="{v["w"]}" HEIGHT="{v["h"]}" REVISION="1.0"/>\n    <PREV_VIDEO FOURCC="mp4v"/>\n  ')


def make_preview(video: Path, start: float, out: Path) -> None:
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, start):.3f}", "-i", video, "-t", str(PREVIEW_SECONDS),
         "-vf", "scale=trunc(iw*sar/2)*2:ih,setsar=1,scale=368:208:force_original_aspect_ratio=decrease,"
                "pad=368:208:(ow-iw)/2:(oh-ih)/2,setsar=1",
         "-c:v", "mpeg4", "-tag:v", "mp4v", "-b:v", "700k", "-maxrate", "1200k", "-bufsize", "1200k", "-r", "25",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", out])


def square_cover(src: Path, out: Path, box: tuple | None = None) -> None:
    from PIL import Image
    im = Image.open(src).convert("RGB")
    if box:
        im = im.crop(box)
    im.resize((256, 256), Image.LANCZOS).save(out, quality=92)


def ps3_melody(xml: str) -> str:
    """PS4 extras the PS3 does not know: <TEMPO> inside notes (tempo per track, PS4 polish)."""
    xml = re.sub(r"\s*<TEMPO\b[^>]*/>", "", xml)
    return re.sub(r"<NOTE\b([^>]*?)\s*>\s*</NOTE>", r"<NOTE\1 />", xml)


def finish(out: Path, pid: int, song: str, extra: dict) -> None:
    artist = re.search(r"<PERFORMANCE_NAME>(.*?)</PERFORMANCE_NAME>", song, re.S).group(1)
    key = re.search(r"<PERFORMANCE_NAME_KEY>(.*?)</PERFORMANCE_NAME_KEY>", song, re.S)
    title = re.search(r"<TITLE>(.*?)</TITLE>", song, re.S).group(1)
    (out / "entry.json").write_text(json.dumps({
        "ps3_id": pid, "song": song, "artist": artist, "title": title,
        "act_key": key.group(1) if key else re.sub(r"[^A-Z0-9 ]", "", artist.upper()), **extra},
        ensure_ascii=False, indent=1), "utf-8")
    print(f"-> {out} (PS3 {pid}: {artist} - {title})")


def pack_to_ps3(pack: Path, ps4: int, out: Path, source: str, ps4_media: bool = False, gain: float = 0.0) -> None:
    """Our PS4 pack folder (Prod_Sku_*) -> PS3 export entry.
    ps4_media: for the PS4 disc-song loader (ps4_discpack.py) - keep the id, the video (1080p), the H.264 preview
    and the PS4 melody; only the song block is put into the export layout.
    gain: dB added to the sound (PS4 packages are made for -12 LUFS, PS3 versions use PS3_LOUDNESS)."""
    pid = ps4 if ps4_media else ps3_id(ps4)
    out.mkdir(parents=True, exist_ok=True)
    sd = pack / str(ps4)
    song = re.search(r"<SONG .*?</SONG>", (pack / "songs_1_0.xml").read_text("utf-8"), re.S).group(0)
    pstart = float((re.search(r'PREVIEWSTART="([\d.]+)"', song) or re.search(r'CHORUS TIME="([\d.]+)"', song)).group(1))
    v = probe(sd / "video.mp4")
    audio = (["-af", f"volume={gain:.2f}dB", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if gain
             else ["-c:a", "copy"])
    if ps4_media:
        shutil.copy2(sd / "video.mp4", out / "video.mp4")
    elif v["h"] > 720 or v["w"] > 1280:  # SingStar PS3 shows > 720p as black
        run(["ffmpeg", "-v", "error", "-y", "-i", sd / "video.mp4", "-vf",
             "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2", "-c:v", "libx264",
             "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", *audio,
             "-movflags", "+faststart", out / "video.mp4"])
    elif gain:  # picture copied, only the sound re-encoded (seconds)
        run(["ffmpeg", "-v", "error", "-y", "-i", sd / "video.mp4", "-c:v", "copy", *audio,
             "-movflags", "+faststart", out / "video.mp4"])
    else:
        shutil.copy2(sd / "video.mp4", out / "video.mp4")
    v = probe(out / "video.mp4")
    mel = (sd / "melody_1.xml").read_text("utf-8")
    if not ps4_media:
        mel = ps3_melody(mel)
    for n in ("melody_4.xml", "melody.xml"):
        (out / n).write_text(mel, "utf-8", newline="\n")
    if ps4_media:
        shutil.copy2(sd / "preview.mp4", out / "preview.mp4")
    else:
        make_preview(out / "video.mp4", pstart, out / "preview.mp4")
    square_cover(next((pack / "textures").glob("*.jpg")), out / "cover.jpg")
    song = song.replace(f'<SONG ID="{ps4}"', f'<SONG ID="{pid}"', 1)
    song = re.sub(r'(<SOLO PLAYER1=")[^"]*"', r'\1Singer 1"', song)  # PS3 discs/Toolbox: "Singer 1"
    song = re.sub(r'PERFORMANCE_TYPE="([^"]*)"', lambda m: f'PERFORMANCE_TYPE="{m.group(1).replace("_", " ")}"', song)
    song = re.sub(r"<PERFORMED_BY\b.*?</PERFORMED_BY>",
                  '<PERFORMED_BY ID="ACTID">\n      <ACT ID="ACTID"/>\n    </PERFORMED_BY>', song, flags=re.S)
    song = re.sub(r"\s*<(MELODY|MUSIC|VIDEO|PREV_VIDEO)\b[^>]*/>", "", song)
    song = re.sub(r"\s*<(MUSIC|VIDEO)\b.*?</\1>", "", song, flags=re.S)
    song = re.sub(r"\s*</SONG>$", ps3_media(v) + "</SONG>", song)
    finish(out, pid, song, {"source": source, "video": f'{v["w"]}x{v["h"]}'})


def from_ultrastar(song_dir: Path, ps4: int, out: Path, loudness: float) -> None:
    tmp = out.parent / f"_tmp_{out.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        print(run([sys.executable, TOOLS / "us_to_ps4.py", song_dir, tmp, "--id", ps4, "--adrs", "auto",
                   "--max-height", "720", "--loudness", loudness]).strip())
        pack_to_ps3(next(tmp.glob("Prod_Sku_*")), ps4, out, "ultrastar")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def from_ps2(iso: Path, sid: int, out: Path, lang: str, loudness: float) -> None:
    tmp = out.parent / f"_tmp_{out.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        print(run([sys.executable, TOOLS / "ps2_to_ps4.py", iso, sid, tmp, "--lang", lang,
                   "--loudness", loudness]).strip())
        pack_to_ps3(next(tmp.glob("Prod_Sku_*")), sid, out, "ps2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def from_ps3disc(export: Path, sid: int, out: Path) -> None:
    """Disc songs are already in the PS3 format: copy media, newest melody, song block and cut out the cover."""
    out.mkdir(parents=True, exist_ok=True)
    sd = export / str(sid)
    for n in ("video.mp4", "preview.mp4"):
        shutil.copy2(sd / n, out / n)
    mel = max(sd.glob("melody*.xml"), key=lambda p: int((re.search(r"_(\d+)", p.name) or [0, 0])[1]))
    for n in ("melody_4.xml", "melody.xml"):
        shutil.copy2(mel, out / n)
    song = re.search(r'<SONG ID="%d".*?</SONG>' % sid, (export / "songs_4_0.xml").read_text("utf-8"), re.S).group(0)
    cov = re.search(r'<TPAGE_BIT NAME="cover_%d"[^>]*/>' % sid, (export / "covers.xml").read_text("utf-8"))
    if cov:
        a = dict(re.findall(r'(\w+)="([^"]*)"', cov.group(0)))
        u, vv, w, h = (int(float(a[k])) for k in ("U", "V", "WIDTH", "HEIGHT"))
        square_cover(export / "textures" / f"{a['TEXTURE']}.jpg", out / "cover.jpg", (u, vv, u + w, vv + h))
    m = re.search(r'<PERFORMED_BY ID="(\d+)"', song)
    finish(out, sid, song, {"source": "ps3disc", "act_id": int(m.group(1)) if m else None,
                            "video": "{WIDTH}x{HEIGHT}".format(**dict(re.findall(r'(WIDTH|HEIGHT)="(\d+)"', song)))})


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=("ultrastar", "ps2", "ps3disc", "ps4pack", "pkg"))
    ap.add_argument("args", nargs="+")
    ap.add_argument("--ps4-id", type=int)
    ap.add_argument("--lang", default="EN")
    ap.add_argument("--loudness", type=float, default=PS3_LOUDNESS)
    ap.add_argument("--pkg-loudness", type=float, default=-12.0, help="kind pkg: loudness the package was made for")
    ap.add_argument("--source", default="ps4pkg", help="kind pkg: source name stored in entry.json")
    a = ap.parse_args()
    if a.kind == "pkg":  # our finished PS4 package (.pkg): much faster than converting the source again
        pkg, sid, out = Path(a.args[0]), int(a.args[1]), Path(a.args[2])
        tmp = out.parent / f"_pkg_{out.name}"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            run(["dotnet", TOOLS / "PkgTool" / "PkgTool.Core.dll", "pkg_extract", pkg, tmp])
            pack_to_ps3(next(tmp.glob("uroot/Prod_Sku_*")), sid, out, a.source, gain=a.loudness - a.pkg_loudness)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif a.kind == "ultrastar":
        from_ultrastar(Path(a.args[0]), a.ps4_id, Path(a.args[1]), a.loudness)
    elif a.kind == "ps2":
        from_ps2(Path(a.args[0]), int(a.args[1]), Path(a.args[2]), a.lang, a.loudness)
    elif a.kind == "ps4pack":  # unpacked PS4 package (Prod_Sku_* folder) taken over from the PS4
        pack_to_ps3(Path(a.args[0]), int(a.args[1]), Path(a.args[2]), "ps4pkg")
    else:
        from_ps3disc(Path(a.args[0]), int(a.args[1]), Path(a.args[2]))


if __name__ == "__main__":
    main()
