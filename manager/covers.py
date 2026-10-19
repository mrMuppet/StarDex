"""Cover images for every song, cached as manager/cache/covers/<id>.jpg (256x256).

Sources in order: UltraStar cover file, imported PS3 disc / PS3 library (covers.xml names a region U/V/WIDTH/HEIGHT
of textures/<page>.jpg), PS2 disc (texture pages, tools/ps2_to_ps4.Disc.cover).
"""
import re
import threading
from functools import lru_cache
from pathlib import Path

CACHE = Path(__file__).parent / "cache" / "covers"
_lock = threading.Lock()
_discs = {}


@lru_cache(maxsize=16)
def _covers_xml(export: str) -> dict[int, dict]:
    p = Path(export) / "covers.xml"
    if not p.exists():
        return {}
    out = {}
    for m in re.finditer(r'<TPAGE_BIT NAME="cover_(\d+)"([^>]*)/>', p.read_text("utf-8", errors="replace")):
        out[int(m.group(1))] = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
    return out


def _from_export(export: Path, sid: int):
    from PIL import Image
    a = _covers_xml(str(export)).get(sid)
    page = a and export / "textures" / f"{a.get('TEXTURE')}.jpg"
    if not page or not page.exists():
        return None
    u, v, w, h = (int(float(a[k])) for k in ("U", "V", "WIDTH", "HEIGHT"))
    return Image.open(page).convert("RGB").crop((u, v, u + w, v + h))


def _from_ps2(iso: str, sid: int):
    from ps2_to_ps4 import Disc
    if iso not in _discs:
        _discs[iso] = Disc(Path(iso))
    return _discs[iso].cover(sid)


def cover(s: dict) -> Path | None:
    us = s["sources"].get("ultrastar", {}).get("cover")
    if us:
        return Path(us)
    out = CACHE / f"{s['id']}.jpg"
    if out.exists():
        return out
    with _lock:
        if out.exists():
            return out
        img = None
        try:
            for key in ("ps3disc", "ps3lib"):
                src = s["sources"].get(key)
                if src and img is None:
                    export = Path(src.get("export") or Path(src["dir"]).parent)
                    img = _from_export(export, src["id"])
            ps2 = s["sources"].get("ps2")
            if img is None and ps2 and ps2.get("iso"):
                img = _from_ps2(ps2["iso"], s["id"])
        except Exception:  # noqa: BLE001  a broken texture must not break the list
            img = None
        if img is None:
            return None
        CACHE.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        img.convert("RGB").resize((256, 256), Image.LANCZOS).save(out, quality=88)
        return out


def available(s: dict) -> bool:
    return bool(s["sources"].get("ultrastar", {}).get("cover") or s["sources"].get("ps3disc")
                or s["sources"].get("ps3lib") or s["sources"].get("ps2", {}).get("iso"))
