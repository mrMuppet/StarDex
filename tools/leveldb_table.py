"""Dump all entries of a LevelDB table file (*.ldb / *.sst), snappy blocks included.

  python leveldb_table.py 000068.ldb [KEY_PREFIX]
"""
import struct
import sys

from leveldb_log import varint


def snappy_decompress(src: bytes) -> bytes:
    n, i = varint(src, 0)
    out = bytearray()
    while i < len(src):
        tag = src[i]; i += 1
        kind = tag & 3
        if kind == 0:  # literal
            ln = tag >> 2
            if ln >= 60:
                nb = ln - 59
                ln = int.from_bytes(src[i:i + nb], "little"); i += nb
            ln += 1
            out += src[i:i + ln]; i += ln
            continue
        if kind == 1:
            ln = ((tag >> 2) & 7) + 4
            off = ((tag >> 5) << 8) | src[i]; i += 1
        elif kind == 2:
            ln = (tag >> 2) + 1
            off = int.from_bytes(src[i:i + 2], "little"); i += 2
        else:
            ln = (tag >> 2) + 1
            off = int.from_bytes(src[i:i + 4], "little"); i += 4
        for _ in range(ln):
            out.append(out[-off])
    assert len(out) == n
    return bytes(out)


def read_block(data: bytes, off: int, size: int) -> bytes:
    raw, ctype = data[off:off + size], data[off + size]
    return snappy_decompress(raw) if ctype == 1 else raw


def block_entries(block: bytes):
    nrest, = struct.unpack_from("<I", block, len(block) - 4)
    end = len(block) - 4 - 4 * nrest
    i, key = 0, b""
    while i < end:
        shared, i = varint(block, i)
        nonshared, i = varint(block, i)
        vlen, i = varint(block, i)
        key = key[:shared] + block[i:i + nonshared]; i += nonshared
        yield key, block[i:i + vlen]; i += vlen


def entries(path: str):
    data = open(path, "rb").read()
    footer = data[-48:]
    _mi_off, i = varint(footer, 0)
    _mi_size, i = varint(footer, i)
    idx_off, i = varint(footer, i)
    idx_size, i = varint(footer, i)
    for _k, handle in block_entries(read_block(data, idx_off, idx_size)):
        off, j = varint(handle, 0)
        size, j = varint(handle, j)
        for ikey, val in block_entries(read_block(data, off, size)):
            seq_type, = struct.unpack("<Q", ikey[-8:])
            yield ikey[:-8], seq_type >> 8, seq_type & 0xff, val


if __name__ == "__main__":
    prefix = sys.argv[2].encode() if len(sys.argv) > 2 else b""
    for key, seq, typ, val in entries(sys.argv[1]):
        if key.startswith(prefix):
            print(f"{seq:6} {'PUT' if typ else 'DEL'} {key.decode('latin1')!r} {val[:200]!r}")
