"""Minimal UFS2 editor for SingStar's download0.dat (plain FreeBSD UFS2 image, little endian).

Turns an existing, EMPTY regular file in the image root into a fast symlink (target stored in the inode,
no block allocation). Used to point /download0/Pack0.psarc to the big user partition, e.g.
/av_contents/video/ss/Pack0.psarc, because the game's Fios loader only accepts /download0/ paths
(see docs/TECHNIK.md).

  python ufs_symlink.py IMAGE info                      superblock + root directory
  python ufs_symlink.py IMAGE link NAME TARGET [--write]  make NAME (empty file) a symlink to TARGET
"""
import struct
import sys

SB_OFF = 0x10000
UFS2_MAGIC = 0x19540119
DINODE = 256
ROOT_INO = 2
IFMT, IFREG, IFLNK = 0o170000, 0o100000, 0o120000
DT_REG, DT_LNK = 8, 10


class Ufs2:
    def __init__(self, path, writable=False):
        self.f = open(path, "r+b" if writable else "rb")
        sb = self.read(SB_OFF, 0x600)
        if struct.unpack_from("<I", sb, 0x55C)[0] != UFS2_MAGIC:
            raise ValueError("kein UFS2-Superblock bei 0x10000")
        g = lambda off: struct.unpack_from("<i", sb, off)[0]
        self.iblkno, self.ncg = g(0x10), g(0x2C)
        self.bsize, self.fsize = g(0x30), g(0x34)
        self.ipg, self.fpg = g(0xB8), g(0xBC)
        self.maxsymlinklen = g(0x528)

    def read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def write(self, off, data):
        self.f.seek(off)
        self.f.write(data)

    def inode_off(self, ino):
        cg, idx = divmod(ino, self.ipg)
        return (cg * self.fpg + self.iblkno) * self.fsize + idx * DINODE

    def inode(self, ino):
        d = self.read(self.inode_off(ino), DINODE)
        mode, nlink = struct.unpack_from("<Hh", d, 0)
        size, blocks = struct.unpack_from("<QQ", d, 0x10)
        db = struct.unpack_from("<12q", d, 0x70)
        ib = struct.unpack_from("<3q", d, 0xD0)
        return {"mode": mode, "nlink": nlink, "size": size, "blocks": blocks, "db": db, "ib": ib, "raw": d}

    def dir_entries(self, ino):
        """(name, ino, type, byte offset of the entry in the image) for a directory (direct blocks only)."""
        di = self.inode(ino)
        out, left = [], di["size"]
        for blk in di["db"]:
            if left <= 0 or blk == 0:
                break
            base = blk * self.fsize
            data = self.read(base, min(self.bsize, left))
            pos = 0
            while pos < len(data):
                d_ino, reclen, dtype, namlen = struct.unpack_from("<IHBB", data, pos)
                if reclen == 0:
                    break
                if d_ino:
                    out.append((data[pos + 8:pos + 8 + namlen].decode("utf-8", "replace"), d_ino, dtype, base + pos))
                pos += reclen
            left -= len(data)
        return out


def info(fs):
    print(f"bsize={fs.bsize} fsize={fs.fsize} ncg={fs.ncg} ipg={fs.ipg} fpg={fs.fpg} iblkno={fs.iblkno} "
          f"maxsymlinklen={fs.maxsymlinklen} Größe ca. {fs.ncg * fs.fpg * fs.fsize / 2**20:.0f} MiB")
    for name, ino, dtype, _ in fs.dir_entries(ROOT_INO):
        di = fs.inode(ino)
        print(f"  {name:20} ino={ino:<6} type={dtype:<2} mode={oct(di['mode'])} size={di['size']} blocks={di['blocks']}")


def make_link(fs, name, target, write):
    t = target.encode()
    if not 0 < len(t) < fs.maxsymlinklen:
        sys.exit(f"Ziel zu lang für einen schnellen Symlink ({len(t)} ≥ {fs.maxsymlinklen})")
    ent = next((e for e in fs.dir_entries(ROOT_INO) if e[0] == name), None)
    if not ent:
        sys.exit(f"{name} nicht im Wurzelverzeichnis")
    _, ino, dtype, ent_off = ent
    di = fs.inode(ino)
    if not target.startswith("/") or ":" in target:
        sys.exit(f"Ziel muss ein PS4-Pfad sein (Git Bash: MSYS_NO_PATHCONV=1 setzen): {target}")
    # erlaubt: leere reguläre Datei oder schon ein schneller Symlink (Ziel ändern); nie Dateien mit Blöcken
    fast_link = di["mode"] & IFMT == IFLNK and di["blocks"] == 0 and di["size"] < fs.maxsymlinklen
    empty_file = di["mode"] & IFMT == IFREG and di["size"] == 0 and di["blocks"] == 0 \
        and not any(di["db"]) and not any(di["ib"])
    if not (fast_link or empty_file):
        sys.exit(f"{name} ist keine leere reguläre Datei (size={di['size']}, blocks={di['blocks']}) – erst leeren")
    raw = bytearray(di["raw"])
    struct.pack_into("<H", raw, 0, IFLNK | 0o777)
    struct.pack_into("<Q", raw, 0x10, len(t))
    raw[0x70:0x70 + 120] = t.ljust(120, b"\0")
    print(f"{name}: ino {ino} → Symlink auf {target} (Eintrag bei {ent_off:#x}, Inode bei {fs.inode_off(ino):#x})")
    if write:
        fs.write(fs.inode_off(ino), bytes(raw))
        fs.write(ent_off + 6, bytes([DT_LNK]))
        fs.f.flush()
        print("geschrieben")
    else:
        print("Probelauf (--write zum Schreiben)")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    img, cmd = sys.argv[1], sys.argv[2]
    write = "--write" in sys.argv
    fs = Ufs2(img, writable=write)
    if cmd == "info":
        info(fs)
    elif cmd == "link":
        make_link(fs, sys.argv[3], sys.argv[4], write)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
