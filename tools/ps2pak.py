"""Reader for SingStar PS2 PAK archives (PACK_EE.PAK, PAK_IOP0/1.PAK, PAK_IOPM.PAK; header "SceeWhPC"/"SceeWhPk").

Layout (reverse-engineered 28.09. from SingStar Party, little endian):
  0x00  magic "SceeWh.." + build date "[dd/mm/yy,hh:mm:ss]", NUL
  0x1c  u32 directory size, 0x20 u32 entry count, 0x24 base path (NUL-terminated), then tables and the
        extension list ("tx2", "txt", "lua", "xml", "mih", "idx", ... NUL separated, 1-based)
  entries from 0x198, each:
        u24 start sector (2048 bytes), u8 prefix length (chars shared with the previous path),
        u8 len(suffix)+1, u16 unknown, u32 size, [u32 checksum: PACK_EE only], suffix, u8 extension index
  file data: offset = sector * 2048

  python ps2pak.py PAKFILE [filter]     list entries
"""
import re
import struct
import sys
from pathlib import Path

SECTOR = 2048


class Pak:
    def __init__(self, path: Path):
        self.path = Path(path)
        with open(self.path, "rb") as f:
            head = f.read(0x40)
            dir_size, count = struct.unpack_from("<II", head, 0x1c)
            f.seek(0)
            raw = f.read(0x198 + dir_size + 0x100)
        # "SceeWhPC" (PACK_EE) records carry a u32 checksum, "SceeWhPk" (IOP paks) do not
        self.rec = 15 if raw[6:8] == b"PC" else 11
        self.exts = [e.decode() for e in raw[0x114:0x198].split(bytes(1)) if e]
        self.entries = self._parse(raw, count)

    def _parse(self, raw: bytes, count: int) -> list[dict]:
        pos, out, prev = 0x198, [], b""
        for _ in range(count):
            sector = int.from_bytes(raw[pos:pos + 3], "little")
            pre, sl = raw[pos + 3], raw[pos + 4]
            unk, size = struct.unpack_from("<HI", raw, pos + 5)
            suffix = raw[pos + self.rec:pos + self.rec + sl - 1]
            ext = raw[pos + self.rec + sl - 1] - 1
            name = prev[:pre] + suffix
            prev = name
            out.append({"name": name.decode("latin-1") + (f".{self.exts[ext]}" if 0 <= ext < len(self.exts) else ""),
                        "offset": sector * SECTOR, "size": size, "unk": unk})
            pos += self.rec + sl
        return out

    def find(self, pattern: str) -> list[dict]:
        return [e for e in self.entries if re.search(pattern, e["name"], re.I)]

    def read(self, entry: dict) -> bytes:
        with open(self.path, "rb") as f:
            f.seek(entry["offset"])
            return f.read(entry["size"])


if __name__ == "__main__":
    p = Pak(Path(sys.argv[1]))
    print(f"{len(p.entries)} entries, exts {p.exts}")
    for e in p.entries:
        if len(sys.argv) < 3 or re.search(sys.argv[2], e["name"], re.I):
            print(f"{e['offset']:#012x} {e['size']:>11}  {e['name']}".encode("ascii", "replace").decode())
