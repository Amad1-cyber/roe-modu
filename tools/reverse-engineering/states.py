import sys, re, struct
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
ts = text.VirtualAddress; code = data[ts:ts+text.Misc_VirtualSize]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
# every "GameStateHandler()::..." string and its function(s)
for m in re.finditer(rb'GameStateHandler\(\)::[ -~]{3,100}', data):
    t = m.group().decode(); va = base + m.start()
    refs = [base + ts + r.start() for r in re.finditer(re.escape(struct.pack('<I', va)), code)]
    print(f'{t[:75]!r} refs {[hex(r) for r in refs][:3]}')
print()
# all stores of a state constant into [reg+4] inside the 0x101fa000-0x101fd000 region
lo, hi = 0x101fa000, 0x101fd800
cur_fn = None
for i in md.disasm(data[lo - base: hi - base], lo):
    if i.mnemonic == 'push' and i.op_str == 'ebp': cur_fn = i.address
    mm = re.match(r'dword ptr \[e[a-d]x \+ 4\], (0x[0-9a-f]+|\d+)$', i.op_str) if i.mnemonic == 'mov' else None
    if mm: print(f'fn {cur_fn:#x} @ {i.address:#x}: state[+4] = {int(mm.group(1), 0)} ({int(mm.group(1), 0):#x})')
