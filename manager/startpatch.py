"""PS4: GoldHEN game patch against the error dialog at SingStar's start ("SU-41766-4" / "NW-31201-7", failing PSN
checks since the servers are gone). Patch bytes and FTP logic live in tools/no_online_check.py (same entry as the
command line tool); here only the per-console switch for the UI. Effective after a SingStar restart.
"""
import ftplib
import sys

import consoles
import library
import store

sys.path.insert(0, str(library.ROOT / "tools"))
import no_online_check  # noqa: E402


def status(f: ftplib.FTP) -> str | None:
    """"on" / "off" / "missing", None = not readable (e.g. GoldHEN patch folder missing)."""
    try:
        return no_online_check.status(f)
    except ftplib.all_errors:
        return None


def set_on(cfg: dict, cid: str, on: bool) -> list[str]:
    """Add/update the patch entry and switch it on or off. Returns notes for the UI (German)."""
    f = consoles.connect(consoles.get(cfg, cid), timeout=30)
    try:
        bak = []

        def save_backup(data: bytes) -> str | None:
            bak.append(consoles.backup(cid, "CUSA00033.xml", data))
            return bak[-1]

        no_online_check.apply(f, on, save_backup)
        st = status(f)
        try:
            ini = consoles.retr(f, "/data/GoldHEN/plugins.ini").decode("utf-8", "replace")
        except ftplib.all_errors:
            ini = ""
    finally:
        f.close()
    d = consoles.load(cid)
    if d is not None:
        d["nodialog"] = st
        consoles.save(cid, d)
    notes = [("Patch eingeschaltet" if on else "Patch ausgeschaltet") + " – wirksam nach Neustart von SingStar"]
    if bak and bak[0]:
        notes.append(f"Vorherige CUSA00033.xml gesichert ({bak[0]})")
    if on and "game_patch" not in ini:
        notes.append("ACHTUNG: game_patch.prx steht nicht in /data/GoldHEN/plugins.ini – Plugin fehlt")
    if on:
        notes.append("In GoldHEN muss der Plugin-Lader eingeschaltet sein; SingStar nach GoldHEN starten")
    store.log("startpatch", f"{consoles.name(cfg, cid)}: Fehlermeldung beim Start "
              + ("ausgeblendet (Patch an)" if on else "wieder eingeschaltet (Patch aus)"), console=cid)
    return notes
