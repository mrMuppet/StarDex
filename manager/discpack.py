"""PS4 songs without PKG: SingStar's disc-song loader reads download0/Pack0.psarc (GoldHEN game patch, see
docs/TECHNIK.md "Disc-Song-Lader"). Per PS4 with install mode "disc" the manager keeps a song list
(data/discpack_<console id>.json), builds one Pack0.psarc from our PS4 packages (tools/ps4_discpack.py) and uploads it.

Since 02.10. (evening) download0/Pack0.psarc is a symlink inside the download0 image (tools/ufs_symlink.py) to
/av_contents/video/ss/Pack0.psarc = FTP path /user/av_contents/video/ss/Pack0.psarc on the big user partition:
no 1 GiB limit (download0 is a fixed 1 GiB image) and uploads work while SingStar is closed. The loader only accepts
/download0/ paths, hence the link. A new pack counts after a SingStar restart. Songs in the pack use their PS4 id and
must not also be installed as PKG.
"""
import ftplib
import io
import re
import sys
import time
from pathlib import Path

import consoles
import library
import store

sys.path.insert(0, str(library.ROOT / "tools"))
import ps4_discpack  # noqa: E402

DL0 = "/mnt/sandbox/CUSA00033_000/download0"   # only while SingStar runs
EXT = "/user/av_contents/video/ss"              # link target, as the game sees it: /av_contents/video/ss
PACK = "Pack0.psarc"
WORK = library.ROOT / "build" / "discpack"

PATCH_XML = "/data/GoldHEN/patches/xml/CUSA00033.xml"
PATCH_SETTINGS = "/data/GoldHEN/patches/settings"
PATCH_NAME = ps4_discpack.PATCH_NAME  # same entry as the shareable release (tools/ps4_install.py)
PATCH_META = re.search(r"    <Metadata.*?</Metadata>\n", ps4_discpack.patch_xml(), re.S).group(0)
OLD_DATA_VARIANT = "Disc-Songs aus /data/singstar/Pack0.psarc"  # tested 02.10.: not loaded -> switch off


def patch_hash(name: str, title: str = "SingStar", app_ver: str = "01.10", elf: str = "eboot.bin") -> str:
    """GoldHEN game_patch switch file name: djb2 (h*33 ^ c, 64 bit) over Title+Name+AppVer+xml path+AppElf."""
    h = 5381
    for c in (title + name + app_ver + PATCH_XML + elf).encode("utf-8"):
        h = ((h * 33) ^ c) & 0xFFFFFFFFFFFFFFFF
    return f"0x{h:016x}"


def state(cid: str) -> dict:
    """{"songs": [ids wanted in the pack], "uploaded": [ids in the pack on the console], "time", "size"}"""
    return store.load(f"discpack_{cid}", {"songs": [], "uploaded": [], "time": None, "size": None})


def save_state(cid: str, st: dict) -> None:
    store.save(f"discpack_{cid}", st)


def pending(cid: str) -> bool:
    st = state(cid)
    return sorted(st["songs"]) != sorted(st["uploaded"])


def crf() -> int | None:
    v = store.load("settings", {}).get("disc_crf")
    return int(v) if v not in (None, "", "orig") else None


def reachable(f: ftplib.FTP) -> bool:
    """Upload target on the user partition reachable (GoldHEN FTP up; SingStar need not run)."""
    try:
        f.nlst("/user/av_contents/video")
        return True
    except ftplib.all_errors:
        return False


def link_state(f: ftplib.FTP) -> str | None:
    """"link" = download0/Pack0.psarc is the symlink (listed, but SIZE fails: target only exists in the game's view),
    "file" = a real Pack0.psarc in download0 (old setup, 1 GiB limit), "missing", None = SingStar not running."""
    try:
        names = [n.rstrip("/").split("/")[-1] for n in f.nlst(DL0)]
    except ftplib.all_errors:
        return None
    if PACK not in names:
        return "missing"
    try:
        f.size(f"{DL0}/{PACK}")
        return "file"
    except ftplib.all_errors:
        return "link"


def setup(cfg: dict, cid: str) -> list[str]:
    """Install the GoldHEN game patch (pointer to /download0/) and switch it on. Returns notes for the UI."""
    notes = []
    f = consoles.connect(consoles.get(cfg, cid), timeout=30)
    try:
        try:
            xml = consoles.retr(f, PATCH_XML).decode("utf-8")
        except ftplib.all_errors:
            xml = ""
        if PATCH_NAME not in xml:
            if xml.strip():
                consoles.backup(cid, "CUSA00033.xml", xml.encode("utf-8"))
                xml = xml.replace("</Patch>", PATCH_META + "</Patch>", 1)
            else:
                xml = ('<?xml version="1.0" encoding="utf-8"?>\n<Patch>\n    <TitleID>\n        <ID>CUSA00033</ID>\n'
                       "    </TitleID>\n" + PATCH_META + "</Patch>\n")
            f.storbinary(f"STOR {PATCH_XML}", io.BytesIO(xml.encode("utf-8")))
            notes.append("Patch eingetragen (CUSA00033.xml)")
        else:
            notes.append("Patch war schon eingetragen")
        f.storbinary(f"STOR {PATCH_SETTINGS}/{patch_hash(PATCH_NAME)}.txt", io.BytesIO(b"1\n"))
        notes.append("Patch eingeschaltet")
        # other variants of the same address must be off (both would patch the same instruction)
        for meta in re.findall(r'Name="([^"]+)"', xml):
            if meta != PATCH_NAME and ("Pack0.psarc" in meta):
                try:
                    f.storbinary(f"STOR {PATCH_SETTINGS}/{patch_hash(meta)}.txt", io.BytesIO(b"0\n"))
                    notes.append(f"ältere Variante ausgeschaltet: {meta}")
                except ftplib.all_errors:
                    pass
        try:
            ini = consoles.retr(f, "/data/GoldHEN/plugins.ini").decode("utf-8", "replace")
        except ftplib.all_errors:
            ini = ""
        if "game_patch" not in ini:
            notes.append("ACHTUNG: game_patch.prx steht nicht in /data/GoldHEN/plugins.ini – Plugin fehlt")
        notes.append("In GoldHEN muss der Plugin-Lader eingeschaltet sein (Meldung beim Start: „1 Patch Applied“)")
        link = link_state(f)
        if link == "link":
            notes.append(f"Verweis download0/{PACK} → {EXT}/{PACK} vorhanden")
        elif link is None:
            notes.append("Verweis in download0 nicht prüfbar (SingStar läuft nicht)")
        else:
            # the payload dl0link.elf creates the link on the PS4 (a real file there is renamed to .bak, never deleted)
            import ps4_install
            try:
                ps4_install.send_payload(consoles.get(cfg, cid)["host"])
                time.sleep(3)
                link = link_state(f)
            except (OSError, SystemExit) as e:
                notes.append(f"Payload dl0link.elf nicht gesendet: {e}")
            if link == "link":
                notes.append(f"Verweis download0/{PACK} → {EXT}/{PACK} angelegt (Payload dl0link.elf)")
            else:
                notes.append(f"ACHTUNG: kein Verweis in download0 ({'echte Datei' if link == 'file' else 'fehlt'}) – "
                             "BinLoader in GoldHEN einschalten (Port 9090) und erneut einrichten (siehe docs/SETUP.md)")
    finally:
        f.close()
    store.log("discpack", f"{consoles.name(cfg, cid)}: Disc-Lader eingerichtet – " + "; ".join(notes), console=cid)
    return notes


class DiscPackJob(consoles.Job):
    """Build Pack0.psarc from the console's song list and replace the one on the user partition (EXT)."""

    def __init__(self, cfg: dict, cid: str, songs_by_id: dict[int, dict]):
        st = state(cid)
        super().__init__(f"{consoles.name(cfg, cid)}: Disc-Pack mit {len(st['songs'])} Songs übertragen")
        self.cfg, self.cid, self.songs, self.st = cfg, cid, songs_by_id, st
        self.total = len(st["songs"]) + 2
        self.after = None

    def run(self):
        c = consoles.get(self.cfg, self.cid)
        f = consoles.connect(c, timeout=60)
        try:
            if not reachable(f):
                raise RuntimeError(f"{EXT} nicht erreichbar – läuft GoldHEN (FTP) auf der PS4?")
        finally:
            f.close()
        work = WORK / self.cid
        (work / "_songs").mkdir(parents=True, exist_ok=True)
        dirs, ids = [], []
        for sid in self.st["songs"]:
            if self.cancelled:
                return
            s = self.songs.get(sid)
            if not s or not s.get("pkg"):
                self.errors.append(f"{sid}: kein PS4-Paket am PC – übersprungen")
                self.done_bytes += 1
                continue
            self.current = f"{s['artist']} – {s['title']} vorbereiten"
            try:
                dirs.append(ps4_discpack.from_pkg(Path(s["pkg"]["file"]), work / "_songs"))
                ids.append(sid)
                self.log.append(f"{sid}: {s['artist']} – {s['title']}")
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"{s['artist']} – {s['title']}: {e}")
            self.done_bytes += 1
        out = work / PACK
        size = 0
        if dirs:
            self.current = "Pack0.psarc bauen" + (f" (Videos verkleinert, CRF {crf()})" if crf() else "")
            ps4_discpack.build(out, dirs, video_crf=crf())
            size = out.stat().st_size
            self.log.append(f"Pack0.psarc: {size / 2**20:.0f} MB, {len(dirs)} Songs")
        self.done_bytes += 1
        f = consoles.connect(c, timeout=120)
        try:
            try:
                f.mkd(EXT)
            except ftplib.all_errors:
                pass  # exists
            names = [n.rstrip("/").split("/")[-1] for n in f.nlst(EXT)]
            for n in names:  # leftovers of an aborted transfer
                if n in (PACK + ".new", PACK + ".old"):
                    f.delete(f"{EXT}/{n}")
            old = PACK in names
            if size:
                self.current = "Pack0.psarc hochladen"
                with open(out, "rb") as fh:
                    f.storbinary(f"STOR {EXT}/{PACK}.new", fh, blocksize=1 << 20)
                if f.size(f"{EXT}/{PACK}.new") != size:
                    raise RuntimeError("Größe nach dem Hochladen stimmt nicht")
                if old:
                    f.rename(f"{EXT}/{PACK}", f"{EXT}/{PACK}.old")
                f.rename(f"{EXT}/{PACK}.new", f"{EXT}/{PACK}")
                if old:
                    f.delete(f"{EXT}/{PACK}.old")
            elif old:
                f.delete(f"{EXT}/{PACK}")
        finally:
            f.close()
        self.done_bytes += 1
        st = state(self.cid)
        st.update(uploaded=ids, time=time.time(), size=size)
        save_state(self.cid, st)
        self.done.append(f"{len(ids)} Songs im Disc-Pack ({size / 2**20:.0f} MB) – SingStar neu starten")
        store.log("discpack", f"{consoles.name(self.cfg, self.cid)}: Disc-Pack mit {len(ids)} Songs übertragen "
                              f"({size / 2**20:.0f} MB) – SingStar neu starten", songs=ids, console=self.cid)
        if self.after:
            self.after()

    def state(self) -> dict:
        st = super().state()
        st["unit"] = "Schritte"
        return st
