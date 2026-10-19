"""Download songs from USDB with the existing UltraStarWorker tool (<usdb_worker>/usdb_download.py:
TXT, cover, audio + video via yt-dlp, then fix_songs.py). Runs in that project's venv; the USDB login is passed from
the manager's settings as USDB_USER/USDB_PASS (environment only, not written anywhere). Target: the UltraStar folder.
"""
import os
import re
import subprocess
from pathlib import Path

import consoles
import library
import local_config  # noqa: E402  (tools/, on sys.path via library)
import store

WORKER = local_config.path("usdb_worker")  # optional: UltraStarWorker folder


def worker_python() -> Path:
    p = WORKER / ".venv" / "Scripts" / "python.exe"
    return p if p.exists() else Path("python")


class USDBDownloadJob(consoles.Job):
    def __init__(self, cfg: dict, ids: list[int], video: bool = True, force: bool = False):
        super().__init__(f"{len(ids)} Songs von USDB laden" if len(ids) > 1 else f"USDB-Song {ids[0]} laden")
        self.cfg, self.ids, self.video, self.force = cfg, ids, video, force
        self.total = len(ids)
        self.folders: list[str] = []
        self.after = None

    def run(self):
        import usdb
        if not usdb.JOBS.acquire(blocking=False):
            self.current = "wartet auf die laufende USDB-Aufgabe …"
            usdb.JOBS.acquire()
        try:
            self._run_locked()
        finally:
            usdb.JOBS.release()

    def _run_locked(self):
        script = WORKER / "usdb_download.py"
        if not script.exists():
            raise RuntimeError(f"{script} nicht gefunden")
        sec = store.load("secrets", {})
        if not sec.get("usdb_user") or not sec.get("usdb_pass"):
            raise RuntimeError("USDB-Zugangsdaten fehlen (Einstellungen)")
        out = library.path(self.cfg["ultrastar_dir"])
        cmd = [str(worker_python()), "-u", str(script), "--out", str(out), *map(str, self.ids)]
        if not self.video:
            cmd.append("--no-video")
        if self.force:  # new USDB version: load again although the song is there
            cmd.append("--force")
        env = {**os.environ, "USDB_USER": sec["usdb_user"], "USDB_PASS": sec["usdb_pass"],
               "PYTHONIOENCODING": "utf-8"}
        self.current = "lädt …"
        p = subprocess.Popen(cmd, cwd=WORKER, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", env=env, stdin=subprocess.DEVNULL)
        self.proc = p
        for raw in p.stdout:
            for line in raw.replace("\r", "\n").splitlines():
                if not line.strip() or line.startswith("[download]"):
                    continue  # yt-dlp progress lines
                self.log.append(line.rstrip())
                m = re.match(r"== \[(\d+)\] (.+?)(?::\s*schon vorhanden.*)?$", line.strip())
                if m:
                    self.done_bytes += 1
                    self.current = m.group(2)
                    self.folders.append(m.group(2))
                    self.done.append(f"{m.group(1)} {m.group(2)}")
                if line.startswith("!! FEHLER"):
                    self.errors.append(line[3:].strip())
            if self.cancelled:
                p.kill()
        p.wait()
        if p.returncode and not self.errors:
            self.errors.append(f"Downloader beendet mit Code {p.returncode} (siehe Protokoll)")
        store.log("usdb", f"{len(self.done)} Songs von USDB geladen" + (f", {len(self.errors)} Fehler" if self.errors else ""),
                  ids=self.ids[:200])
        if self.after:
            self.after(self)

    def state(self) -> dict:
        st = super().state()
        st["unit"] = "Songs"
        return st
