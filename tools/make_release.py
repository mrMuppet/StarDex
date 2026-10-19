"""Put together the shareable SingStar PS4 custom-song tools: release/SingStar-PS4-CustomSongs/ (+ .zip).

  python make_release.py

Only tools, no songs. Copies the needed modules (private paths removed), PkgTool, the payload (dl0link.elf +
source), the GoldHEN patch and the docs (tools/release_readme.md = package guide, tools/release_discpack.md),
then scans every file for private data (IPs, account id, local paths, names) and stops if anything is found.
lib/PkgTool (third-party binaries, copied unchanged) is not scanned.
"""
import json
import re
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
OUT = ROOT / "release" / "SingStar-PS4-CustomSongs"
MODULES = ["us_to_ps4.py", "ps3_to_ps4.py", "to_ps3.py", "songid.py", "chc.py", "psarc.py", "ps4_discpack.py",
           "build_dlc.py"]
SCRIPTS = ["singstar_pkg.py", "singstar_pack.py", "ps4_install.py"]
PAYLOAD = ["dl0link.elf", "dl0link.c", "Makefile", "payload.ld"]
# (file, pattern, replacement): private paths / data that must not leave this PC
SCRUB = [
    ("us_to_ps4.py", r'import local_config[^\n]*\nPS3_EXPORT = [^\n]*', "PS3_EXPORT = None  # no PS3 library"),
]


def private_patterns() -> list[str]:
    # local drives/paths of this PC (README examples like D:\UltraStar are fine)
    pats = [r"192\.168\.\d+\.\d+", r"\b[QqCc]:[/\\]", r"claude\.code", r"ultraStarWorker", r"Song Library"]
    own = TOOLS / "release_private.txt"  # optional, not in the repository: one regex per line (own name, mail, ...)
    if own.exists():
        pats += [s.strip() for s in own.read_text("utf-8").splitlines() if s.strip() and not s.startswith("#")]
    cfg = TOOLS / "dev" / "remote" / "ps4ctl.json"
    if cfg.exists():  # Remote Play account id; the user name there is just a generic word
        c = json.loads(cfg.read_text("utf-8"))
        pats += [re.escape(str(c["account_b64"]))] if c.get("account_b64") else []
    return pats


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "lib").mkdir(parents=True)
    (OUT / "ps4" / "payload_source").mkdir(parents=True)
    for m in MODULES:
        shutil.copy2(TOOLS / m, OUT / "lib" / m)
    for s in SCRIPTS:
        shutil.copy2(TOOLS / s, OUT / s)
    for fname, pat, rep in SCRUB:
        p = OUT / "lib" / fname
        t, n = re.subn(pat, rep, p.read_text("utf-8"))
        if n != 1:
            sys.exit(f"scrub pattern not found in {fname}: {pat}")
        p.write_text(t, "utf-8", newline="\n")
    shutil.copy2(TOOLS / "payload" / "dl0link.elf", OUT / "ps4" / "dl0link.elf")
    for n in PAYLOAD[1:]:
        shutil.copy2(TOOLS / "payload" / n, OUT / "ps4" / "payload_source" / n)
    sys.path.insert(0, str(TOOLS))
    import ps4_discpack
    (OUT / "ps4" / "CUSA00033.xml").write_text(ps4_discpack.patch_xml(), "utf-8", newline="\n")
    shutil.copytree(TOOLS / "PkgTool", OUT / "lib" / "PkgTool")
    shutil.copy2(TOOLS / "release_readme.md", OUT / "README.md")
    shutil.copy2(TOOLS / "release_discpack.md", OUT / "DISC_PACK.md")

    bad = []
    pats = [re.compile(p) for p in private_patterns()]
    for p in OUT.rglob("*"):
        if p.is_file() and "PkgTool" not in p.parts:
            text = p.read_bytes().decode("latin-1")
            for rx in pats:
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    bad.append(f"{p.relative_to(OUT)}:{line}: {m.group(0)!r}")
    if bad:
        print("PRIVATE DATA FOUND - release not finished:")
        print("\n".join("  " + b for b in bad))
        sys.exit(1)
    for p in OUT.rglob("__pycache__"):
        shutil.rmtree(p)
    zipf = shutil.make_archive(str(OUT), "zip", OUT.parent, OUT.name)
    files = sorted(str(p.relative_to(OUT)) for p in OUT.rglob("*") if p.is_file())
    print("\n".join(files))
    print(f"-> {OUT}\n-> {zipf} ({Path(zipf).stat().st_size / 1024:.0f} KB), privacy scan clean")


if __name__ == "__main__":
    main()
