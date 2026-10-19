"""Small JSON stores in manager/data/: decisions (duplicates), wishlist, settings/secrets, history log."""
import json
import threading
import time
from pathlib import Path

DATA = Path(__file__).parent / "data"
_lock = threading.Lock()


def load(name: str, default):
    p = DATA / f"{name}.json"
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def save(name: str, data) -> None:
    with _lock:
        DATA.mkdir(exist_ok=True)
        tmp = DATA / f"{name}.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(DATA / f"{name}.json")


def log(kind: str, text: str, **extra) -> None:
    with _lock:
        DATA.mkdir(exist_ok=True)
        with (DATA / "history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "kind": kind, "text": text, **extra}, ensure_ascii=False) + "\n")


def history(limit: int = 300) -> list[dict]:
    p = DATA / "history.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]
    return rows[-limit:][::-1]
