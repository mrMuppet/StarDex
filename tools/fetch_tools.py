"""Download the third-party programs StarDex needs from their official GitHub releases.

  python tools/fetch_tools.py            fehlende Programme herunterladen (PkgTool, scee_london, IPUenc)
  python tools/fetch_tools.py --check    nur anzeigen, was fehlt (auch .NET, ffmpeg, 7-Zip)
  python tools/fetch_tools.py --force    neu herunterladen, auch wenn schon vorhanden
  python tools/fetch_tools.py --ask      einmalig fragen (für start.bat/start.sh)

Versions and SHA-256 of the release archives are pinned; an archive with another checksum is rejected.
The licence files stay next to the programs (PkgTool: LGPL-3.0, scee_london and IPUenc: GPL-3.0).
"""
import hashlib
import io
import os
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
ASKED = ROOT / ".venv" / "tools.asked"  # start scripts ask only once

DOWNLOADS = {
    "PkgTool": {
        "what": "PS4-Pakete bauen",
        "version": "v0.2.231",
        # (url, sha256, file name; None = zip archive, unpacked into the folder)
        "files": [("https://github.com/maxton/LibOrbisPkg/releases/download/v0.2/PkgTool.Core-0.2.231.zip",
                   "4bdb25a32be28f84ac2aa177fe1ae4285669419d5e15c05968b4d8cf43e872b3", None)],
        "dest": TOOLS / "PkgTool",
        "check": "PkgTool.Core.dll",
        "license": "LGPL-3.0 (LICENSE.txt)",
    },
    "scee_london": {
        "what": "PS3-Discs einlesen",
        "version": "v1.4.3",
        "files": [("https://github.com/EdnessP/scee-london/releases/download/v1.4.3/scee_london.zip",
                   "61385fbf06a8c360eb315b4ced7e375765374089a02bb3d38481f903fab50645", None)],
        "dest": TOOLS / "scee_london",
        "check": "windows/scee_london.exe",
        "license": "GPL-3.0 (license.txt)",
        "executable": ["linux/scee_london", "macos/scee_london"],
    },
    "IPUenc": {
        "what": "PS2-Discs einlesen",
        "version": "v1.1",
        # the converters call IPUenc.exe (Windows x64 build); the release has no licence file -> LICENSE from the tag
        "files": [("https://github.com/ravenDS/IPUenc/releases/download/v1.1/IPUenc-win-x64.exe",
                   "2ab0b6e6e6b4dd58737b0e8086520dc2f4fbf4be1718c9437f79ca8fbcc2e1b9", "IPUenc.exe"),
                  ("https://raw.githubusercontent.com/ravenDS/IPUenc/v1.1/LICENSE",
                   "33782d3ca63400559cc3c38acd3ad970f64c3a78888fd89583b5f775b9ad6239", "LICENSE")],
        "dest": TOOLS / "IPUenc",
        "check": "IPUenc.exe",
        "license": "GPL-3.0 (LICENSE)",
    },
}


def _which(name: str, *fallbacks: Path) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    return next((str(p) for p in fallbacks if p.exists()), None)


def status() -> list[dict]:
    """All programs with present/missing and a short hint (for --check and the manager)."""
    out = []
    for name, d in DOWNLOADS.items():
        p = d["dest"] / d["check"]
        out.append({"name": name, "what": d["what"], "ok": p.exists(), "path": str(p), "auto": True,
                    "hint": f"automatisch herunterladbar ({d['version']}, {d['license']})"})
    dotnet = _which("dotnet")
    out.append({"name": ".NET-Runtime", "what": "für PkgTool (PS4-Pakete)", "ok": bool(dotnet), "path": dotnet,
                "auto": False, "hint": "installieren: https://dotnet.microsoft.com/download (z. B. .NET 8)"})
    ff = _which("ffmpeg")
    out.append({"name": "ffmpeg", "what": "Songs umwandeln", "ok": bool(ff), "path": ff, "auto": False,
                "hint": "installieren und in den PATH: https://ffmpeg.org (Windows: winget install ffmpeg)"})
    sz = Path("C:/Program Files/7-Zip/7z.exe")
    out.append({"name": "7-Zip", "what": "Disc-Abbilder einlesen", "ok": sz.exists(), "path": str(sz), "auto": False,
                "hint": "installieren: https://www.7-zip.org"})
    return out


def missing() -> list[str]:
    return [n for n, d in DOWNLOADS.items() if not (d["dest"] / d["check"]).exists()]


def fetch(name: str, log=print) -> Path:
    """Download, verify and unpack one program into its folder (replaces an older copy only on success)."""
    d = DOWNLOADS[name]
    log(f"{name} {d['version']} herunterladen …")
    dest = d["dest"]
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        for url, sha256, save_as in d["files"]:
            req = urllib.request.Request(url, headers={"User-Agent": "StarDex"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            digest = hashlib.sha256(data).hexdigest()
            if digest != sha256:
                raise RuntimeError(f"Prüfsumme stimmt nicht für {url.rsplit('/', 1)[-1]} (erwartet {sha256}, "
                                   f"erhalten {digest}) – Download nicht verwendet")
            if save_as:
                (tmp / save_as).write_bytes(data)
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for m in z.infolist():
                    if not (tmp / m.filename).resolve().is_relative_to(tmp.resolve()):
                        raise RuntimeError(f"unerwarteter Pfad im Archiv: {m.filename}")
                z.extractall(tmp)
        if not (tmp / d["check"]).exists():
            raise RuntimeError(f"{d['check']} fehlt im Download")
        for rel in d.get("executable", []):
            p = tmp / rel
            if p.exists():
                p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    log(f"{name} {d['version']} → {dest.relative_to(ROOT)} (Lizenz: {d['license']})")
    return dest


def fetch_missing(force: bool = False, log=print) -> list[str]:
    errors = []
    for name in (list(DOWNLOADS) if force else missing()):
        try:
            fetch(name, log)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            log(f"Fehler: {name}: {e}")
    return errors


def print_status():
    for s in status():
        print(f"  {'ok     ' if s['ok'] else 'FEHLT  '} {s['name']:<13} {s['what']}" + ("" if s["ok"] else f" – {s['hint']}"))


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(errors="replace")  # Windows console without PYTHONIOENCODING=utf-8: no crash on "→"
    if "--check" in argv:
        print_status()
        return 0
    if "--ask" in argv:
        if ASKED.exists() or not missing():
            return 0
        ASKED.parent.mkdir(parents=True, exist_ok=True)
        ASKED.write_text("1")
        print("Zusatzprogramme fehlen: " + ", ".join(f"{n} ({DOWNLOADS[n]['what']})" for n in missing()))
        print("Sie werden von GitHub geladen (zusammen unter 1 MB). Später auch im Manager unter Einstellungen.")
        try:
            answer = input("Jetzt herunterladen? [J/n] ").strip().lower()
        except EOFError:
            return 0
        if answer not in ("", "j", "ja", "y", "yes"):
            return 0
    errors = fetch_missing(force="--force" in argv)
    print_status()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
