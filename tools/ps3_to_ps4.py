"""Convert songs from a SingStar PS3 library (FileSystem/Export) into a SingStar PS4 DLC pack folder.

  python ps3_to_ps4.py EXPORT_DIR OUT_ROOT auto SONG_ID[=NEW_ID] [--name "Pack name"]
  python ps3_to_ps4.py EXPORT_DIR OUT_ROOT SKU SONG_ID[=NEW_ID] [...] [--no-chc] [--name "Pack name"]

Creates OUT_ROOT/Prod_Sku_<SKU>/ (config, songs, acts, covers, textures, <id>/melody_1.xml + media).
Feed OUT_ROOT to build_dlc.py afterwards.

The game only keeps a song if its id equals the pack label's base-36 digits (see songid.py).
SKU "auto": one song, NEW_ID defaults to songid.ps4_id() (custom 600xx -> 45xxx), SKU = 130 + base36(id).
An explicit SKU must match the song id; --unsafe skips that check (test packs only).

--no-chc omits melodies_1.chc and the MELODY_CACHE entry (PS3 libraries work without it;
the multi-song .chc layout is still unknown).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, str(Path(__file__).parent))
import chc  # noqa: E402
import songid  # noqa: E402

NS = ('xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xmlns="http://www.singstargame.com"')


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_packets:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    return {"w": s["width"], "h": s["height"], "fps": num / den,
            "frames": int(s["nb_read_packets"]), "len": float(j["format"]["duration"])}


def element(xml: str, tag: str, sid: str) -> str:
    m = re.search(r'<%s ID="%s".*?</%s>' % (tag, sid, tag), xml, re.S)
    if not m:
        raise KeyError(f"{tag} {sid} not found")
    return m.group(0)


def add_duet_parts(melody: str) -> str:
    """Give solo-only melodies a Solo 1 / Solo 2 split, like native PS4 songs.

    Duet/Battle modes build a sentence list per singer and crash (null deref near
    performance/adrsSupported) when the Solo 2 list is empty. Singer= is sticky until the
    next change; native songs switch singer on the sentence carrying a PTM marker.
    """
    if 'Singer="Solo 2"' in melody or melody.count("<TRACK") > 1:
        return melody
    parts = re.split(r"(<SENTENCE\b[^>]*>)", melody)  # [pre, tag, body, tag, body, ...]
    tags, bodies = parts[1::2], parts[2::2]
    ptm = [i for i, body in enumerate(bodies) if 'Type="PTM"' in body]
    starts = set(ptm) if len(ptm) >= 2 else set(range(4, len(tags), 4))
    starts.add(0)
    singer = 0
    for i, tag in enumerate(tags):
        tag = re.sub(r'\s+Singer="[^"]*"', "", tag)
        if i in starts:
            tag = tag.replace("<SENTENCE", f'<SENTENCE Singer="Solo {singer % 2 + 1}"', 1)
            singer += 1
        parts[1 + 2 * i] = tag
    return "".join(parts)


def melody_file(song_dir: Path) -> Path:
    """melody.xml, else the highest-versioned melody_N.xml."""
    if (song_dir / "melody.xml").exists():
        return song_dir / "melody.xml"
    return max(song_dir.glob("melody_*.xml"), key=lambda p: int(re.search(r"_(\d+)", p.name).group(1)))


def convert_song(song_xml: str, v: dict, preview_start: float) -> str:
    """Adapt a PS3 <SONG> element to the PS4 layout seen in Prod_Sku_130U9X."""
    s = re.sub(r'PERFORMANCE_TYPE="([^"]*)"', lambda m: 'PERFORMANCE_TYPE="%s"' % m.group(1).replace(" ", "_"),
               song_xml)
    s = re.sub(r"\s*<(MELODY|MUSIC|VIDEO|PREV_VIDEO)\b[^>]*/>", "", s)
    s = re.sub(r"\s*<(MUSIC|VIDEO)\b.*?</\1>", "", s, flags=re.S)
    attrs = (f'FRAME_COUNT="{v["frames"]}" WIDTH="{v["w"]}" HEIGHT="{v["h"]}" '
             f'FRAME_RATE="{v["fps"]:g}" LENGTH="{v["len"]:.2f}"')
    media = (
        '\n    <MUSIC REVISION="2.0">\n      <TRACK ID="0" NAME="Stereo" />\n    </MUSIC>'
        '\n    <MELODY REVISION="2.0" />'
        f'\n    <VIDEO REVISION="2.0" {attrs} PREVIEWSTART="{preview_start:.2f}">'
        f'\n      <TRACK ID="0" NAME="HD720VideoDL" {attrs} />\n    </VIDEO>'
        '\n    <PREV_VIDEO FOURCC="avc1" />\n  ')
    return re.sub(r"\s*</SONG>$", media + "</SONG>", s)


# ---------------------------------------------------------------- PS4 polish (28.09.): song end, tempo, rap, video

def _segments(melody: str) -> list[tuple[int, int]]:
    """(start, end) of each track's part: <TRACK>...</TRACK> containers (two-track duets), else the whole melody."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"<TRACK\b[^>]*[^/]>.*?</TRACK>", melody, re.S)
             if "<NOTE" in m.group(0)]  # PS2 duets declare empty <TRACK ...> </TRACK> and share the sentences
    return spans or [(0, len(melody))]


def read_melody(path: Path) -> str:
    """Melody text as UTF-8 XML: 41 PS3-library melodies (PS2 era) are ISO-8859-1."""
    raw = path.read_bytes()
    enc = re.search(rb'encoding="([^"]+)"', raw[:200])
    text = raw.decode(enc.group(1).decode() if enc else "utf-8", errors="replace")
    text = re.sub(r'encoding="[^"]+"', 'encoding="UTF-8"', text, count=1)
    # PS2-era header (<MELODY Tempo=.. Resolution=.. SongType=..>, ~20 songs): add what PS4 melodies carry
    if not re.search(r"<MELODY[^>]*xmlns=", text):
        text = text.replace("<MELODY", '<MELODY xmlns="http://www.singstargame.com" Version="1" FixedTempo="Yes"', 1)
    return text


def polish_melody(melody: str, song_len: float) -> tuple[str, list]:
    """Per track: a <TEMPO> child in the first note (official PS4 melodies always have it; ADRS timing uses the
    tempo map) and a final rest up to the end of the song (the game stops where the melody ends)."""
    head = re.search(r"<MELODY[^>]*>", melody).group()
    tempo = float(re.search(r'Tempo="([\d.]+)"', head).group(1))
    res = "Semiquaver" if 'Resolution="Semiquaver"' in head else "Demisemiquaver"
    tick = 60.0 / (tempo * (4 if res == "Semiquaver" else 8))
    log = []
    for a, b in reversed(_segments(melody)):
        seg = melody[a:b]
        changes = {float(t) for t in re.findall(r'<TEMPO Tempo="([\d.]+)"', seg)}
        if "<TEMPO" not in seg:
            tag = f'<TEMPO Tempo="{tempo:g}" Resolution="{res}" Offset="0" />'
            # first note: self-closing <NOTE .../> or open <NOTE ...> </NOTE> (PS2-era melodies)
            seg = re.sub(r"(<NOTE\b[^>]*?)(\s*/>|>)",
                         lambda m: f"{m.group(1)}>{tag}</NOTE>" if "/" in m.group(2) else f"{m.group(1)}>{tag}",
                         seg, count=1)
        if any(abs(c - tempo) > 0.01 for c in changes):
            log.append("tempo changes: song end left as is")
        else:
            total = sum(int(d) for d in re.findall(r'<NOTE\b[^>]*Duration="(\d+)"', seg)) * tick
            rest = round((song_len - total) / tick) + 1
            if rest > 1:
                i = seg.rindex("</SENTENCE>")
                seg = seg[:i] + f'  <NOTE MidiNote="0" Duration="{rest}" Lyric="" />\n    ' + seg[i:]
                log.append(f"song end +{rest * tick:.1f} s")
        melody = melody[:a] + seg + melody[b:]
    return melody, log


def add_rap_block(song: str, melody: str) -> str:
    """Rap notes need <GAMEPLAY>Rap</GAMEPLAY> and a <RAP> block, else the game gives no rap timing feedback."""
    if 'Rap="Yes"' not in melody or "<RAP>" in song:
        return song
    if "<GAMEPLAY>Rap</GAMEPLAY>" not in song:
        song = song.replace("</INFO>", "  <GAMEPLAY>Rap</GAMEPLAY>\n    </INFO>", 1)
    use = '<USE VERSION="Short">Yes</USE>\n        <USE VERSION="Normal">Yes</USE>'
    block = (f'\n    <RAP>\n      <PLAYER ID="1">\n        {use}\n      </PLAYER>\n'
             f'      <PLAYER ID="2">\n        {use}\n      </PLAYER>\n    </RAP>')
    return song.replace("</INFO>", "</INFO>" + block, 1)


def video_fix(src: Path, crf: int = 0) -> tuple[list, str]:
    """ffmpeg video options for the PS4 copy + description.
    720x576 (PAL rips, 58 songs): anamorphic 16:9 (Sony's own previews show the full 16:9 picture) -> SAR 64:45.
    720x404 with SAR 101:144/101:180/101:135 (Toolbox copies of PS2 discs): the picture is 4:3 with a
    letterbox band inside; the band is cropped and re-encoded with square pixels, else SAR 101:135 (4:3).
    crf > 0: re-encode everything (Toolbox exports use fixed 10/15 Mbit/s: 372 songs = 95 GB, too much for the
    PS4); PAL keeps 720x576 with SAR 64:45 in the stream (upscaling cost ~50 % more). crf 0: copy where possible, SAR by metadata."""
    from us_to_ps4 import detect_crop, ffprobe_json  # local: us_to_ps4 imports this module
    info = ffprobe_json(src)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    w, h, sar = int(v["width"]), int(v["height"]), v.get("sample_aspect_ratio", "")
    enc = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", str(crf or 18),
           "-preset", "slow"]
    if crf:
        if (w, h) == (720, 576):
            return ["-vf", "setsar=64/45", *enc], f"720x576 16:9 (SAR 64:45), crf {crf}"
        if not ((w, h) == (720, 404) and sar in ("101:144", "101:180", "101:135")):
            # even sizes for yuv420p (Celebration 25953 is 720x405)
            return ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1", *enc], f"re-encoded crf {crf}"
    if (w, h) == (720, 576):
        return ["-c:v", "copy", "-bsf:v", "h264_metadata=sample_aspect_ratio=64/45"], "SAR 64:45 (16:9)"
    if (w, h) == (720, 404) and sar in ("101:144", "101:180", "101:135"):
        length = float(info["format"]["duration"])
        boxes = [detect_crop(src, length * f) for f in (0.25, 0.5, 0.75)]
        boxes = [tuple(map(int, re.findall(r"\d+", b))) for b in boxes if b]
        if boxes and max(b[1] for b in boxes) < h - 40:
            cw, ch = max(b[0] for b in boxes), max(b[1] for b in boxes)
            cx, cy = min(b[2] for b in boxes), min(b[3] for b in boxes)
            aspect = cw * 101 / 135 / ch  # the band's true display aspect (full frame = 4:3)
            dw, dh = 720, round(720 / aspect / 2) * 2
            return (["-vf", f"crop={cw}:{ch}:{cx}:{cy},scale={dw}:{dh}:flags=lanczos,setsar=1", *enc],
                    f"band {cw}x{ch} cropped -> {dw}x{dh} ({aspect:.2f}:1)")
        if crf:
            return ["-vf", "scale=540:404:flags=lanczos,setsar=1", *enc], f"4:3 -> 540x404, crf {crf}"
        return ["-c:v", "copy", "-bsf:v", "h264_metadata=sample_aspect_ratio=101/135"], "SAR 101:135 (4:3)"
    return ["-c:v", "copy"], "copied"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path)
    ap.add_argument("out_root", type=Path)
    ap.add_argument("sku")
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--no-chc", action="store_true")
    ap.add_argument("--name", default="SingStar Custom")
    ap.add_argument("--title-suffix", default="", help='appended to every song title, e.g. " (Duet Fix)"')
    ap.add_argument("--unsafe", action="store_true", help="allow song ids that do not match the pack label")
    ap.add_argument("--loudness", type=float, default=-12.0, help="target loudness in LUFS (audio re-encoded)")
    ap.add_argument("--no-normalize", action="store_true", help="copy audio unchanged")
    ap.add_argument("--crf", type=int, default=18, help="re-encode video with this x264 CRF (0 = copy)")
    a = ap.parse_args()

    if a.sku == "auto":
        if len(a.ids) != 1:
            sys.exit("SKU auto needs exactly one song")
        sid, _, new_id = a.ids[0].partition("=")
        new_id = new_id or str(songid.ps4_id(int(sid)))
        a.ids = [f"{sid}={new_id}"]
        a.sku = songid.sku_for(int(new_id))
    if not a.unsafe:
        final_ids = [int(s.rpartition("=")[2]) for s in a.ids]
        if len(final_ids) != 1 or songid.id_from_label(a.sku) != final_ids[0]:
            sys.exit(f"pack {a.sku} would hold song id(s) {final_ids}, but the game expects exactly "
                     f"{songid.id_from_label(a.sku)} - use SKU auto (or --unsafe for test packs)")

    songs_all = (a.export / "songs_4_0.xml").read_text("utf-8")
    acts_all = (a.export / "acts_4_0.xml").read_text("utf-8")
    covers_all = (a.export / "covers.xml").read_text("utf-8")

    pack = f"Prod_Sku_{a.sku}"
    dst = a.out_root / pack
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "textures").mkdir(parents=True)

    songs, acts, covers, cache, melodies = [], {}, [], [], []
    for spec in a.ids:
        sid, _, new_id = spec.partition("=")  # "60009" or "60009=960009" (new in-game song id)
        new_id = new_id or sid
        src = a.export / sid
        song = element(songs_all, "SONG", sid).replace(f'<SONG ID="{sid}"', f'<SONG ID="{new_id}"', 1)
        if a.title_suffix:
            song = re.sub(r"<TITLE>(.*?)</TITLE>", lambda m: f"<TITLE>{m.group(1)}{a.title_suffix}</TITLE>", song, 1)
            song = re.sub(r"<TITLE_KEY>(.*?)</TITLE_KEY>",
                          lambda m: f"<TITLE_KEY>{m.group(1)}{re.sub(r'[^A-Z0-9 ]', '', a.title_suffix.upper())}</TITLE_KEY>",
                          song, 1)
        # One act per song, id = song id, name from PERFORMANCE_NAME (like us_to_ps4.py): the Toolbox export
        # lacks the acts of official songs (280 of 419) and reuses act ids for different artists
        # (e.g. 121 = Franz Ferdinand and Interpol), which would show wrong names on the PS4.
        pname = re.search(r"<PERFORMANCE_NAME>(.*?)</PERFORMANCE_NAME>", song, re.S).group(1)
        pkey = re.search(r"<PERFORMANCE_NAME_KEY>(.*?)</PERFORMANCE_NAME_KEY>", song, re.S)
        pkey = pkey.group(1) if pkey else re.sub(r"[^A-Z0-9 ]", "", pname.upper())
        song = re.sub(r"<PERFORMED_BY\b.*?</PERFORMED_BY>",
                      f'<PERFORMED_BY ID="{new_id}">\n      <ACT ID="{new_id}" />\n    </PERFORMED_BY>', song, 1,
                      flags=re.S)
        acts[new_id] = f'<ACT ID="{new_id}">\n    <NAME>{pname}</NAME>\n    <NAME_KEY>{pkey}</NAME_KEY>\n  </ACT>'
        cov = re.search(r'<TPAGE_BIT NAME="cover_%s"[^>]*/>' % sid, covers_all).group(0)
        tex = re.search(r'TEXTURE="([^"]+)"', cov).group(1)
        covers.append(cov.replace(f"cover_{sid}", f"cover_{new_id}"))
        shutil.copy2(a.export / "textures" / f"{tex}.jpg", dst / "textures" / f"{tex}.jpg")

        out = dst / new_id
        out.mkdir()
        from us_to_ps4 import detect_crop, loudness_filter  # local: us_to_ps4 imports this module
        vopts, vinfo = video_fix(src / "video.mp4", a.crf)
        aopts = ["-c:a", "copy"]
        if not a.no_normalize:
            afilter, measured = loudness_filter(src / "video.mp4", a.loudness)
            aopts = ["-af", afilter, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]
            print(f"  audio: {measured:.1f} LUFS -> {a.loudness:g} LUFS ({a.loudness - measured:+.1f} dB)")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src / "video.mp4"), "-map", "0:v:0", "-map", "0:a:0",
                        *vopts, *aopts, "-movflags", "+faststart", str(out / "video.mp4")], check=True)
        print(f"  video: {vinfo}")
        v = probe(out / "video.mp4")

        medley = re.search(r'<TYPE Start="([\d.]+)"[^>]*>Normal', song)
        chorus = re.search(r'<CHORUS TIME="([\d.]+)"', song)
        start = float(medley.group(1)) if medley else float(chorus.group(1)) if chorus else 0.0
        # preview from the finished video (PS3 previews are MPEG-4 Part 2 and share the Toolbox aspect errors):
        # 30 s, black borders dropped, content aspect kept, max 368x208, H.264 like us_to_ps4.py
        pstart = max(0.0, start - 0.5)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{pstart:.3f}", "-i", str(out / "video.mp4"), "-t", "30",
                        # square pixels first: scale works on stored pixels and would squash 720x576 SAR 64:45
                        "-vf", f"{detect_crop(out / 'video.mp4', pstart)}scale=trunc(iw*sar/2)*2:ih,setsar=1,"
                        "scale=368:208:force_original_aspect_ratio="
                        "decrease:force_divisible_by=16,setsar=1", "-c:v", "libx264", "-profile:v", "high",
                        "-level", "3.1", "-pix_fmt", "yuv420p", "-crf", "22", "-c:a", "aac", "-b:a", "128k",
                        "-ar", "48000", "-movflags", "+faststart", str(out / "preview.mp4")], check=True)
        shutil.copy2(out / "preview.mp4", out / "audiopreview.mp4")

        text, polish = polish_melody(add_duet_parts(read_melody(melody_file(src))), v["len"])
        if polish:
            print("  melody: " + ", ".join(polish))
        song = add_rap_block(song, text)
        melody = text.encode("utf-8")
        (out / "melody_1.xml").write_bytes(melody)
        melodies.append((int(new_id), melody))
        songs.append(convert_song(song, v, pstart))
        cache += [f"{new_id}/audiopreview.mp4", f"{new_id}/melody_1.xml", f"textures/{tex}.jpg"]
        print(f"  {sid} -> {new_id}: {re.search(r'<TITLE>(.*?)</TITLE>', song).group(1)}")

    write_pack_files(dst, pack, songs, list(acts.values()), covers, cache, melodies,
                     a.name, a.ids[0].rpartition("=")[2], use_chc=not a.no_chc)
    print(f"-> {dst} ({len(songs)} songs, chc={'no' if a.no_chc else 'yes'})")


def write_pack_files(dst: Path, pack: str, songs: list, acts: list, covers: list, cache: list,
                     melodies: list, name: str, product_code, use_chc: bool = True) -> None:
    """Write songs/acts/covers/config (+ melodies_1.chc) for a Prod_Sku folder whose media is in place."""
    hdr = '<?xml version="1.0" encoding="UTF-8"?>\n'
    (dst / "songs_1_0.xml").write_text(
        hdr + f"<SONG_SET {NS}>\n  " + "\n  ".join(songs) + "\n</SONG_SET>\n", "utf-8", newline="\n")
    (dst / "acts_1_0.xml").write_text(
        hdr + f"<ACT_SET {NS}>\n  " + "\n  ".join(acts) + "\n</ACT_SET>\n", "utf-8", newline="\n")
    (dst / "covers.xml").write_text(
        hdr + f"<TPAGE_BIT_SET {NS}>\n  " + "\n  ".join(covers) + "\n</TPAGE_BIT_SET>\n", "utf-8", newline="\n")

    melody_cache = ""
    if use_chc:
        if len(melodies) != 1:
            sys.exit("multi-song .chc layout unknown - use --no-chc for packs with more than one song")
        (dst / "melodies_1.chc").write_bytes(chc.pack(melodies[0][1], melodies[0][0]))
        melody_cache = f"    <MELODY_CACHE>\n      <FILE>{pack}/melodies_1.chc</FILE>\n    </MELODY_CACHE>\n"
        cache.insert(0, "melodies_1.chc")

    cache_files = ["acts_1_0.xml", "covers.xml", "songs_1_0.xml"] + cache
    config = (
        hdr + f"<CONFIG {NS}>\n"
        '  <VERSION version="1">\n'
        f'    <SONGS TIMESTAMP="{datetime.now():%Y-%m-%dT%H:%M:%S}">\n'
        "      <PACK_NAME />\n      <LAYER>0</LAYER>\n"
        f"      <SONG_LIST>{pack}/songs_1_0.xml</SONG_LIST>\n"
        f"      <ACT_LIST>{pack}/acts_1_0.xml</ACT_LIST>\n"
        f"      <PATH>{pack}/</PATH>\n    </SONGS>\n"
        f"{melody_cache}"
        f"    <COVERS>\n      <LIST>{pack}/covers.xml</LIST>\n      <PATH>{pack}/textures/</PATH>\n    </COVERS>\n"
        "    <CACHE>\n" + "".join(f"      <FILE>{f}</FILE>\n" for f in cache_files) + "    </CACHE>\n"
        "  </VERSION>\n"
        "  <CROSS_TITLE_PRODUCT_CODE>20003</CROSS_TITLE_PRODUCT_CODE>\n"
        f"  <PRODUCT_DESC>{xml_escape(name)}</PRODUCT_DESC>\n"
        "  <BRAND_NAME>SingStar</BRAND_NAME>\n"
        f"  <PRODUCT_NAME>{xml_escape(name)}</PRODUCT_NAME>\n"
        f"  <PRODUCT_CODE>{product_code}</PRODUCT_CODE>\n"
        "  <TERRITORY>Europe</TERRITORY>\n  <SKU>International</SKU>\n  <DEFAULT_LANG>EN</DEFAULT_LANG>\n"
        "</CONFIG>\n")
    (dst / "config.xml").write_text(config, "utf-8", newline="\n")


if __name__ == "__main__":
    main()
