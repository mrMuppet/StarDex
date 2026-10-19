"""Cross references in eboot.bin: who uses a string, who calls a function.

  python xref.py str "entitlementsModified" [...]
  python xref.py calls 0x7d4fe0 [...]
"""
import re
import struct
import sys

from ebootdis import BASE, Eboot

eb = Eboot(sys.argv[0].replace("xref.py", "../build/eboot.bin") if False else "build/eboot.bin")
TEXT_OFF, TEXT_LEN = 0x4000, 0x736DDC
code = eb.data[TEXT_OFF:TEXT_OFF + TEXT_LEN]


def str_va(s: bytes):
    out = []
    for m in re.finditer(re.escape(s) + b"\0", eb.data):
        o = m.start()
        if o and eb.data[o - 1] != 0:
            continue  # only whole strings
        for v, fo, sz in eb.segs:
            if fo <= o < fo + sz:
                out.append(BASE + v + o - fo)
    return out


def lea_refs(va):
    out = []
    for m in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", code):
        i = m.start()
        disp, = struct.unpack_from("<i", code, i + 3)
        if BASE + i + 7 + disp == va:
            out.append(BASE + i)
    return out


def call_refs(target):
    out = []
    for m in re.finditer(rb"\xe8", code):
        i = m.start()
        rel, = struct.unpack_from("<i", code, i + 1)
        if BASE + i + 5 + rel == target:
            out.append(BASE + i)
    return out


def func_strings(f):
    return list(dict.fromkeys(n.split('"')[1] for _i, n in eb.disasm(f, eb.func_end(f)) if '"' in n))


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    for a in args:
        if mode == "str":
            for va in str_va(a.encode()):
                for r in lea_refs(va):
                    f = eb.func_start(r)
                    print(f'"{a}" @ {va:#x} used at {r:#x} in func {f:#x}: {" | ".join(func_strings(f))[:300]}')
        else:
            for r in call_refs(int(a, 16)):
                f = eb.func_start(r)
                print(f"{a} called at {r:#x} in func {f:#x}: {' | '.join(func_strings(f))[:300]}")
