"""SingStar PS4 melody cache (.chc) pack/unpack.

Layout (little endian), verified against Prod_Sku_130U9X/melodies_1.chc:
  u32 version      = 1
  u32 song_id      (e.g. 39237)
  u32 data_offset  = 20
  u32 packed_size  (zlib stream length)
  u32 raw_size     (length of melody_1.xml)
  zlib stream of melody_1.xml

Usage:
  python chc.py unpack melodies_1.chc [out.xml]
  python chc.py pack melody_1.xml SONG_ID melodies_1.chc
"""
import struct
import sys
import zlib

HEADER = struct.Struct("<5I")


def unpack(data: bytes) -> tuple[int, bytes]:
    version, song_id, offset, packed, raw = HEADER.unpack_from(data)
    if version != 1:
        raise ValueError(f"unexpected version {version}")
    xml = zlib.decompress(data[offset:offset + packed])
    if len(xml) != raw:
        raise ValueError(f"size mismatch: header {raw}, got {len(xml)}")
    return song_id, xml


def pack(xml: bytes, song_id: int) -> bytes:
    z = zlib.compress(xml, 9)
    return HEADER.pack(1, song_id, HEADER.size, len(z), len(xml)) + z


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "unpack":
        sid, xml = unpack(open(args[0], "rb").read())
        out = args[1] if len(args) > 1 else f"melody_{sid}.xml"
        open(out, "wb").write(xml)
        print(f"song {sid}: {len(xml)} bytes -> {out}")
    elif cmd == "pack":
        data = pack(open(args[0], "rb").read(), int(args[1]))
        open(args[2], "wb").write(data)
        print(f"{len(data)} bytes -> {args[2]}")
    else:
        print(__doc__)
