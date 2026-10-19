"""Copy songs that exist only on a console to the PC ("Konsolen-Übernahmen").

PS3: Export/<id>/ (melody, video, preview), the song's <SONG> and <ACT> entries and its cover (cut out of the texture
     page) -> <console_imports>/PS3/export/ in the Toolbox/disc layout (songs_4_0.xml, acts_4_0.xml, covers.xml,
     textures/page_<id>.jpg) -> the library treats it like an imported PS3 disc (source "ps3disc").
PS4: /user/addcont/CUSA00033/<LABEL>/ac.pkg -> <console_imports>/PS4/pkgs/<content id>.pkg, unpacked with PkgTool to
     PS4/packs/<LABEL>/ (source "ps4pkg"). Only fake PKGs can be unpacked; official Sony packs are encrypted and are
     deleted again ("verschlüsselt").
"""
import html
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

import consoles
import library
import store

HDR = '<?xml version="1.0" encoding="UTF-8"?>\n'
NS = 'xmlns="http://www.singstargame.com" xmlns:ss="http://www.singstargame.com"'
EMPTY = {"songs_4_0.xml": f"{HDR}<SONG_SET {NS}>\n</SONG_SET>\n",
         "acts_4_0.xml": f"{HDR}<ACT_SET {NS}>\n</ACT_SET>\n",
         "covers.xml": f"{HDR}<TPAGE_BIT_SET {NS}>\n</TPAGE_BIT_SET>\n"}
PKGTOOL = library.ROOT / "tools" / "PkgTool" / "PkgTool.Core.dll"


def root(cfg: dict) -> Path:
    return library.path(cfg.get("console_imports") or "imports/konsolen")


def _dl(f, remote: str, local: Path, **kw) -> None:
    with open(local, "wb") as fh:
        f.retrbinary(f"RETR {remote}", fh.write, **kw)


def pkg_head(f, remote: str, n: int = 16) -> bytes:
    """First bytes of a remote file without downloading it (connection closed early, server reply ignored)."""
    conn = f.transfercmd(f"RETR {remote}")
    data = b""
    try:
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        conn.close()
    try:
        f.getresp()
    except Exception:  # noqa: BLE001  426/451 after the early close is expected
        pass
    return data


def is_retail(head: bytes) -> bool:
    """PKG header offset 4: 0x80000000 set = finalized retail package (encrypted, e.g. official Sony DLC);
    fake PKGs (ours, PkgTool) have 0x00000001."""
    return len(head) >= 8 and head[:4] == b"CNT" and bool(head[4] & 0x80)


def _put(text: str, closing: str, pattern: str, block: str) -> str:
    text = re.sub(pattern, "", text, flags=re.S)
    return text.replace(closing, block + closing, 1)


class PullPS3Job(consoles.Job):
    def __init__(self, cfg: dict, ids: list[int], cid: str = "ps3"):
        super().__init__(f"{len(ids)} Songs von {consoles.name(cfg, cid)} auf den PC holen")
        self.cfg, self.ids, self.cid = cfg, ids, cid
        self.total = len(ids)
        self.after = None

    def run(self):
        from PIL import Image
        exp = root(self.cfg) / "PS3" / "export"
        (exp / "textures").mkdir(parents=True, exist_ok=True)
        lists = {n: (exp / n).read_text("utf-8") if (exp / n).exists() else EMPTY[n] for n in EMPTY}
        E = consoles.PS3_EXPORT
        ftp = consoles.RetryFtp(consoles.get(self.cfg, self.cid), timeout=60)
        try:
            remote = {n: ftp.do(lambda f, n=n: consoles.retr(f, f"{E}/{n}")).decode("utf-8", "replace")
                      for n in EMPTY}
            for sid in self.ids:
                if self.cancelled:
                    break
                try:
                    song = re.search(r'<SONG ID="%d".*?</SONG>' % sid, remote["songs_4_0.xml"], re.S)
                    if not song:
                        raise RuntimeError("nicht in der Songliste der PS3")
                    artist = html.unescape(re.search(r"<PERFORMANCE_NAME>(.*?)<", song.group(0), re.S).group(1))
                    self.current = f"{sid} {artist}"
                    (exp / str(sid)).mkdir(exist_ok=True)
                    files = ftp.do(lambda f: [n.rstrip("/").split("/")[-1] for n in f.nlst(f"{E}/{sid}")])
                    for n in files:
                        if n.endswith((".xml", ".mp4")):
                            ftp.do(lambda f, n=n: _dl(f, f"{E}/{sid}/{n}", exp / str(sid) / n))
                    if not (exp / str(sid) / "video.mp4").exists():
                        raise RuntimeError("video.mp4 fehlt auf der PS3")
                    cov = re.search(r'<TPAGE_BIT NAME="cover_%d"([^>]*)/>' % sid, remote["covers.xml"])
                    if cov:
                        a = dict(re.findall(r'(\w+)="([^"]*)"', cov.group(1)))
                        page = ftp.do(lambda f: consoles.retr(f, f"{E}/textures/{a['TEXTURE']}.jpg"))
                        u, v, w, h = (int(float(a[k])) for k in ("U", "V", "WIDTH", "HEIGHT"))
                        Image.open(io.BytesIO(page)).convert("RGB").crop((u, v, u + w, v + h)) \
                            .resize((256, 256), Image.LANCZOS).save(exp / "textures" / f"page_{sid}.jpg", quality=92)
                        lists["covers.xml"] = _put(lists["covers.xml"], "</TPAGE_BIT_SET>",
                                                   r'[ \t]*<TPAGE_BIT NAME="cover_%d"[^>]*/>\s*' % sid,
                                                   f'  <TPAGE_BIT NAME="cover_{sid}" TEXTURE="page_{sid}" U="0" V="0" '
                                                   f'WIDTH="256" HEIGHT="256"/>\n')
                    lists["songs_4_0.xml"] = _put(lists["songs_4_0.xml"], "</SONG_SET>",
                                                  r'[ \t]*<SONG ID="%d"[^>]*>.*?</SONG>\s*' % sid,
                                                  "  " + song.group(0).replace("\r\n", "\n") + "\n")
                    aid = re.search(r'<PERFORMED_BY ID="(\d+)"', song.group(0))
                    if aid and f'<ACT ID="{aid.group(1)}"' not in lists["acts_4_0.xml"]:
                        act = re.search(r'<ACT ID="%s">.*?</ACT>' % aid.group(1), remote["acts_4_0.xml"], re.S)
                        key = re.search(r"<PERFORMANCE_NAME_KEY>(.*?)<", song.group(0))
                        block = act.group(0).replace("\r\n", "\n") if act else (
                            f'<ACT ID="{aid.group(1)}">\n    <NAME>{html.escape(artist)}</NAME>\n'
                            f'    <NAME_KEY>{key.group(1) if key else artist.upper()}</NAME_KEY>\n  </ACT>')
                        lists["acts_4_0.xml"] = lists["acts_4_0.xml"].replace("</ACT_SET>", f"  {block}\n</ACT_SET>", 1)
                    self.done.append(f"{sid} {artist}")
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"{sid}: {e}")
                self.done_bytes += 1
        finally:
            ftp.close()
        for n, t in lists.items():
            (exp / n).write_text(t, "utf-8", newline="\n")
        info = exp.parent / "disc.json"
        if not info.exists():
            info.write_text(json.dumps({"name": "PS3", "edition": "von der PS3 übernommen"}, ensure_ascii=False), "utf-8")
        store.log("pull", f"{len(self.done)} Songs von {consoles.name(self.cfg, self.cid)} auf den PC geholt",
                  songs=self.ids[:500], console=self.cid)
        if self.after:
            self.after()


class PullPS4Job(consoles.Job):
    def __init__(self, cfg: dict, labels: list[str], cid: str = "ps4"):
        super().__init__(f"{len(labels)} Pakete von {consoles.name(cfg, cid)} auf den PC holen")
        self.cfg, self.labels, self.cid = cfg, labels, cid
        self.total = len(labels)
        self.after = None

    def run(self):
        base = root(self.cfg) / "PS4"
        (base / "pkgs").mkdir(parents=True, exist_ok=True)
        (base / "packs").mkdir(parents=True, exist_ok=True)
        ftp = consoles.RetryFtp(consoles.get(self.cfg, self.cid), timeout=60)
        try:
            for label in self.labels:
                if self.cancelled:
                    break
                self.current = label
                tmp = base / "pkgs" / f"{label}.download"
                try:
                    head = ftp.do(lambda f: pkg_head(f, f"{consoles.PS4_ADDCONT}/{label}/ac.pkg"))
                    if is_retail(head):
                        raise RuntimeError("offizielles Sony-Paket (verschlüsselt) – lässt sich nicht übernehmen")
                    ftp.do(lambda f: _dl(f, f"{consoles.PS4_ADDCONT}/{label}/ac.pkg", tmp, blocksize=1 << 20))
                    head = tmp.open("rb").read(0x80)
                    cid = head[0x40:0x64].decode("ascii", "replace").strip("\x00") or f"UNKNOWN-{label}"
                    out = base / "packs" / label
                    shutil.rmtree(out, ignore_errors=True)
                    p = subprocess.run(["dotnet", str(PKGTOOL), "pkg_extract", str(tmp), str(out)],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace")
                    if p.returncode or not list(out.glob("uroot/Prod_Sku_*/songs_*.xml")):
                        shutil.rmtree(out, ignore_errors=True)
                        tmp.unlink(missing_ok=True)
                        raise RuntimeError("verschlüsselt (offizielles Sony-Paket) – lässt sich nicht übernehmen")
                    tmp.replace(base / "pkgs" / f"{cid}.pkg")
                    self.done.append(f"{label} ({cid})")
                except Exception as e:  # noqa: BLE001
                    tmp.unlink(missing_ok=True)
                    self.errors.append(f"{label}: {e}")
                self.done_bytes += 1
        finally:
            ftp.close()
        store.log("pull", f"{len(self.done)} Pakete von {consoles.name(self.cfg, self.cid)} auf den PC geholt"
                  + (f", {len(self.errors)} nicht möglich" if self.errors else ""), labels=self.labels[:500])
        if self.after:
            self.after()
