import sys, struct, re
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
tbl = {}
for line in open(sys.argv[2]):
    p = line.split()
    tbl[int(p[0])] = int(p[2], 16)
addrs = sorted(set(tbl.values()))
def end_of(a):
    nxt = [x for x in addrs if x > a]
    return min(nxt[0] if nxt else a + 0x600, a + 0x800)
LO, HI = 0x1009c000, 0x100a2000
for t, a in sorted(tbl.items()):
    callees = set()
    for ins in md.disasm(data[a - base: end_of(a) - base], a):
        if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
            v = int(ins.op_str, 16)
            if LO <= v < HI: callees.add(hex(v))
    if callees: print(f'type {t} ({t:#x}) handler {a:#x} -> {sorted(callees)}')
