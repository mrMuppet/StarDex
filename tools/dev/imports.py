"""Resolve eboot imports: NID -> PLT stub address.  python tools/imports.py sceErrorDialogOpen ..."""
import struct, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from nid import nid
from ebootdis import BASE
d = open(Path(__file__).resolve().parents[2] / "build" / "eboot.bin","rb").read()
phoff, = struct.unpack_from("<Q", d, 0x20); phentsz, phnum = struct.unpack_from("<HH", d, 0x36)
phs=[struct.unpack_from("<IIQQQQQQ", d, phoff+i*phentsz) for i in range(phnum)]
dyn=[p for p in phs if p[0]==2][0]; dld=[p for p in phs if p[0]==0x61000000][0]
tags={}
o=dyn[2]
while True:
    t,v=struct.unpack_from("<qQ",d,o); o+=16
    if t==0: break
    tags.setdefault(t,v)
base=dld[2]
jmprel=base+tags[0x61000029]; pltsz=tags[0x6100002d]; symtab=base+tags[0x61000039]; strtab=base+tags[0x61000035]
def s(off):
    e=d.index(b"\0",off); return d[off:e].decode()
names={}
for i in range(pltsz//24):
    r_off,info,add=struct.unpack_from("<QQq",d,jmprel+i*24)
    sym=info>>32
    st_name,=struct.unpack_from("<I",d,symtab+sym*24)
    names[r_off]=s(strtab+st_name).split("#")[0]
# find plt stubs: ff 25 disp32 -> got
text=[p for p in phs if p[0]==1 and p[1]&1][0]
code=d[text[2]:text[2]+text[5]]
stub={}
for m in re.finditer(rb"\xff\x25",code):
    i=m.start(); disp,=struct.unpack_from("<i",code,i+2)
    tgt=text[3]+i+6+disp
    if tgt in names: stub[names[tgt]]=BASE+text[3]+i
want=sys.argv[1:]
for w in want:
    n=nid(w); print(w, n, hex(stub[n]) if n in stub else "-")
