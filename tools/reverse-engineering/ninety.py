import sys, re, struct
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
ts = text.VirtualAddress; code = data[ts:ts+text.Misc_VirtualSize]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
refs = [base + ts + r.start() for r in re.finditer(re.escape(struct.pack('<I', 0x102d2b64)), code)]
print('refs to 90.0 float at 0x102d2b64:', [hex(r) for r in refs])
for r in refs:
    # find function start
    pos = r - base
    while pos > 0 and not (data[pos:pos+3] == b'\x55\x8b\xec' and data[pos-1] in (0xCC, 0xC3, 0xC2)): pos -= 1
    fs = base + pos
    print(f'--- ref {r:#x} in function {fs:#x}')
    for i in md.disasm(data[r - 0x50 - base: r + 0x30 - base], r - 0x50):
        if i.address >= r - 0x40: print(f'   {i.address:08x} {i.mnemonic:6s} {i.op_str}')
