"""Dump a LevelDB write-ahead log (*.log): every put/delete in order.

  python leveldb_log.py 000057.log
"""
import struct
import sys


def varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7f) << s; s += 7
        if c < 0x80:
            return r, i


def records(data):
    buf, i = b"", 0
    while i + 7 <= len(data):
        blk_left = 32768 - (i % 32768)
        if blk_left < 7:
            i += blk_left; continue
        _crc, ln, typ = struct.unpack_from("<IHB", data, i)
        frag = data[i + 7:i + 7 + ln]; i += 7 + ln
        if typ == 0 and ln == 0:
            continue
        if typ in (1,):           # FULL
            yield frag
        elif typ == 2:            # FIRST
            buf = frag
        elif typ == 3:            # MIDDLE
            buf += frag
        elif typ == 4:            # LAST
            yield buf + frag; buf = b""


def main(path):
    for rec in records(open(path, "rb").read()):
        seq, count = struct.unpack_from("<QI", rec, 0)
        i = 12
        for _ in range(count):
            tag = rec[i]; i += 1
            kl, i = varint(rec, i); key = rec[i:i + kl]; i += kl
            if tag == 1:
                vl, i = varint(rec, i); val = rec[i:i + vl]; i += vl
                print(f"{seq:6} PUT {key.decode('latin1')!r} = {val[:60]!r}{'...' if len(val) > 60 else ''} ({len(val)} B)")
            else:
                print(f"{seq:6} DEL {key.decode('latin1')!r}")
            seq += 1


if __name__ == "__main__":
    main(sys.argv[1])
