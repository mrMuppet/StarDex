"""Settings of this setup (console IPs, folders), read from manager/config.json (kept out of the repository).

Copy manager/config.example.json to manager/config.json and fill it in.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "manager" / "config.json"
_UNSET = object()


def _cfg():
    try:
        return json.loads(CONFIG.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def host(console):
    """IP of "ps4" or "ps3"; a placeholder if it is missing."""
    return (_cfg().get(console) or {}).get("host") or f"{console.upper()}-IP-fehlt-in-manager-config.json"


def path(key, missing=_UNSET):
    """Folder/file from config.json. If it is not set: `missing` if given, else a path that does not exist
    (named after the key, so errors say what to fill in)."""
    v = _cfg().get(key)
    if v:
        return Path(v) if Path(v).is_absolute() else ROOT / v  # relative = inside the project, as in the manager
    return ROOT / f"_{key}_fehlt_in_manager_config.json" if missing is _UNSET else missing
