"""PlayStation archive (PSARC 1.4, zlib) - read, extract and create.

  python psarc.py list ARCHIVE
  python psarc.py extract ARCHIVE OUTDIR
  python psarc.py create ARCHIVE SRCDIR [--prefix filesystem/export]   (files under SRCDIR, paths relative)

Layout (big endian), as in SingStar PS4's app0/Data/ORBIS/pitchdisplay.psarc:
  header 32 B: "PSAR", 1, 4, "zlib", toc_length (header+toc+block table), toc entry size 30, entry count
               (incl. manifest), block size 65536, flags 1 (relative paths, ignore case)
  toc entry 30 B: MD5 of the UPPER-CASE path (manifest: 16 zero bytes), first block index u32,
               size u40, offset u40
  block table: u16 per block = stored size; 0 = full 65536-byte block stored raw; stored == size -> raw,
               otherwise zlib. Entry 0 is the manifest: the paths, newline separated, in toc order.
Media (mp4/jpg/...) is stored raw, text is compressed when that saves space.
"""
import hashlib
import struct
import sys
import zlib
from pathlib import Path

BLOCK = 65536
RAW_EXT = {".mp4", ".jpg", ".jpeg", ".png", ".gnf", ".at9", ".mp3", ".m4a", ".psarc", ".pkd"}


def read_toc(f):
    head = f.read(32)
    magic, maj, mino, comp, toclen, tes, cnt, bs, flags = struct.unpack(">4sHH4sIIIII", head)
    if magic != b"PSAR":
        raise ValueError("kein PSARC")
    raw = f.read(toclen - 32)
    entries = []
    for i in range(cnt):
        e = raw[i * tes:(i + 1) * tes]
        entries.append({"md5": e[:16], "block": struct.unpack(">I", e[16:20])[0],
                        "size": int.from_bytes(e[20:25], "big"), "offset": int.from_bytes(e[25:30], "big")})
    nb = {65536: 2, 16777216: 3}.get(bs, 4)
    tab_raw = raw[cnt * tes:]
    table = [int.from_bytes(tab_raw[i:i + nb], "big") for i in range(0, len(tab_raw) - nb + 1, nb)]
    return {"version": (maj, mino), "comp": comp, "block": bs, "flags": flags, "entries": entries, "table": table}


def read_entry(f, toc, e) -> bytes:
    out, left, bi, pos = bytearray(), e["size"], e["block"], e["offset"]
    bs = toc["block"]
    while left > 0:
        stored = toc["table"][bi] or bs
        f.seek(pos)
        data = f.read(stored)
        want = min(bs, left)
        out += data if stored == want else zlib.decompress(data)
        left -= want
        pos += stored
        bi += 1
    return bytes(out)


def entries(path: str):
    with open(path, "rb") as f:
        toc = read_toc(f)
        names = read_entry(f, toc, toc["entries"][0]).decode("utf-8").split("\n")
        for name, e in zip(names, toc["entries"][1:]):
            yield name, e, toc


def extract(path: str, out: str) -> None:
    with open(path, "rb") as f:
        toc = read_toc(f)
        names = read_entry(f, toc, toc["entries"][0]).decode("utf-8").split("\n")
        for name, e in zip(names, toc["entries"][1:]):
            dst = Path(out) / name.lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(read_entry(f, toc, e))


def _blocks(data_iter, compress: bool):
    """yield (stored bytes, table value) per 64 KiB block"""
    for chunk in data_iter:
        if compress:
            z = zlib.compress(chunk, 9)
            if len(z) < len(chunk):
                yield z, len(z)
                continue
        yield chunk, (0 if len(chunk) == BLOCK else len(chunk))


def _chunks(path: Path):
    with open(path, "rb") as fh:
        while True:
            c = fh.read(BLOCK)
            if not c:
                return
            yield c


def create(archive: str, files: list[tuple[str, Path]], flags: int = 1, absolute: bool = False,
           compress: bool = True) -> None:
    """files: [(path inside the archive, local file)] - written in this order.
    flags: 1 = relative + ignore case (Sony default), 0 = case sensitive, 2 = absolute paths ("/" + path).
    MD5 per path: upper case path if ignore case (flags & 1), else the path as stored."""
    names = [("/" if absolute else "") + n.replace("\\", "/").lstrip("/") for n, _ in files]
    manifest = "\n".join(names).encode("utf-8")
    # block counts are needed for the header: compression is decided per block, but the COUNT of blocks only
    # depends on the sizes
    sizes = [len(manifest)] + [p.stat().st_size for _, p in files]
    nblocks = [max(1, -(-s // BLOCK)) for s in sizes]
    cnt = len(sizes)
    toclen = 32 + cnt * 30 + sum(nblocks) * 2
    tmp = Path(str(archive) + ".data")
    table, offsets, first = [], [], []
    with open(tmp, "wb") as data:
        pos = toclen
        sources = [(iter([manifest[i:i + BLOCK] for i in range(0, max(1, len(manifest)), BLOCK)]), compress)]
        sources += [(_chunks(p), compress and p.suffix.lower() not in RAW_EXT) for _, p in files]
        for (it, comp), n in zip(sources, nblocks):
            first.append(len(table))
            offsets.append(pos)
            k = 0
            for stored, val in _blocks(it, comp):
                data.write(stored)
                table.append(val)
                pos += len(stored)
                k += 1
            if k == 0:  # empty file: one empty block
                table.append(0 if False else 0)
                k = 1
            assert k == n, (k, n)
    head = struct.pack(">4sHH4sIIIII", b"PSAR", 1, 4, b"zlib", toclen, 30, cnt, BLOCK, flags)
    toc = bytearray()
    for i, (size, off) in enumerate(zip(sizes, offsets)):
        md5 = b"\0" * 16 if i == 0 else hashlib.md5(names[i - 1].upper().encode("utf-8")).digest()
        toc += md5 + struct.pack(">I", first[i]) + size.to_bytes(5, "big") + off.to_bytes(5, "big")
    with open(archive, "wb") as out:
        out.write(head + toc + b"".join(v.to_bytes(2, "big") for v in table))
        with open(tmp, "rb") as data:
            while True:
                c = data.read(1 << 22)
                if not c:
                    break
                out.write(c)
    tmp.unlink()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "list":
        for name, e, _ in entries(sys.argv[2]):
            print(f"{e['size']:>12}  {name}")
    elif cmd == "extract":
        extract(sys.argv[2], sys.argv[3])
    elif cmd == "create":
        src = Path(sys.argv[3])
        prefix = sys.argv[sys.argv.index("--prefix") + 1].strip("/") + "/" if "--prefix" in sys.argv else ""
        files = [(prefix + p.relative_to(src).as_posix(), p) for p in sorted(src.rglob("*")) if p.is_file()]
        create(sys.argv[2], files)
        print(f"{sys.argv[2]}: {len(files)} Dateien")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
