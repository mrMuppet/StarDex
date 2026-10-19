"""Build Pack0.psarc for SingStar PS4's disc-song loader (see docs/TECHNIK.md).

  python ps4_discpack.py OUT.psarc SONGDIR [SONGDIR ...] [--crf 26]   (--crf: smaller videos)
      SONGDIR = a PS3 version folder from to_ps3.py (video.mp4, preview.mp4, melody_4.xml, melody.xml,
                cover.jpg, entry.json) or one of our PS4 packages (.pkg)
  python ps4_discpack.py --patch OUT.xml   write the GoldHEN patch (CUSA00033 v01.10)

The game looks for <prefix>Pack0.psarc, Pack1.psarc … (prefix /app0/ in the retail eboot, function 0x7d8310) and loads
FileSystem/Export/ from them (paths inside the archive: filesystem/export/...). The patch points the prefix to
/download0/ : lea rsi at 0x7d8166 -> the string "/download0/" that is already in the eboot. Only /download0/ loads
(a pointer to /data/singstar/ was tested 02.10. and does not). download0 is a fixed 1 GiB image, so Pack0.psarc there
is a symlink to /av_contents/video/ss/Pack0.psarc (FTP: /user/av_contents/video/ss/), made by tools/payload/dl0link.elf.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import psarc  # noqa: E402

NS = ('xmlns="http://www.singstargame.com" xmlns:ss="http://www.singstargame.com" '
      'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')
HDR = '<?xml version="1.0" encoding="UTF-8"?>\n'

CONFIG = HDR + f"""<CONFIG {NS}>
  <VERSION version="4">
    <SONGS TIMESTAMP="2026-10-01T00:00:00Z">
      <LAYER>0</LAYER>
      <SONG_LIST>FileSystem/Export/songs_4_0.xml</SONG_LIST>
      <ACT_LIST>FileSystem/Export/acts_4_0.xml</ACT_LIST>
      <PATH>FileSystem/Export/</PATH>
    </SONGS>
    <SONG_LISTS TIMESTAMP="2026-10-01T00:00:00Z">
      <FILE>FileSystem/Export/songlists_4.xml</FILE>
    </SONG_LISTS>
    <COVERS>
      <LIST>FileSystem/Export/covers.xml</LIST>
      <PATH>FileSystem/Export/textures/</PATH>
    </COVERS>
    <GAME_CREDITS>
      <FILE>FileSystem/Export/credits.xml</FILE>
    </GAME_CREDITS>
    <FILTERS>
      <FILE>FileSystem/Export/filters.xml</FILE>
    </FILTERS>
    <RATINGS/>
  </VERSION>
  <CROSS_TITLE_PRODUCT_CODE>00011</CROSS_TITLE_PRODUCT_CODE>
  <PRODUCT_DESC>SingStar Custom</PRODUCT_DESC>
  <BRAND_NAME>SingStar</BRAND_NAME>
  <PRODUCT_NAME>SingStar Custom</PRODUCT_NAME>
  <PRODUCT_CODE>00617</PRODUCT_CODE>
  <TERRITORY>Europe</TERRITORY>
  <SKU>International</SKU>
  <DEFAULT_LANG>EN</DEFAULT_LANG>
</CONFIG>
"""

# filters (genre / language codes the game knows, as on the PS3 discs) and our own credits text
GENRES = ["Pop", "Rock", "RnB", "IndieAlt", "Duet", "Rap", "Soundtrack"]
LANGS = ["PL", "EN", "FR", "DE", "ES", "IT", "NO", "SV", "FI", "DA", "NL", "PT"]


def _filter(name: str, kind: str, weight: int) -> str:
    code = f"{kind}_{name.upper()}"
    return (f'  <FILTER name="{name}" stringId="ID_{code}" filterType="{kind}" phonemeId="DVCID_FILTER_{code}" '
            f'weight="{weight}"/>\n')


FILTERS = (HDR + f"<FILTER_SET {NS}>\n" + "".join(_filter(g, "GENRE", i) for i, g in enumerate(GENRES))
           + _filter("Other", "GENRE", 100) + "".join(_filter(c, "LANGUAGE", i - 26) for i, c in enumerate(LANGS))
           + _filter("RU", "LANGUAGE", 0) + _filter("??", "LANGUAGE", 255) + "</FILTER_SET>\n")
CREDITS = HDR + f'<GAME_CREDITS {NS}>\n  <CREDITS LANG="EN">SingStar Custom Disc Pack</CREDITS>\n</GAME_CREDITS>\n'

PATCH_NAME = "Disc songs from /download0/Pack0.psarc"
PATCH_LEA = (0x7D8166, bytes.fromhex("488d35f4192400"))  # was 48 8d 35 63 69 29 00 -> "/app0/", now "/download0/"


PKGTOOL = Path(__file__).parent / "PkgTool" / "PkgTool.Core.dll"


def from_pkg(pkg: Path, work: Path) -> Path:
    """Our PS4 package (EP9000-CUSA00033_00-<LABEL>.pkg) -> song folder like to_ps3.py, with the PS4 media."""
    import to_ps3
    label = pkg.stem.split("-")[-1]
    sid = int(label[3:6], 36)
    out = work / str(sid)
    if (out / "entry.json").exists() and (out / "entry.json").stat().st_mtime >= pkg.stat().st_mtime:
        return out  # unchanged package: reuse (a rebuilt package is unpacked again)
    shutil.rmtree(out, ignore_errors=True)
    ext = work / f"_pkg_{label}"
    shutil.rmtree(ext, ignore_errors=True)
    subprocess.run(["dotnet", str(PKGTOOL), "pkg_extract", str(pkg), str(ext)], check=True, capture_output=True)
    try:
        to_ps3.pack_to_ps3(next(ext.glob("uroot/Prod_Sku_*")), sid, out, "ps4pkg", ps4_media=True)
    finally:
        shutil.rmtree(ext, ignore_errors=True)
    return out


def ps4_preview(src: Path, dst: Path) -> None:
    """PS3 previews are MPEG-4 Part 2 (mp4v): the PS4 preview player plays the sound but shows black.
    Re-encode to H.264 368x208 like the PS4 packages (sizes multiple of 16, the player ignores frame cropping)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:v", "libx264", "-profile:v", "high",
                    "-level", "3.1", "-pix_fmt", "yuv420p", "-crf", "22", "-vf", "setsar=1",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(dst)], check=True)


def small_video(src: Path, dst: Path, crf: int) -> None:
    """download0 is a fixed 1 GiB image (DOWNLOAD_DATA_SIZE 1024) - re-encode the picture smaller, sound copied."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:v", "libx264", "-profile:v", "high",
                    "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "slow", "-c:a", "copy",
                    "-movflags", "+faststart", str(dst)], check=True)


def build(out: Path, song_dirs: list[Path], prefix: str = "filesystem/export/", video_crf: int | None = None,
          **psarc_opts) -> None:
    """video_crf: re-encode the videos (e.g. 26) to fit more songs into download0.
    prefix: paths inside the archive. Tested 02.10.: /download0/Pack0.psarc with filesystem/export/... loads;
    /data/singstar/ does not load (tested with the same pack) - only /download0/ works."""
    tmp = Path(tempfile.mkdtemp(prefix="discpack_", dir=str(out.parent)))
    try:
        exp = tmp / "export"
        (exp / "textures").mkdir(parents=True)
        songs, acts, covers, refs = [], {}, [], []
        files = []
        for d in song_dirs:
            e = json.loads((d / "entry.json").read_text("utf-8"))
            pid = e["ps3_id"]
            aid = e.get("act_id") or pid
            block = e["song"].replace('PERFORMED_BY ID="ACTID"', f'PERFORMED_BY ID="{aid}"') \
                             .replace('<ACT ID="ACTID"/>', f'<ACT ID="{aid}"/>')
            block = block.replace('<PREV_VIDEO FOURCC="mp4v"/>', '<PREV_VIDEO FOURCC="avc1"/>')
            songs.append("  " + block)
            (tmp / str(pid)).mkdir(exist_ok=True)
            prev = tmp / str(pid) / "preview.mp4"
            codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=codec_name", "-of", "csv=p=0", str(d / "preview.mp4")],
                                   capture_output=True, text=True).stdout.strip()
            if codec == "h264":
                shutil.copy2(d / "preview.mp4", prev)
            else:
                ps4_preview(d / "preview.mp4", prev)
            acts[aid] = (f'  <ACT ID="{aid}">\n    <NAME>{e["artist"]}</NAME>\n    <NAME_KEY>{e["act_key"]}</NAME_KEY>\n'
                         f'  </ACT>')
            covers.append(f'  <TPAGE_BIT NAME="cover_{pid}" TEXTURE="page_{pid}" U="0" V="0" WIDTH="256" HEIGHT="256"/>')
            refs.append(f'      <SONG_REF ID="{pid}"></SONG_REF>')
            video = d / "video.mp4"
            if video_crf is not None:  # kept next to the song (re-encoding takes ~1 min per song)
                video = d / f"video_crf{video_crf}.mp4"
                if not video.exists() or video.stat().st_mtime < (d / "video.mp4").stat().st_mtime:
                    small_video(d / "video.mp4", video.with_suffix(".tmp.mp4"), video_crf)
                    video.with_suffix(".tmp.mp4").replace(video)
            for n in ("melody_4.xml", "melody.xml", "preview.mp4", "video.mp4"):
                files.append((f"{pid}/{n}", {"preview.mp4": prev, "video.mp4": video}.get(n, d / n)))
            files.append((f"textures/page_{pid}.jpg", d / "cover.jpg"))
        (exp / "config.xml").write_text(CONFIG, "utf-8", newline="\n")
        (exp / "songs_4_0.xml").write_text(HDR + f"<SONG_SET {NS}>\n" + "\n".join(songs) + "\n</SONG_SET>\n",
                                           "utf-8", newline="\n")
        (exp / "acts_4_0.xml").write_text(HDR + f"<ACT_SET {NS}>\n" + "\n".join(acts.values()) + "\n</ACT_SET>\n",
                                          "utf-8", newline="\n")
        (exp / "covers.xml").write_text(HDR + f"<TPAGE_BIT_SET {NS}>\n" + "\n".join(covers) + "\n</TPAGE_BIT_SET>\n",
                                        "utf-8", newline="\n")
        (exp / "songlists_4.xml").write_text(
            HDR + f'<SUBSETS {NS}>\n  <GROUP Name="Root">\n    <SUBSET Name="Carousel">\n'
            '      <Name_Legacy>Carousel</Name_Legacy>\n' + "\n".join(refs) + "\n    </SUBSET>\n  </GROUP>\n</SUBSETS>\n",
            "utf-8", newline="\n")
        (exp / "filters.xml").write_text(FILTERS, "utf-8", newline="\n")
        (exp / "credits.xml").write_text(CREDITS, "utf-8", newline="\n")
        meta = [(n, exp / n) for n in
                ("config.xml", "songs_4_0.xml", "acts_4_0.xml", "covers.xml", "songlists_4.xml", "filters.xml",
                 "credits.xml")]
        psarc.create(str(out), [(prefix + n, f) for n, f in meta + files], **psarc_opts)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def patch_xml() -> str:
    lines = "\n".join(f'            <Line Type="bytes" Address="0x{a:08x}" Value="{v.hex()}"/>'
                      for a, v in (PATCH_LEA,))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Patch>
    <TitleID>
        <ID>CUSA00033</ID>
    </TitleID>
    <Metadata Title="SingStar"
              Name="{PATCH_NAME}"
              Note="Loads extra songs from download0/Pack0.psarc (disc song loader instead of /app0/)"
              Author="PS4Singstar"
              PatchVer="1.0"
              AppVer="01.10"
              AppElf="eboot.bin">
        <PatchList>
{lines}
        </PatchList>
    </Metadata>
</Patch>
"""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) >= 3 and sys.argv[1] == "--patch":
        Path(sys.argv[2]).write_text(patch_xml(), "utf-8")
        print(sys.argv[2])
    elif len(sys.argv) >= 3:
        out = Path(sys.argv[1])
        crf = None
        if "--crf" in sys.argv:
            i = sys.argv.index("--crf")
            crf = int(sys.argv[i + 1])
            del sys.argv[i:i + 2]
        work = out.parent / "_songs"
        work.mkdir(parents=True, exist_ok=True)
        build(out, [from_pkg(Path(p), work) if p.endswith(".pkg") else Path(p) for p in sys.argv[2:]], video_crf=crf)
        print(sys.argv[1], f"{Path(sys.argv[1]).stat().st_size / 2**20:.1f} MB")
    else:
        sys.exit(__doc__)
