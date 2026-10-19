"""Write songs to the PS3 (webMAN FTP, /dev_hdd0/FileSystem/Export).

Per song: <id>/{video.mp4, preview.mp4, melody_4.xml, melody.xml} and textures/page_<id>.jpg are uploaded first;
then songs_4_0.xml, acts_4_0.xml, covers.xml and songlists_4.xml are changed ONCE for all songs of the job:
  songs     - <SONG ID=id> replaced or appended
  acts      - <ACT> for the song's act (id = song id unless taken by another artist)
  covers    - <TPAGE_BIT NAME="cover_<id>" TEXTURE="page_<id>" 256x256>
  songlists - SONG_REF in the Carousel (every song must be there, see singstar_fixer.py)
Every changed list is parsed (must be valid XML, song count as expected) before upload, read back and compared;
the old lists are backed up to data/backups/ps3/ first. SingStar must be restarted to see the changes.
"""
import html
import io
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import consoles
import library
import ps3versions
import store

EXPORT = consoles.PS3_EXPORT
LISTS = ("songs_4_0.xml", "acts_4_0.xml", "covers.xml", "songlists_4.xml")
TOOLS = library.ROOT / "tools"


def ps3_source(s: dict) -> str | None:
    """Which source a PS3 version is built from (PS3 library songs are on the PS3 already)."""
    us = s["sources"].get("ultrastar", {})
    if us.get("txt") and not us.get("duet") and s["id"] > 0:
        return "ultrastar"
    if "ps3disc" in s["sources"]:
        return "ps3disc"
    ps2 = s["sources"].get("ps2")
    if ps2 and not ps2.get("skip"):
        return "ps2"
    if "ps4pkg" in s["sources"]:
        return "ps4pkg"
    return None


def build_version(s: dict, src: str, log) -> Path:
    pid = 60000 + (s["id"] - library.songid.CUSTOM_BASE) if s["id"] >= library.songid.CUSTOM_BASE else s["id"]
    keep = ps3versions.stored(pid)
    # a stored version is only reused while its source is unchanged (e.g. GAP edited in the UltraStar .txt since)
    srcfile = {"ultrastar": s["sources"].get("ultrastar", {}).get("txt"),
               "ps2": (s.get("pkg") or {}).get("file")}.get(src)
    fresh = keep and (keep / "entry.json").exists() and not (
        srcfile and Path(srcfile).exists() and Path(srcfile).stat().st_mtime > (keep / "entry.json").stat().st_mtime)
    if fresh and json.loads((keep / "entry.json").read_text("utf-8")).get("source") == src:
        log(f"{pid}: gespeicherte PS3-Fassung wird verwendet")
        return keep
    out = ps3versions.work_dir(pid)
    out.parent.mkdir(parents=True, exist_ok=True)
    if src == "ultrastar":
        cmd = ["ultrastar", s["sources"]["ultrastar"]["folder"], str(out), "--ps4-id", str(s["id"])]
    elif src == "ps4pkg":
        cmd = ["ps4pack", s["sources"]["ps4pkg"]["pack"], str(s["id"]), str(out)]
    elif src == "ps3disc":
        cmd = ["ps3disc", s["sources"]["ps3disc"]["export"], str(s["id"]), str(out)]
    elif s.get("pkg") and s["pkg"]["source"] == "ps2" and Path(s["pkg"]["file"]).exists():
        # finished PS4 package from the same PS2 song: unpack + adapt (seconds) instead of converting the disc
        # again (minutes, vocal separation). PS2 videos are <= 720p, the picture is copied, the sound raised to PS3 level
        rep = (s.get("pkgs", {}).get("ps2") or {}).get("report") or {}
        m = re.search(r"-> (-?[\d.]+) LUFS", str(rep.get("loudness", "")))
        cmd = ["pkg", s["pkg"]["file"], str(s["id"]), str(out), "--source", "ps2",
               "--pkg-loudness", m.group(1) if m else "-12"]
    else:
        ps2 = s["sources"]["ps2"]
        cmd = ["ps2", ps2["iso"], str(s["id"]), str(out), "--lang", ps2.get("lang", "EN")]
    log(f"{pid}: PS3-Fassung bauen ({src}) …")
    p = subprocess.run([sys.executable, str(TOOLS / "to_ps3.py"), *cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr).strip().splitlines()[-1])
    return out


def _nl(text: str) -> str:
    return "\r\n" if "\r\n" in text[:2000] else "\n"


def merge_lists(lists: dict[str, str], entries: list[dict]) -> dict[str, str]:
    songs, acts, covers, sl = (lists[n] for n in LISTS)
    nl = _nl(songs)
    for e in entries:
        pid = e["ps3_id"]
        # act: song's own act id (disc) or the song id, unless another artist uses that id
        aid = e.get("act_id") or pid
        m = re.search(r'<ACT ID="%d">\s*<NAME>(.*?)</NAME>' % aid, acts, re.S)
        if m and html.unescape(m.group(1)).lower() != html.unescape(e["artist"]).lower():
            used = {int(x) for x in re.findall(r'<ACT ID="(\d+)"', acts)}
            aid = max([70000, *used]) + 1
            m = None
        if not m:
            anl = _nl(acts)
            act = (f'  <ACT ID="{aid}">{anl}    <NAME>{e["artist"]}</NAME>{anl}'
                   f'    <NAME_KEY>{e["act_key"]}</NAME_KEY>{anl}  </ACT>{anl}')
            acts = acts.replace("</ACT_SET>", act + "</ACT_SET>", 1)
        block = re.sub(r'(<PERFORMED_BY ID=")[^"]*(">\s*<ACT ID=")[^"]*"', rf'\g<1>{aid}\g<2>{aid}"', e["song"])
        block = "  " + block.replace("\r\n", "\n").replace("\n", nl) + nl
        old = list(re.finditer(r'[ \t]*<SONG ID="%d"[^>]*>.*?</SONG>[ \t]*\r?\n' % pid, songs, re.S))
        if old:
            first = old[0]
            songs = songs[:first.start()] + block + songs[first.end():]
            for o in reversed(list(re.finditer(r'[ \t]*<SONG ID="%d"[^>]*>.*?</SONG>[ \t]*\r?\n' % pid, songs, re.S))[1:]):
                songs = songs[:o.start()] + songs[o.end():]
        else:
            songs = songs.replace("</SONG_SET>", block + "</SONG_SET>", 1)
        cnl = _nl(covers)
        covers = re.sub(r'[ \t]*<TPAGE_BIT NAME="cover_%d"[^>]*/>[ \t]*\r?\n' % pid, "", covers)
        covers = covers.replace("</TPAGE_BIT_SET>", f'  <TPAGE_BIT NAME="cover_{pid}" TEXTURE="page_{pid}" U="0" V="0" '
                                                    f'WIDTH="256" HEIGHT="256"/>{cnl}</TPAGE_BIT_SET>', 1)
        car = re.search(r'<SUBSET Name="Carousel">.*?</SUBSET>', sl, re.S)
        if car and f'SONG_REF ID="{pid}"' not in car.group(0):
            refs = list(re.finditer(r'(\r?\n)([ \t]*)<SONG_REF ID="\d+"></SONG_REF>', car.group(0)))
            at = car.start() + refs[-1].end()  # after the last entry, same line break and indent
            sl = sl[:at] + f'{refs[-1].group(1)}{refs[-1].group(2)}<SONG_REF ID="{pid}"></SONG_REF>' + sl[at:]
    return dict(zip(LISTS, (songs, acts, covers, sl)))


def check_lists(old: dict[str, str], new: dict[str, str], entries: list[dict]) -> None:
    for n in LISTS:
        ET.fromstring(new[n].encode("utf-8"))  # must stay valid XML
    before = set(re.findall(r'<SONG ID="(\d+)"', old["songs_4_0.xml"]))
    after = re.findall(r'<SONG ID="(\d+)"', new["songs_4_0.xml"])
    want = before | {str(e["ps3_id"]) for e in entries}
    if set(after) != want or len(after) != len(set(after)):
        raise RuntimeError("Songliste nach dem Einfügen unplausibel – nichts hochgeladen")


_locks: dict = {}


def _console_lock(cid: str):
    import threading
    return _locks.setdefault(cid, threading.Lock())


class PS3WriteJob(consoles.Job):
    """Write songs to one or more PS3 consoles (console ids). Pipeline: a builder thread makes the PS3 versions,
    each finished song is uploaded right away (to every target console) while the next ones are still being built.
    The song lists (songs_4_0.xml …) are changed once per console at the end, only for songs whose files arrived;
    until then SingStar does not see the new folders, so a cancelled or failed run leaves the PS3 consistent."""

    def __init__(self, cfg: dict, items: list[dict], cids: list[str] | None = None):
        self.cids = cids or ["ps3"]
        where = ", ".join(consoles.name(cfg, c) for c in self.cids)
        super().__init__(f"{len(items)} Songs auf {where} übertragen" if len(items) > 1
                         else f"{items[0]['artist']} – {items[0]['title']} auf {where}")
        self.cfg, self.items = cfg, items
        self.total = len(items) * (1 + len(self.cids))  # one step per song to build + one per song and console
        self.after = None
        self.building = ""

    def _build_all(self, q):
        try:
            for s in self.items:
                if self.cancelled:
                    break
                self.building = f"{s['artist']} – {s['title']}"
                try:
                    d = build_version(s, ps3_source(s), self.log.append)
                    q.put((json.loads((d / "entry.json").read_text("utf-8")), d))
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"{s['artist']} – {s['title']}: {e}")
                    self.done_bytes += len(self.cids)
                self.done_bytes += 1
        finally:
            self.building = ""
            q.put(None)

    LIST_EVERY = 20  # songs per console between song list updates: an abort loses at most this many entries

    def run(self):
        import queue
        import threading
        # one transfer per PS3 at a time (two at once overload webMAN, 09.10.); a second one waits here
        locks = [_console_lock(c) for c in sorted(self.cids)]
        for lk in locks:
            if not lk.acquire(blocking=False):
                self.current = "wartet auf die laufende Übertragung zu dieser PS3 …"
                lk.acquire()
        try:
            self._run_locked(queue, threading)
        finally:
            for lk in locks:
                lk.release()

    def _run_locked(self, queue, threading):
        q = queue.Queue(maxsize=6)  # keeps the builder a few songs ahead, not the whole list on disk
        threading.Thread(target=self._build_all, args=(q,), daemon=True).start()
        ftps, failed = {}, {}
        pending = {cid: [] for cid in self.cids}  # uploaded, not yet in the song lists
        listed = {cid: [] for cid in self.cids}

        def flush(cid):
            if not pending[cid] or cid not in ftps:
                return
            try:
                self._lists(cid, ftps[cid], pending[cid])
                listed[cid] += pending[cid]
            except Exception as ex:  # noqa: BLE001  stay pending; "Lesen" finds them later (unlisted folders)
                self.errors.append(f"{consoles.name(self.cfg, cid)}: Songlisten: {type(ex).__name__}: {ex}")
            pending[cid] = []
        try:
            while True:
                try:
                    item = q.get(timeout=1)
                except queue.Empty:
                    self.current = f"PS3-Fassung bauen: {self.building}" if self.building else self.current
                    continue
                if item is None:
                    break
                e, d = item
                for cid in self.cids:
                    if cid in failed:
                        self.done_bytes += 1
                        continue
                    try:
                        if cid not in ftps:
                            ftps[cid] = consoles.RetryFtp(consoles.get(self.cfg, cid), timeout=60)
                            ftps[cid].on_wait = lambda t: setattr(self, "current", t)
                        self._upload(cid, ftps[cid], e, d)
                        pending[cid].append(e)
                    except Exception as ex:  # noqa: BLE001  this console is skipped from now on
                        failed[cid] = ex
                        self.errors.append(f"{consoles.name(self.cfg, cid)}: {type(ex).__name__}: {ex}")
                    self.done_bytes += 1
                    if len(pending[cid]) >= self.LIST_EVERY:
                        flush(cid)
                ps3versions.after_upload(e["ps3_id"])
            for cid in self.cids:  # the rest (also songs uploaded before a console failed)
                flush(cid)
        finally:
            for f in ftps.values():
                f.close()
        done = store.load("ps3_written", {})
        for cid, entries in listed.items():
            for e in entries:
                old = done.get(str(e["ps3_id"]), {})
                done[str(e["ps3_id"])] = {"time": time.time(), "source": e.get("source"),
                                          "consoles": sorted(set(old.get("consoles", ["ps3"] if old else [])) | {cid})}
        store.save("ps3_written", done)
        for cid in self.cids:
            if listed[cid]:
                try:
                    consoles.scan_ps3(self.cfg, cid)
                except Exception:  # noqa: BLE001
                    pass
        if self.after:
            self.after()

    @staticmethod
    def _stor(ftp, remote: str, local: Path | None = None, data: bytes | None = None):
        def go(f):
            src = open(local, "rb") if local else io.BytesIO(data)
            with src:
                f.storbinary(f"STOR {remote}", src, blocksize=1 << 20)
        ftp.do(go)  # webMAN drops sockets now and then (421) -> RetryFtp reconnects

    def _upload(self, cid: str, ftp, e: dict, d: Path) -> None:
        cname, pid = consoles.name(self.cfg, cid), e["ps3_id"]

        def mkd(f):
            try:
                f.mkd(f"{EXPORT}/{pid}")
            except consoles.ftplib.error_perm:  # exists already
                pass
        self.current = f"{cname}: {e['artist']} – {e['title']} hochladen" +             (f" (baut: {self.building})" if self.building else "")
        ftp.do(mkd)

        def remote_size(path):
            try:
                return ftp.do(lambda f: f.size(path))  # SIZE needs no data connection (webMAN runs out of those)
            except consoles.ftplib.error_perm:
                return None
        skipped = 0
        files = [(f"{EXPORT}/{pid}/{n}", d / n) for n in ("melody_4.xml", "melody.xml", "preview.mp4", "video.mp4")]
        files.append((f"{EXPORT}/textures/page_{pid}.jpg", d / "cover.jpg"))
        for remote, local in files:
            # media already there in the same size (e.g. from a transfer that broke off before the song lists):
            # keep it; the small melody files are always sent (a GAP change can keep their size)
            if local.suffix in (".mp4", ".jpg") and remote_size(remote) == local.stat().st_size:
                skipped += 1
                continue
            self._stor(ftp, remote, local)
        self.log.append(f"{cname} {pid}: Dateien hochgeladen" + (f" ({skipped} schon vorhanden)" if skipped else ""))

    def _lists(self, cid: str, ftp, entries: list[dict]) -> None:
        cname = consoles.name(self.cfg, cid)
        self.current = f"{cname}: Songlisten aktualisieren"
        old = {n: ftp.do(lambda f, n=n: consoles.retr(f, f"{EXPORT}/{n}")).decode("utf-8") for n in LISTS}
        for n in LISTS:
            consoles.backup(cid, n, old[n].encode("utf-8"))
        new = merge_lists(old, entries)
        check_lists(old, new, entries)
        for n in LISTS:
            if new[n] != old[n]:
                self._stor(ftp, f"{EXPORT}/{n}", data=new[n].encode("utf-8"))
                if ftp.do(lambda f, n=n: consoles.retr(f, f"{EXPORT}/{n}")) != new[n].encode("utf-8"):
                    raise RuntimeError(f"{n}: Kontrolle nach dem Hochladen fehlgeschlagen")
        for e in entries:
            self.done.append(f"{cname}: {e['ps3_id']} {e['artist']} – {e['title']}")
        store.log("ps3-write", f"{len(entries)} Songs auf {cname} übertragen (SingStar neu starten)",
                  songs=[e["ps3_id"] for e in entries], console=cid)

    def state(self) -> dict:
        st = super().state()
        st["unit"] = "Schritte"
        return st
