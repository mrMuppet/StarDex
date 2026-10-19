"""Build a SingStar PS4 DLC pack folder from an existing pack, with a new SKU / song id.

The result is the root of an addcont package (Prod_Sku_<SKU>/...), ready for a GP4 project.
Only the IDs and visible titles change, so a hit in-game is unmistakable.

Usage:
  python make_testpack.py SRC_PACK_DIR OUT_ROOT SKU SONG_ID "TITLE" "ARTIST"
  e.g. python make_testpack.py .../addcont0/Prod_Sku_130U9X build/dlc_root CSTM01 900001 "PS4 CUSTOM TEST" "Claude Test"
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/
import chc  # noqa: E402


def sub_all(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def main(src: Path, out_root: Path, sku: str, song_id: int, title: str, artist: str) -> None:
    old_sku = src.name.removeprefix("Prod_Sku_")
    old_id = re.search(r'<SONG ID="(\d+)"', (src / "songs_1_0.xml").read_text("utf-8")).group(1)
    old_act = re.search(r'<ACT ID="(\d+)"', (src / "acts_1_0.xml").read_text("utf-8")).group(1)
    dst = out_root / f"Prod_Sku_{sku}"
    if dst.exists():
        shutil.rmtree(dst)
    (dst / str(song_id)).mkdir(parents=True)
    (dst / "textures").mkdir()

    ids = [(f"Prod_Sku_{old_sku}", f"Prod_Sku_{sku}"), (f"cover_{old_id}", f"cover_{song_id}")]

    cfg = sub_all((src / "config.xml").read_text("utf-8"), ids)
    cfg = cfg.replace(f"{old_id}/", f"{song_id}/")
    cfg = re.sub(r"<PRODUCT_CODE>\d+</PRODUCT_CODE>", f"<PRODUCT_CODE>{song_id}</PRODUCT_CODE>", cfg)
    cfg = re.sub(r"<PRODUCT_DESC>.*?</PRODUCT_DESC>", f"<PRODUCT_DESC>{artist} - {title}</PRODUCT_DESC>", cfg)
    cfg = re.sub(r"<PRODUCT_NAME>.*?</PRODUCT_NAME>", f"<PRODUCT_NAME>{artist}</PRODUCT_NAME>", cfg)
    (dst / "config.xml").write_text(cfg, "utf-8", newline="\n")

    songs = (src / "songs_1_0.xml").read_text("utf-8")
    songs = songs.replace(f'<SONG ID="{old_id}"', f'<SONG ID="{song_id}"')
    songs = re.sub(r'ID="%s"' % old_act, f'ID="{song_id}"', songs)
    songs = re.sub(r"<TITLE>.*?</TITLE>", f"<TITLE>{title}</TITLE>", songs)
    songs = re.sub(r"<TITLE_KEY>.*?</TITLE_KEY>", f"<TITLE_KEY>{title.upper()}</TITLE_KEY>", songs)
    songs = re.sub(r"<PERFORMANCE_NAME>.*?</PERFORMANCE_NAME>", f"<PERFORMANCE_NAME>{artist}</PERFORMANCE_NAME>", songs)
    songs = re.sub(r"<PERFORMANCE_NAME_KEY>.*?</PERFORMANCE_NAME_KEY>",
                   f"<PERFORMANCE_NAME_KEY>{artist.upper()}</PERFORMANCE_NAME_KEY>", songs)
    (dst / "songs_1_0.xml").write_text(songs, "utf-8", newline="\n")

    acts = (src / "acts_1_0.xml").read_text("utf-8").replace(f'ID="{old_act}"', f'ID="{song_id}"')
    acts = re.sub(r"<NAME>.*?</NAME>", f"<NAME>{artist}</NAME>", acts)
    acts = re.sub(r"<NAME_KEY>.*?</NAME_KEY>", f"<NAME_KEY>{artist.upper()}</NAME_KEY>", acts)
    (dst / "acts_1_0.xml").write_text(acts, "utf-8", newline="\n")

    (dst / "covers.xml").write_text(sub_all((src / "covers.xml").read_text("utf-8"), ids), "utf-8", newline="\n")
    for tex in (src / "textures").iterdir():
        shutil.copy2(tex, dst / "textures" / tex.name)

    melody = (src / old_id / "melody_1.xml").read_bytes()
    (dst / str(song_id) / "melody_1.xml").write_bytes(melody)
    (dst / "melodies_1.chc").write_bytes(chc.pack(melody, song_id))
    for media in ("video.mp4", "preview.mp4", "audiopreview.mp4"):
        if (src / old_id / media).exists():
            shutil.copy2(src / old_id / media, dst / str(song_id) / media)

    print(f"{src.name} (song {old_id}) -> {dst} (song {song_id})")


if __name__ == "__main__":
    if len(sys.argv) != 7:
        sys.exit(__doc__)
    a = sys.argv[1:]
    main(Path(a[0]), Path(a[1]), a[2], int(a[3]), a[4], a[5])
