import sys, re
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
def cstr(va):
    o = va - base
    if 0 <= o < len(data) - 1:
        e = data.find(b'\0', o, o + 120); s = data[o:e] if e > o else b''
        if len(s) >= 3 and all(32 <= c < 127 for c in s): return s.decode()
start, end, copy_base = int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4], 16)  # copy_base = K in [ebp-K] where msg+0 lives
for i in md.disasm(data[start - base: end - base], start):
    if re.search(r'int3|0xcccccccc|rep stosd|_chkesp|cmp    ebp, esp|cmp    esi, esp', f'{i.mnemonic} {i.op_str}'): continue
    note = ''
    for m in re.finditer(r'\[ebp - (0x[0-9a-f]+)\]', i.op_str):
        k = int(m.group(1), 16); off = copy_base - k
        if 0 <= off < 0x170: note += f' <msg+{off:#x}>'
    for tok in re.findall(r'0x[0-9a-f]{6,8}', i.op_str):
        s = cstr(int(tok, 16))
        if s and i.mnemonic in ('push', 'mov', 'lea'): note += f'  ; "{s}"'
    print(f'{i.address:08x}  {i.mnemonic:6s} {i.op_str}{note}')
