"""Convert a song from a SingStar PS2 disc (extracted ISO) into a SingStar PS4 DLC pack folder.

  python ps2_to_ps4.py DISC_DIR SONG_ID OUT_ROOT [--lang DE] [--no-adrs]

DISC_DIR: the extracted ISO (contains PACK_EE.PAK + PAK_IOP*.PAK, or EE/export + IOP*/ for SingStar Germany).
Media: video movie.ipu -> M2V (tools/IPUenc, SingStar stores macroblocks column-major) -> H.264 1024x576
(640x336 = 16:9; 640x512 = 4:3 frame with a letterbox band, cropped). Audio music.mib (PS-ADPCM, 4 channels:
0/1 music, 2/3 lead vocals - silent on older discs, vocal then in the mix; header music.mih) -> stereo mix,
-12 LUFS. The vocal track (or a Demucs separation) feeds the per-segment ADRS decision (adrs_auto.StemShaper).
Melody: PS2 XML (ISO-8859-1, old header) normalised like ps3_to_ps4.py, duet split, tempo, song end, medley
markers. The PS2 song id is kept (label = 130 + base36(id)). Build the package with build_dlc.py afterwards.
"""
import argparse
import glob
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).parent))
import songid  # noqa: E402
from ps2pak import Pak  # noqa: E402
from ps3_to_ps4 import add_duet_parts, convert_song, polish_melody, probe, write_pack_files  # noqa: E402
from us_to_ps4 import add_adrs, key_text, loudness_filter  # noqa: E402

TOOLS = Path(__file__).parent
IPUENC = TOOLS / "IPUenc" / "IPUenc.exe"
import local_config  # noqa: E402
DEMUCS = local_config.path("demucs", Path("demucs"))  # demucs executable, default: on the PATH
PREVIEW_LEN = 30.0
ADRS_LOW, ADRS_HIGH = 312.5, 3125.0


def tx2_image(raw: bytes, w: int = 0):
    """PS2 texture page (.tx2, 132772 bytes): 256-byte header, w*h 8-bit indices in GS PSMT8 swizzle order,
    a 256-byte GS packet, then the 256-colour RGBA palette with the usual CSM1 block swap (entries 8-15 and
    16-23 of every 32 exchanged). Decoded 29.09. from SingStar Party page_0.tx2."""
    import numpy as np
    from PIL import Image
    w = w or (raw[0x0D] & 0x7F) * 256  # header byte 0x0d: width / 256 (2 = 512, 4 = 1024: SingStar Germany page_6)
    h = (len(raw) - 1700) // w
    n = w * h
    px = np.frombuffer(raw[256:256 + n], np.uint8)
    y, x = np.mgrid[0:h, 0:w]
    idx = px[(y & ~0xF) * w + (x & ~0xF) * 2 + ((((y & ~3) >> 1) + (y & 1)) & 7) * w * 2
             + ((x + (((y + 2) >> 2) & 1) * 4) & 7) * 4 + ((y >> 1) & 1) + ((x >> 2) & 2)]
    pal = np.frombuffer(raw[256 + n + 256:256 + n + 256 + 1024], np.uint8).reshape(-1, 4).copy()
    for base in range(0, 256, 32):
        pal[[*range(base + 8, base + 16), *range(base + 16, base + 24)]] = \
            pal[[*range(base + 16, base + 24), *range(base + 8, base + 16)]]
    return Image.fromarray(pal[:, :3][idx])


def version(name: str) -> int:
    """melody_10.xml > melody_9.xml > melody.xml (numeric, not alphabetical)."""
    m = re.search(r"_(\d+)\.\w+$", str(name))
    return int(m.group(1)) if m else 0


def xml_text(raw: bytes) -> str:
    """Song lists are UTF-8 on later discs and ISO-8859-1 on early ones (declared or not)."""
    enc = re.search(rb'encoding="([^"]+)"', raw[:200])
    try:
        return raw.decode(enc.group(1).decode() if enc else "utf-8")
    except (UnicodeDecodeError, LookupError):
        return raw.decode("latin-1")


class Disc:
    """Song files of one extracted PS2 disc, PAK archives or loose EE/IOP folders."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.ee = Pak(self.root / "PACK_EE.PAK") if (self.root / "PACK_EE.PAK").exists() else None
        self.iop = [Pak(p) for p in sorted(self.root.glob("PAK_IOP[0-9].PAK"))]

    def songs(self) -> dict:
        raws = ([self.ee.read(e) for e in self.ee.find(r"export.songs[^\\]*\.xml$")] if self.ee
                else [p.read_bytes() for p in self.root.glob("EE/export/songs*.xml")])
        texts = [xml_text(r) for r in raws]
        out = {}
        for t in texts:
            for m in re.finditer(r"<SONG\b([^>]*)>", t):
                a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
                if "ID" in a and "TITLE" in a:
                    out[int(a["ID"])] = a
        return out

    def ee_file(self, sid: int, pattern: str) -> bytes:
        if self.ee:
            hits = self.ee.find(rf"^export.{sid}.{pattern}$")
            if not hits:
                raise FileNotFoundError(f"export\\{sid}\\{pattern}")
            return self.ee.read(max(hits, key=lambda e: version(e["name"])))
        files = sorted(glob.glob(str(self.root / "EE" / "export" / str(sid) / "*")))
        files = [f for f in files if re.fullmatch(pattern, Path(f).name)]
        if not files:
            raise FileNotFoundError(f"EE/export/{sid}/{pattern}")
        return Path(max(files, key=version)).read_bytes()

    def _export_file(self, name: str) -> bytes | None:
        """export/<name> from PACK_EE or the loose EE/export folder."""
        if self.ee:
            hits = self.ee.find(r"^export." + re.escape(name).replace("/", ".") + "$")
            return self.ee.read(hits[0]) if hits else None
        p = self.root / "EE" / "export" / name
        return p.read_bytes() if p.exists() else None

    def cover(self, sid: int):
        """The song's cover as a PIL image: covers.xml names a region of a texture page (page_N.tga, or the
        PS2 texture page_N.tx2), e.g. 170x170 at U=170 V=0. None if the disc has none for this song."""
        from PIL import Image
        xml = self._export_file("covers.xml")
        m = xml and re.search(rf'<TPAGE_BIT NAME="cover_{sid}"([^>]*)>', xml.decode("latin-1"))
        if not m:
            return None
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        u, v, w, h = (int(a[k]) for k in ("U", "V", "WIDTH", "HEIGHT"))
        tga = self._export_file(f"textures/{a['TEXTURE']}.tga")
        if tga:
            page = Image.open(io.BytesIO(tga)).convert("RGB")
        else:
            tx2 = self._export_file(f"textures/{a['TEXTURE']}.tx2")
            if not tx2:
                return None
            page = tx2_image(tx2)
        return page.crop((u, v, u + w, v + h))

    def iop_copy(self, sid: int, name: str, dst: Path) -> None:
        """movie.ipu / music.mib (hundreds of MB) streamed to dst."""
        for pak in self.iop:
            hits = pak.find(rf"^{sid}.{re.escape(name)}$")
            if hits:
                e = hits[0]
                with open(pak.path, "rb") as f, open(dst, "wb") as o:
                    f.seek(e["offset"])
                    left = e["size"]
                    while left:
                        b = f.read(min(left, 1 << 24))
                        o.write(b)
                        left -= len(b)
                return
        loose = sorted(self.root.glob(f"IOP*/{sid}/{name}"))
        if not loose:
            raise FileNotFoundError(f"{sid}/{name}")
        shutil.copy2(loose[0], dst)


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def read_melody(raw: bytes) -> str:
    enc = re.search(rb'encoding="([^"]+)"', raw[:200])
    text = raw.decode(enc.group(1).decode() if enc else "latin-1", errors="replace")
    text = re.sub(r'encoding="[^"]+"', 'encoding="UTF-8"', text, count=1)
    if not re.search(r"<MELODY[^>]*xmlns=", text):
        text = text.replace("<MELODY", '<MELODY xmlns="http://www.singstargame.com" FixedTempo="Yes"', 1)

    # Later discs (e.g. Boy Bands vs Girl Bands) write attributes alphabetically (Duration before MidiNote);
    # the melody tools expect <NOTE MidiNote=.. Duration=.. Lyric=.. ...> like Sony's PS3/PS4 melodies.
    def note(m):
        attrs = re.findall(r'(\w+)="([^"]*)"', m.group(1))
        first = {k: v for k, v in attrs if k in ("MidiNote", "Duration", "Lyric")}
        rest = "".join(f' {k}="{v}"' for k, v in attrs if k not in first)
        head = "".join(f' {k}="{first[k]}"' for k in ("MidiNote", "Duration", "Lyric") if k in first)
        return f"<NOTE{head}{rest}{m.group(2)}>"
    return re.sub(r"<NOTE\b([^>]*?)\s*(/?)>", note, text)


def sentence_times(melody: str) -> list[tuple[float, float, int]]:
    """(start, end, index) of every sentence that has sung notes (first track), seconds."""
    head = re.search(r"<MELODY[^>]*>", melody).group()
    tick = 60.0 / (float(re.search(r'Tempo="([\d.]+)"', head).group(1)) * 8)
    pos, out = 0, []
    for i, m in enumerate(re.finditer(r"<SENTENCE\b[^>]*>(.*?)</SENTENCE>", melody, re.S)):
        first = last = None
        for n in re.finditer(r'<NOTE\b[^>]*MidiNote="(\d+)"[^>]*Duration="(\d+)"', m.group(1)):
            if int(n.group(1)) > 0:
                first = pos if first is None else first
                last = pos + int(n.group(2))
            pos += int(n.group(2))
        if first is not None:
            out.append((first * tick, last * tick, i))
    return out


def add_medley_markers(melody: str, marks: dict) -> str:
    """marks: sentence index -> list of MARKER_N xml, placed as children of the sentence's first/last note."""
    parts = re.split(r"(<SENTENCE\b[^>]*>.*?</SENTENCE>)", melody, flags=re.S)
    idx = 0
    for k, p in enumerate(parts):
        if not p.startswith("<SENTENCE"):
            continue
        for kind, xml in marks.get(idx, []):
            notes = list(re.finditer(r"<NOTE\b[^>]*?(/>|>)", p))
            n = notes[0] if kind == "begin" else notes[-1]
            s = n.group(0)
            new = s[:-2].rstrip() + f">{xml}</NOTE>" if s.endswith("/>") else s + xml
            p = p[:n.start()] + new + p[n.end():]
        parts[k] = p
        idx += 1
    return "".join(parts)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("disc", type=Path)
    ap.add_argument("song_id", type=int)
    ap.add_argument("out_root", type=Path)
    ap.add_argument("--lang", default="EN")
    ap.add_argument("--no-adrs", action="store_true")
    ap.add_argument("--loudness", type=float, default=-12.0)
    a = ap.parse_args()
    # Song-Manager setting "Gesangstrennung": full (default) / nodemucs = ADRS only from the disc's own vocal track /
    # off = no ADRS at all
    if os.environ.get("SINGSTAR_ADRS", "full") == "off":
        a.no_adrs = True

    disc = Disc(a.disc)
    meta = disc.songs().get(a.song_id)
    if not meta:
        sys.exit(f"song {a.song_id} not in the disc's song list")
    sid = a.song_id
    title, artist = meta["TITLE"], meta.get("PERFORMANCE_NAME", "?")
    ptype = meta.get("PERFORMANCE_TYPE", "MALE SOLO").replace(" ", "_")
    sku = songid.sku_for(sid)
    pack = f"Prod_Sku_{sku}"
    dst = a.out_root / pack
    if a.out_root.exists():
        shutil.rmtree(a.out_root)
    (dst / str(sid)).mkdir(parents=True)
    (dst / "textures").mkdir()
    out = dst / str(sid)
    print(f"{artist} - {title}: id {sid}, label {songid.label_for(sid)}")

    with tempfile.TemporaryDirectory(dir=a.out_root) as tmpd:
        tmp = Path(tmpd)
        # ---- audio: MIB + MIH -> ADS container (ffmpeg decodes PS-ADPCM), split music / vocals
        mih = disc.ee_file(sid, r"music\.mih")
        _hs, _unk, ch, rate, inter, _blocks = struct.unpack_from("<6I", mih)
        disc.iop_copy(sid, "music.mib", tmp / "music.mib")
        size = (tmp / "music.mib").stat().st_size
        with open(tmp / "music.ads", "wb") as o, open(tmp / "music.mib", "rb") as i:
            o.write(b"SShd" + struct.pack("<7I", 0x18, 0x10, rate, ch, inter, 0xFFFFFFFF, 0xFFFFFFFF)
                    + b"SSbd" + struct.pack("<I", size))
            shutil.copyfileobj(i, o, 1 << 24)
        (tmp / "music.mib").unlink()
        stems = tmp / "stems"
        stems.mkdir()
        ff("-i", str(tmp / "music.ads"), "-filter_complex",
           "[0:a]pan=stereo|c0=c0|c1=c1[m];[0:a]pan=stereo|c0=c2|c1=c3[v];[0:a]pan=stereo|c0=c0+c2|c1=c1+c3[x]",
           "-map", "[m]", str(stems / "no_vocals.wav"), "-map", "[v]", str(stems / "vocals.wav"),
           "-map", "[x]", str(tmp / "mix.wav"))
        afilter, measured = loudness_filter(tmp / "mix.wav", a.loudness)
        print(f"  audio: {ch} ch, {measured:.1f} LUFS -> {a.loudness:g} LUFS ({a.loudness - measured:+.1f} dB)")

        # ---- video: IPU -> M2V (IPUenc) -> H.264 16:9
        disc.iop_copy(sid, "movie.ipu", tmp / "movie.ipu")
        subprocess.run([str(IPUENC), "-decode", str(tmp / "movie.ipu"), str(tmp / "movie.m2v")],
                       check=True, capture_output=True)
        (tmp / "movie.ipu").unlink()
        w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                        "stream=width,height", "-of", "csv=p=0", str(tmp / "movie.m2v")],
                                       capture_output=True, text=True).stdout.strip().split(",")[:2])
        if h >= 480:  # 4:3 frame with the 16:9-ish picture as a band (SingStar Germany): crop it
            cd = subprocess.run(["ffmpeg", "-r", "25", "-i", str(tmp / "movie.m2v"), "-vf",
                                 "select='not(mod(n,250))',cropdetect=24:2:0", "-f", "null", "-"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
            boxes = [tuple(map(int, b)) for b in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", cd)]
            bh = max(b[1] for b in boxes) if boxes else h
            by = min(b[3] for b in boxes) if boxes else 0
            vf = f"crop={w}:{bh}:0:{by},"
            aspect = (4 / 3) * h / bh
        else:
            vf, aspect = "", 16 / 9
        vh = 576
        vw = round(vh * aspect / 2) * 2
        ff("-r", "25", "-i", str(tmp / "movie.m2v"), "-i", str(tmp / "mix.wav"), "-map", "0:v:0", "-map", "1:a:0",
           "-vf", f"{vf}scale={vw}:{vh}:flags=lanczos,setsar=1", "-c:v", "libx264", "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", "-r", "25",
           "-af", afilter, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
           "-shortest", "-movflags", "+faststart", str(out / "video.mp4"))
        v = probe(out / "video.mp4")
        print(f"  video: {w}x{h} -> {v['w']}x{v['h']} ({aspect:.2f}:1), {v['len']:.1f} s")

        # ---- melody
        text = read_melody(disc.ee_file(sid, r"melody[_\d]*\.xml"))
        text = add_duet_parts(text)
        text, polish = polish_melody(text, v["len"])
        if polish:
            print("  melody: " + ", ".join(polish))
        sents = sentence_times(text)
        marker = re.search(r'MARKER_N Type="MedleyNormalBegin"', text)
        p0 = v["len"] / 3
        b = min(range(len(sents)), key=lambda i: abs(sents[i][0] - p0))
        ne = max((i for i in range(b, len(sents)) if sents[i][1] - sents[b][0] <= PREVIEW_LEN), default=b)
        me = max((i for i in range(b, len(sents)) if sents[i][1] - sents[b][0] <= 12), default=b)
        if not marker:
            marks = {}  # the same sentence may carry several markers (e.g. both medleys end there)
            for i, kind, xml in ((b, "begin", '<MARKER_N Type="MedleyNormalBegin" Delay="10" />'),
                                 (b, "begin", '<MARKER_N Type="MedleyMicroBegin" Delay="5" />'),
                                 (ne, "end", '<MARKER_N Type="MedleyNormalEnd" Delay="10" />'),
                                 (me, "end", '<MARKER_N Type="MedleyMicroEnd" Delay="5" />')):
                marks.setdefault(sents[i][2], []).append((kind, xml))
            text = add_medley_markers(text, marks)
        if not a.no_adrs:
            import adrs_auto
            import numpy as np
            vocal = adrs_auto.ab.load(stems / "vocals.wav")
            silent = float(np.sqrt((vocal ** 2).mean())) < 1e-4
            if silent and os.environ.get("SINGSTAR_ADRS", "full") == "nodemucs":
                print("  vocal track silent on this disc, Gesangstrennung abgeschaltet: ADRS: aus")
                a.no_adrs = True
        if not a.no_adrs:
            if silent:
                # older discs (e.g. SingStar Party 2004) leave channels 2/3 silent: the vocal is in the mix
                subprocess.run([str(DEMUCS), "--two-stems=vocals", "-n", "htdemucs", "-o", str(tmp / "demucs"),
                                str(tmp / "mix.wav")], check=True, capture_output=True)
                stems = tmp / "demucs" / "htdemucs" / "mix"
                print("  vocal track silent on this disc: Demucs separation used for ADRS")
            shaper = adrs_auto.StemShaper(stems, ADRS_LOW, ADRS_HIGH)
            text, ev = add_adrs(text, ADRS_LOW, ADRS_HIGH, 0, shape=shaper)
            on = [s for s in shaper.log if not s["off"]]
            if not on:  # nothing reduced: leave the song without ADRS, like Sony does for unsuitable mixes
                text = re.sub(r"<ADRS [^>]*/>", "", text)
            elif 'shouldHaveAdrs=' not in text[:600]:
                text = text.replace("<MELODY", '<MELODY shouldHaveAdrs="Yes"', 1)
            print(f"  ADRS: {len(on)}/{len(shaper.log)} segments reduced")
        melody = text.encode("utf-8")
        (out / "melody_1.xml").write_bytes(melody)

    # ---- preview (30 s from the medley start; 16:9 video -> 368x208, multiples of 16)
    start = sents[b][0]
    pstart = max(0.0, start - 0.5)
    ff("-ss", f"{pstart:.3f}", "-i", str(out / "video.mp4"), "-t", f"{PREVIEW_LEN:.0f}",
       "-vf", "scale=368:208:force_original_aspect_ratio=decrease:force_divisible_by=16,setsar=1",
       "-c:v", "libx264", "-profile:v", "high", "-level", "3.1", "-pix_fmt", "yuv420p", "-crf", "22",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(out / "preview.mp4"))
    shutil.copy2(out / "preview.mp4", out / "audiopreview.mp4")

    # ---- cover: the disc's own cover (covers.xml + texture page), else a frame from the chorus
    tex = f"page_{sid}"
    (a.out_root / "sce_sys").mkdir(parents=True, exist_ok=True)
    cover = disc.cover(sid)
    if cover is not None:
        from PIL import Image
        cover.resize((256, 256), Image.LANCZOS).save(dst / "textures" / f"{tex}.jpg", quality=92)
        cover.resize((512, 512), Image.LANCZOS).save(a.out_root / "sce_sys" / "icon0.png")
        print(f"  cover: from the disc ({cover.width}x{cover.height})")
    else:
        grab = ["-ss", f"{start + 8:.2f}", "-i", str(out / "video.mp4"), "-frames:v", "1"]
        ff(*grab, "-vf", "scale=256:256:force_original_aspect_ratio=increase,crop=256:256", "-q:v", "2",
           str(dst / "textures" / f"{tex}.jpg"))
        ff(*grab, "-vf", "scale=512:512:force_original_aspect_ratio=increase,crop=512:512", "-pix_fmt", "rgb24",
           str(a.out_root / "sce_sys" / "icon0.png"))
        print("  cover: no disc cover, video frame used")

    # ---- songs / acts / covers / config
    head = re.search(r"<MELODY[^>]*>", text).group()
    genre = (re.search(r'Genre="([^"]*)"', head) or [None, "Pop"])[1] or "Pop"
    year = (re.search(r'Year="(\d{4})', head) or [None, "2000"])[1]
    tempo = float(re.search(r'Tempo="([\d.]+)"', head).group(1))
    song = (f'<SONG ID="{sid}" PERFORMANCE_TYPE="{ptype}">\n'
            f"    <TITLE>{escape(title)}</TITLE>\n    <TITLE_KEY>{key_text(title)}</TITLE_KEY>\n"
            f"    <ALBUM />\n    <SHORT_VER>false</SHORT_VER>\n"
            f'    <SOLO PLAYER1={quoteattr(artist)} SHORT_VER="0" />\n'
            f'    <TEMPO BPM="{tempo:g}" RESOLUTION="Demisemiquaver" />\n'
            f'    <CHORUS TIME="{start:.3f}" />\n'
            f"    <INFO>\n      <GENRE>{escape(genre)}</GENRE>\n      <GAMEPLAY>Singing</GAMEPLAY>\n"
            f"      <RELEASE_DATE>{year}-01-01</RELEASE_DATE>\n      <VOXLANGUAGE>{a.lang}</VOXLANGUAGE>\n"
            f"    </INFO>\n"
            f'    <MEDLEYS>\n      <TYPE Start="{start:.3f}" End="{sents[ne][1]:.3f}">Normal</TYPE>\n'
            f'      <TYPE Start="{start:.3f}" End="{sents[me][1]:.3f}">Micro</TYPE>\n    </MEDLEYS>\n'
            f'    <PERFORMED_BY ID="{sid}">\n      <ACT ID="{sid}" />\n    </PERFORMED_BY>\n'
            f"    <PERFORMANCE_NAME>{escape(artist)}</PERFORMANCE_NAME>\n"
            f"    <PERFORMANCE_NAME_KEY>{key_text(artist)}</PERFORMANCE_NAME_KEY>\n  </SONG>")
    song = convert_song(song, v, pstart)
    act = f'<ACT ID="{sid}">\n    <NAME>{escape(artist)}</NAME>\n    <NAME_KEY>{key_text(artist)}</NAME_KEY>\n  </ACT>'
    cov = f'<TPAGE_BIT NAME="cover_{sid}" TEXTURE="{tex}" U="0" V="0" WIDTH="256" HEIGHT="256" />'
    cache = [f"{sid}/audiopreview.mp4", f"{sid}/melody_1.xml", f"textures/{tex}.jpg"]
    write_pack_files(dst, pack, [song], [act], [cov], cache, [(sid, melody)], f"{artist} - {title}", sid)
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
