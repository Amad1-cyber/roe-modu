import sys, struct, re
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
ts = text.VirtualAddress; tsz = text.Misc_VirtualSize; code = data[ts:ts+tsz]
lo, hi = base + ts, base + ts + tsz
target = 0x10238350
pat = struct.pack('<I', target)
hits = [base + ts + m.start() for m in re.finditer(re.escape(pat), code)]
print('imm32 xrefs to 0x10238350:', [hex(h) for h in hits])
if hits:
    h = hits[0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
    # print neighbourhood
    start = h - 0x60
    for ins in md.disasm(data[start - base: start - base + 0x120], start):
        print(f'{ins.address:08x}  {ins.mnemonic:6s} {ins.op_str}')
