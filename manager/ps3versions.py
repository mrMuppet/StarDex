"""Where PS3 versions of songs are built (720p video, PS3 preview) and whether they stay on the PC.

SingStar PS3 plays at most 1280x720 (test 30.09.: 1080p stays black, also with WIDTH/HEIGHT in songs_4_0.xml).
Songs whose source already fits (PS3 library, PS3 discs) need no PS3 version; UltraStar songs above 720p do.
Setting "ps3_keep" (manager/data/settings.json):
  true  -> versions stay in ps3_dir/<ps3 id>/ and are reused for later uploads (costs disk space)
  false -> built in ps3_dir/_temp/<ps3 id>/ and deleted after the upload to the PS3
"""
import shutil
from pathlib import Path

import library
import store

DEFAULT_DIR = str(library.ROOT / "build" / "ps3")
MAX_HEIGHT = 720


def settings() -> dict:
    s = store.load("settings", {})
    return {"keep": bool(s.get("ps3_keep", True)), "dir": s.get("ps3_dir") or DEFAULT_DIR}


def needs_version(width: int, height: int) -> bool:
    return height > MAX_HEIGHT or width > 1280


def work_dir(ps3_id: int) -> Path:
    st = settings()
    root = Path(st["dir"])
    return root / str(ps3_id) if st["keep"] else root / "_temp" / str(ps3_id)


def stored(ps3_id: int) -> Path | None:
    """A kept PS3 version (video.mp4 present), reusable without converting again."""
    d = Path(settings()["dir"]) / str(ps3_id)
    return d if (d / "video.mp4").exists() else None


def after_upload(ps3_id: int) -> None:
    """Called after a PS3 version was uploaded: drop it unless it should be kept."""
    if not settings()["keep"]:
        shutil.rmtree(Path(settings()["dir"]) / "_temp" / str(ps3_id), ignore_errors=True)


def usage() -> dict:
    root = Path(settings()["dir"])
    if not root.is_dir():
        return {"songs": 0, "bytes": 0}
    songs = [d for d in root.iterdir() if d.is_dir() and d.name.isdigit()]
    size = sum(f.stat().st_size for d in songs for f in d.rglob("*") if f.is_file())
    return {"songs": len(songs), "bytes": size}
