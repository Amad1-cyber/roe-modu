import sys, struct, re
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
ts = text.VirtualAddress; tsz = text.Misc_VirtualSize
lo, hi = base + ts, base + ts + tsz
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
# find ctor start: scan back from 0x10237bae for a function prologue
pos = 0x10237bae - base
while not (data[pos:pos+3] == b'\x55\x8b\xec' and data[pos-1] in (0xCC, 0xC3, 0xC2)): pos -= 1
cstart = base + pos
print('ctor start', hex(cstart))
table = {}
addr = cstart
end = cstart + 0x2000
for ins in md.disasm(data[cstart - base: end - base], cstart):
    if ins.mnemonic == 'mov' and 'dword ptr [' in ins.op_str and ins.op_str.count(',') == 1:
        dst, src = [x.strip() for x in ins.op_str.split(',')]
        m = re.match(r'dword ptr \[e[a-d]x \+ (0x[0-9a-f]+)\]$', dst)
        if m and src.startswith('0x'):
            disp, imm = int(m.group(1), 16), int(src, 16)
            if lo <= imm < hi and 4 <= disp <= 0x5c4: table[(disp - 4) // 4] = imm
    if ins.mnemonic == 'ret' and ins.address > cstart + 0x100 and len(table) > 50: print('ctor ends', hex(ins.address)); break
print('entries:', len(table))
def cstr(va):
    o = va - base
    if 0 <= o < len(data) - 1:
        e = data.find(b'\0', o, o + 100)
        s = data[o:e] if e > o else b''
        if len(s) >= 6 and all(32 <= c < 127 for c in s): return s.decode()
def first_strings(fa, n=2):
    out = []
    for ins in md.disasm(data[fa - base: fa - base + 0x400], fa):
        if ins.mnemonic == 'push' and ins.op_str.startswith('0x'):
            v = int(ins.op_str, 16)
            if base <= v < base + len(data):
                s = cstr(v)
                if s: out.append(s[:60])
        if ins.mnemonic == 'ret' and len(out) >= 0 and ins.address > fa + 0x20: break
        if len(out) >= n: break
    return out
with open(sys.argv[2], 'w') as f:
    for t in sorted(table):
        f.write(f'{t:4d} {t:#06x}  {table[t]:#x}  {" | ".join(first_strings(table[t]))}\n')
print('written', sys.argv[2])
