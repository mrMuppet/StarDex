"""Build a SingStar PS4 fake-DLC (.pkg with extra data) from a pack root folder.

  python build_dlc.py ROOT_DIR auto|LABEL16 "DLC TITLE" OUT_DIR
  e.g. python build_dlc.py build/x/root auto "Matilda" build/x

ROOT_DIR contains one Prod_Sku_XXXXXX/...; sce_sys/param.sfo (+ icon0.png if present) is generated here.
"auto" derives the label from the Prod_Sku folder (XXXXXX + 10 zeros). The pack must hold exactly the
song whose id equals the label's base-36 digits (songid.py) - otherwise the game purges it.
Needs tools/PkgTool (LibOrbisPkg PkgTool.Core) and the dotnet runtime.
"""
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import quoteattr

TITLE_ID = "CUSA00033"
CONTENT_PREFIX = "EP9000-CUSA00033_00-"
PKGTOOL = Path(__file__).parent / "PkgTool" / "PkgTool.Core.dll"

sys.path.insert(0, str(Path(__file__).parent))
import songid  # noqa: E402


def pkgtool(*args: str) -> None:
    # PkgTool targets .NET Core 3.0: allow a newer runtime (e.g. only .NET 8 installed, tested 02.10.)
    env = {**os.environ, "DOTNET_ROLL_FORWARD": os.environ.get("DOTNET_ROLL_FORWARD", "Major")}
    subprocess.run(["dotnet", str(PKGTOOL), *args], check=True, env=env)


def make_sfo(path: Path, content_id: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    pkgtool("sfo_new", str(path))
    entries = [
        ("ATTRIBUTE", "integer", "0", 4),
        ("CATEGORY", "utf8", "ac", 4),
        ("CONTENT_ID", "utf8", content_id, 48),
        ("FORMAT", "utf8", "obs", 4),
        ("TITLE", "utf8", title, 128),
        ("TITLE_ID", "utf8", TITLE_ID, 12),
        ("VERSION", "utf8", "01.00", 8),
    ]
    for name, typ, value, maxsize in entries:
        pkgtool("sfo_setentry", "--value", value, "--type", typ, "--maxsize", str(maxsize), str(path), name)


def dir_xml(d: Path, root: Path, indent: str) -> str:
    out = []
    for sub in sorted(p for p in d.iterdir() if p.is_dir()):
        inner = dir_xml(sub, root, indent + "  ")
        if inner:
            out.append(f"{indent}<dir targ_name={quoteattr(sub.name)}>\n{inner}{indent}</dir>\n")
        else:
            out.append(f"{indent}<dir targ_name={quoteattr(sub.name)} />\n")
    return "".join(out)


def make_gp4(root: Path, gp4: Path, content_id: str) -> None:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    file_lines = "".join(
        f"    <file targ_path={quoteattr(p.relative_to(root).as_posix())} "
        f"orig_path={quoteattr(str(p.resolve()))} />\n" for p in files)
    zeros = "0" * 32
    gp4.write_text(
        '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        '<psproject fmt="gp4" version="1000">\n'
        "  <volume>\n"
        "    <volume_type>pkg_ps4_ac_data</volume_type>\n"
        "    <volume_id>PS4VOLUME</volume_id>\n"
        f"    <volume_ts>{datetime.now():%Y-%m-%d %H:%M:%S}</volume_ts>\n"
        f'    <package content_id="{content_id}" passcode="{zeros}" entitlement_key="{zeros}" />\n'
        "  </volume>\n"
        '  <files img_no="0">\n'
        f"{file_lines}"
        "  </files>\n"
        "  <rootdir>\n"
        f"{dir_xml(root, root, '    ')}"
        "  </rootdir>\n"
        "</psproject>\n",
        encoding="utf-8")


def main(root: Path, label: str, title: str, out: Path, unsafe: bool = False) -> None:
    packs = list(root.glob("Prod_Sku_*"))
    if len(packs) != 1:
        sys.exit(f"expected exactly one Prod_Sku_* folder in {root}, found {len(packs)}")
    pack = packs[0]
    if label == "auto":
        label = pack.name.removeprefix("Prod_Sku_").ljust(16, "0")
    if len(label) != 16 or not label.isalnum() or label != label.upper():
        sys.exit("LABEL16 must be 16 uppercase alphanumeric characters")
    if not pack.name.endswith(label[:6]):
        sys.exit(f"{pack.name} does not match label {label} (folder must be Prod_Sku_{label[:6]})")
    content_id = CONTENT_PREFIX + label
    missing = [f for f in ("config.xml", "songs_1_0.xml") if not (pack / f).exists()]
    if missing or not list(pack.glob("*/video.mp4")):
        sys.exit(f"incomplete pack {pack}: missing {missing or ['*/video.mp4']}")
    ids = [int(i) for i in re.findall(r'<SONG ID="(\d+)"', (pack / "songs_1_0.xml").read_text("utf-8"))]
    if not unsafe and ids != [songid.id_from_label(label)]:
        sys.exit(f"label {label} expects song id {songid.id_from_label(label)}, pack holds {ids} "
                 f"- the game would purge it (use --unsafe only for experiments)")
    make_sfo(root / "sce_sys" / "param.sfo", content_id, title)
    out.mkdir(parents=True, exist_ok=True)
    gp4 = out / f"{label}.gp4"
    make_gp4(root, gp4, content_id)
    pkgtool("pkg_build", str(gp4), str(out))
    print(f"built {content_id}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--unsafe"]
    if len(args) != 4:
        sys.exit(__doc__)
    main(Path(args[0]), args[1], args[2], Path(args[3]), unsafe="--unsafe" in sys.argv)
