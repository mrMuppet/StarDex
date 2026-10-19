"""Disassemble the decrypted SingStar eboot.bin at runtime addresses (as printed in klog crash dumps).

  python ebootdis.py EBOOT START:END[:MARK] [...]     linear disassembly, MARK flagged with >>
  python ebootdis.py EBOOT --func ADDR [...]          whole function containing ADDR (clang prologue scan)

rip-relative operands are resolved and annotated with the C string they point to.
"""
import re
import struct
import sys

import capstone

BASE = 0x400000  # runtime load address of eboot.bin (from AFR log: base_address)


class Eboot:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        phoff, = struct.unpack_from("<Q", self.data, 0x20)
        phentsz, phnum = struct.unpack_from("<HH", self.data, 0x36)
        self.segs = []
        for i in range(phnum):
            _t, _f, off, vaddr, _p, filesz, _m, _a = struct.unpack_from("<IIQQQQQQ", self.data, phoff + i * phentsz)
            if filesz:
                self.segs.append((vaddr, off, filesz))
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def off(self, va):
        va -= BASE
        for v, o, s in self.segs:
            if v <= va < v + s:
                return o + va - v
        return None

    def read(self, va, n):
        o = self.off(va)
        return self.data[o:o + n] if o is not None else b""

    def cstr(self, va):
        o = self.off(va)
        if o is None:
            return None
        e = self.data.find(b"\0", o, o + 160)
        s = self.data[o:e]
        if e > o and all(32 <= c < 127 or c in (9, 10) for c in s):
            return s.decode("latin1")
        return None

    def disasm(self, start, end):
        for ins in self.md.disasm(self.read(start, end - start), start):
            note = ""
            for m in re.findall(r"rip \+ (0x[0-9a-f]+)", ins.op_str):
                tgt = ins.address + ins.size + int(m, 16)
                s = self.cstr(tgt)
                note = f'   ; {tgt:#x} "{s}"' if s else f"   ; {tgt:#x}"
            yield ins, note

    def func_start(self, addr, limit=0x8000):
        a = addr
        while a > addr - limit:
            if self.read(a, 4) == b"\x55\x48\x89\xe5":
                return a
            a -= 1
        return None

    def func_end(self, start, limit=0x8000):
        nxt = self.data.find(b"\x55\x48\x89\xe5", self.off(start) + 4, self.off(start) + limit)
        return start + (nxt - self.off(start)) if nxt > 0 else start + limit

    def show(self, start, end, mark=None):
        for ins, note in self.disasm(start, end):
            flag = ">> " if mark is not None and ins.address <= mark < ins.address + ins.size else "   "
            print(f"{flag}{ins.address:x}: {ins.mnemonic} {ins.op_str}{note}")


def main(argv):
    eb = Eboot(argv[0])
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--func":
            addr = int(args.pop(0), 16)
            s = eb.func_start(addr)
            print(f"=== function {s:x} (contains {addr:x})")
            eb.show(s, eb.func_end(s), addr)
        else:
            s, e, *m = [int(x, 16) for x in a.split(":")]
            print(f"=== {s:x}-{e:x}")
            eb.show(s, e, m[0] if m else None)


if __name__ == "__main__":
    main(sys.argv[1:])
