"""Read SingStar disc images into the PC library.

  python disc_import.py <file.iso|file.7z> [...]

PS3 (decrypted .dec.iso; Redump ISOs must be decrypted first, e.g. PS3 ISO Tools):
  7-Zip extracts PS3_GAME/USRDIR/Pack*.pkd (+ PARAM.SFO, DiscInfo), scee_london (EdnessP, GPL-3.0, tools/scee_london)
  unpacks them -> filesystem/export/<id>/{melody_N.xml, video.mp4, preview.mp4} + songs_N_0.xml, acts, covers,
  textures. The export is normalised like a Toolbox export (songs_4_0.xml / acts_4_0.xml = newest version), so
  ps3_to_ps4.py / batch_ps3.py --export convert it unchanged. Target: PS3_IMPORTS/<Disc>/export/.
PS2 (.iso): 7-Zip extracts the ISO to PS2_ROOT/<Disc>/<Disc>_ISO/ (layout of the existing discs), where
  batch_ps2.py / ps2_to_ps4.py pick it up.
.7z archives are unpacked first (disc image inside).
"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SEVENZIP = Path("C:/Program Files/7-Zip/7z.exe")
SCEE = Path(__file__).parent / "scee_london" / "windows" / "scee_london.exe"
import local_config  # noqa: E402

PS3_IMPORTS = local_config.path("ps3_imports")
PS2_ROOT = local_config.path("ps2_root")
KEYS_DB = local_config.path("toolbox_keys_db")


class ImportError_(Exception):
    pass


def run(cmd: list, log=print) -> str:
    p = subprocess.run([str(c) for c in cmd], capture_output=True)
    out = (p.stdout + p.stderr).replace(b"\x00", b"").decode("utf-8", errors="replace")
    if p.returncode:
        raise ImportError_(f"{Path(str(cmd[0])).name} fehlgeschlagen: {out.strip().splitlines()[-1] if out.strip() else p.returncode}")
    return out


def listing(path: Path, typ: str | None = None) -> list[str]:
    cmd = [SEVENZIP, "l", "-slt"] + ([f"-t{typ}"] if typ else []) + [path]
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return re.findall(r"^Path = (.+)$", p.stdout, re.M)[1:]


def disc_name(path: Path) -> str:
    n = re.sub(r"\.dec$", "", path.stem)
    n = re.sub(r"\s*\((?:En|De|Fr),[^)]*\)", "", n)
    return re.sub(r"[<>:\"/\\|?*]", "", n).strip()


def detect(path: Path) -> dict:
    """{'kind': 'ps3'|'ps2'|'archive'|'unknown', 'name': ...}"""
    ext = path.suffix.lower()
    if ext in (".7z", ".zip", ".rar"):
        inner = [n for n in listing(path) if n.lower().endswith(".iso")]
        return {"kind": "archive", "name": disc_name(Path(inner[0]) if inner else path), "inner": inner}
    if ext != ".iso":
        return {"kind": "unknown", "name": path.name}
    names = [n.replace("\\", "/").upper() for n in listing(path, "iso")]
    if any(n.startswith("PS3_GAME/") for n in names):
        return {"kind": "ps3", "name": disc_name(path), "packs": [n for n in names if n.endswith(".PKD")]}
    if "SYSTEM.CNF" in names:
        return {"kind": "ps2", "name": disc_name(path)}
    return {"kind": "unknown", "name": disc_name(path)}


def serial_name(serial: str) -> str | None:
    if not KEYS_DB.exists():
        return None
    m = re.search(serial + r"\|([^|]+)\|", KEYS_DB.read_bytes().decode("latin-1"))
    return re.sub(r"\s*\((Europe|Germany|USA|Spain|France|Italy|Australia|Asia)\)", "", m.group(1)).strip() if m else None


def import_ps3(iso: Path, log=print, name: str | None = None, source: Path | None = None) -> Path:
    if not SCEE.exists():
        raise ImportError_(f"{SCEE} fehlt")
    name = name or disc_name(iso)
    dest = PS3_IMPORTS / name
    if (dest / "export" / "songs_4_0.xml").exists():
        log(f"schon eingelesen: {dest}")
        return dest / "export"
    work = PS3_IMPORTS / "_work" / name
    work.mkdir(parents=True, exist_ok=True)
    try:
        log("PS3-ISO: Pakete aus dem Abbild kopieren (dauert einige Minuten) …")
        run([SEVENZIP, "e", "-tiso", "-y", f"-o{work}", iso, "PS3_GAME/USRDIR/Pack*.pkd", "PS3_GAME/USRDIR/DiscInfo",
             "PS3_GAME/PARAM.SFO"])
        packs = sorted(work.glob("Pack*.pkd"))
        if not packs:
            raise ImportError_("keine Pack*.pkd im Abbild – ist es eine SingStar-PS3-Disc?")
        sfo = (work / "PARAM.SFO").read_bytes() if (work / "PARAM.SFO").exists() else b""
        m = re.search(rb"([A-Z]{4}\d{5})", sfo)
        serial = m.group(1).decode() if m else ""
        for p in packs:
            log(f"{p.name} auspacken (scee_london) …")
            out = run([SCEE, p, "-o", work / "out"])
            if "Done" not in out:
                raise ImportError_(f"{p.name}: scee_london meldet kein Ergebnis – Abbild evtl. noch verschlüsselt "
                                   "(Redump-ISO → vorher entschlüsseln, .dec.iso verwenden)")
            p.unlink()  # 3–7 GB each, the unpacked files are what we keep
        exp = work / "out" / "filesystem" / "export"
        if not exp.is_dir():
            raise ImportError_("keine filesystem/export im entpackten Paket")
        for kind in ("songs", "acts"):
            vers = sorted(exp.glob(f"{kind}_*_0.xml"), key=lambda f: int(re.search(r"_(\d+)_0", f.name).group(1)))
            if vers:
                shutil.copy2(vers[-1], exp / f"{kind}_4_0.xml")
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / "export").exists():
            shutil.rmtree(dest / "export")
        shutil.move(str(exp), dest / "export")
        songs = len(re.findall(r"<SONG ID=", (dest / "export" / "songs_4_0.xml").read_text("utf-8", errors="replace")))
        info = {"name": name, "serial": serial, "edition": serial_name(serial) or name, "source": str(source or iso),
                "songs": songs}
        (dest / "disc.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
        log(f"fertig: {songs} Songs → {dest / 'export'}")
        return dest / "export"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def import_ps2(iso: Path, log=print, name: str | None = None) -> Path:
    name = name or disc_name(iso)
    dest = PS2_ROOT / name / f"{name}_ISO"
    if dest.exists() and any(dest.iterdir()):
        log(f"schon eingelesen: {dest}")
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    log("PS2-ISO entpacken …")
    run([SEVENZIP, "x", "-y", f"-o{dest}", iso])
    log(f"fertig → {dest}")
    return dest


def import_path(path: Path, log=print, source: Path | None = None) -> dict:
    info = detect(path)
    if info["kind"] == "archive":
        if not info["inner"]:
            raise ImportError_("Archiv enthält kein .iso")
        name = info["name"]
        if (PS3_IMPORTS / name / "export" / "songs_4_0.xml").exists():
            log(f"schon eingelesen: {PS3_IMPORTS / name}")
            return {"kind": "ps3", "name": name, "dir": str(PS3_IMPORTS / name / "export"), "existing": True}
        ps2 = PS2_ROOT / name / f"{name}_ISO"
        if ps2.is_dir() and any(ps2.iterdir()):
            log(f"schon eingelesen: {ps2}")
            return {"kind": "ps2", "name": name, "dir": str(ps2), "existing": True}
        # own work folder: tempfile.mkdtemp hangs on the Q: drive (retries PermissionError)
        tmp = PS3_IMPORTS / "_work" / f"archive_{int(time.time())}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            log(f"Archiv entpacken: {info['inner'][0]} …")
            run([SEVENZIP, "e", "-y", f"-o{tmp}", path, info["inner"][0]])
            return import_path(tmp / Path(info["inner"][0]).name, log, source=path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if info["kind"] == "ps3":
        return {"kind": "ps3", "name": info["name"], "dir": str(import_ps3(path, log, source=source))}
    if info["kind"] == "ps2":
        return {"kind": "ps2", "name": info["name"], "dir": str(import_ps2(path, log))}
    raise ImportError_(f"{path.name}: weder PS2- noch PS3-SingStar-Abbild erkannt")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for arg in sys.argv[1:]:
        print(import_path(Path(arg)))
