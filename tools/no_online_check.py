"""GoldHEN game patch: no "SU-41766-4" / "NW-31201-7" error dialog when SingStar starts.

With the servers gone, SingStar's PSN checks at startup fail (SU-41766-4 = outdated system software, NW-31201-7 = no
network) and the error code is queued for the system error dialog (queue: enqueue 0x4d7130, called from 0x43b035,
0x4f4048, 0x993eef). Zeroing the sceNpCheckNpAvailability result (poll 0x6bcb50) was not enough (tested 02.10.).
The patch works where the queue is drained (0x4d71d0): sceErrorDialogInitialize (call at 0x4d7209) -> nop,
sceErrorDialogOpen (call at 0x4d7243) -> mov eax, 1 ("open failed") -> the entry is dropped, no dialog.
Side effect: SingStar shows no system error dialogs at all (they are all PSN/network related offline).

  python tools/no_online_check.py [HOST]          add the patch to CUSA00033.xml (backup first) and switch it on
  python tools/no_online_check.py [HOST] --off    switch it off
  python tools/no_online_check.py [HOST] --status on / off / missing
Effective after a SingStar restart (GoldHEN started before SingStar).
"""
import ftplib
import io
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import local_config  # noqa: E402
from ps4_install import PATCH_SETTINGS, PATCH_XML, patch_hash, retr  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
NAME = "No online check error at startup"
LINES = ((0x4D7209, "0f1f440000"),  # was e8 22 b4 50 00 (call sceErrorDialogInitialize)
         (0x4D7243, "b801000000"))  # was e8 f8 b3 50 00 (call sceErrorDialogOpen)

META = f"""    <Metadata Title="SingStar"
              Name="{NAME}"
              Note="Skips the SU-41766-4 / NW-31201-7 system error dialog at startup (PSN checks, servers offline)"
              Author="PS4Singstar"
              PatchVer="1.1"
              AppVer="01.10"
              AppElf="eboot.bin">
        <PatchList>
""" + "".join(f'            <Line Type="bytes" Address="0x{a:08x}" Value="{v}"/>\n' for a, v in LINES) + """        </PatchList>
    </Metadata>
"""


def status(f: ftplib.FTP) -> str:
    """"on" / "off" (entry in CUSA00033.xml, switch file 1/0) or "missing" (no entry)."""
    xml = (retr(f, PATCH_XML) or b"").decode("utf-8", "replace")
    if f'Name="{NAME}"' not in xml:
        return "missing"
    return "on" if (retr(f, f"{PATCH_SETTINGS}/{patch_hash(NAME)}.txt") or b"").strip() == b"1" else "off"


def apply(f: ftplib.FTP, on: bool = True, save_backup=None) -> list[str]:
    """Add/update the entry (on) and set the switch. save_backup(xml_bytes) -> path is called before an existing
    CUSA00033.xml gets a new entry. Returns notes (English)."""
    notes = []
    if on:
        xml = (retr(f, PATCH_XML) or b"").decode("utf-8", "replace")
        old = re.search(rf'    <Metadata[^>]*Name="{re.escape(NAME)}".*?</Metadata>\n', xml, re.S)
        if old and old.group(0) == META:
            notes.append("patch already in CUSA00033.xml")
        else:
            if old:
                xml = xml.replace(old.group(0), META)
                notes.append("patch updated in CUSA00033.xml")
            elif xml.strip():
                bak = save_backup(xml.encode("utf-8")) if save_backup else None
                xml = xml.replace("</Patch>", META + "</Patch>", 1)
                notes.append("patch added to CUSA00033.xml" + (f" (old file saved: {bak})" if bak else ""))
            else:
                xml = ('<?xml version="1.0" encoding="utf-8"?>\n<Patch>\n    <TitleID>\n        <ID>CUSA00033</ID>\n'
                       '    </TitleID>\n' + META + '</Patch>\n')
                notes.append("CUSA00033.xml written")
            f.storbinary(f"STOR {PATCH_XML}", io.BytesIO(xml.encode("utf-8")))
    f.storbinary(f"STOR {PATCH_SETTINGS}/{patch_hash(NAME)}.txt", io.BytesIO(b"1" if on else b"0"))
    notes.append(f"switch {patch_hash(NAME)}.txt = {int(on)} (effective after SingStar restart)")
    return notes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    host = args[0] if args else local_config.host("ps4")
    f = ftplib.FTP()
    f.connect(host, 2121, timeout=15)
    f.login()
    f.voidcmd("TYPE I")
    if "--status" in sys.argv:
        print(status(f))
    else:
        def save_backup(data: bytes) -> Path:
            bak = HERE / "backup" / f"CUSA00033_{host}_{time.strftime('%Y%m%d_%H%M%S')}.xml"
            bak.parent.mkdir(exist_ok=True)
            bak.write_bytes(data)
            return bak
        print("\n".join(apply(f, "--off" not in sys.argv, save_backup)))
    f.quit()


if __name__ == "__main__":
    main()
