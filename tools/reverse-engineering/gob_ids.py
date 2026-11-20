import re, struct, sys
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\Object.lto')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
def s(v):
    o = v - base
    if 0 <= o < len(data):
        e = data.find(b'\0', o, o + 60); t = data[o:e] if e > o else b''
        if 2 <= len(t) <= 40 and all(32 <= c < 127 for c in t): return t.decode()
# map handler address -> name by finding the 'push <str>' at the handler start
handler_name = {}
for i in md.disasm(data[0x1005e6d0 - base: 0x1005eae9 - base], 0x1005e6d0):
    if i.mnemonic == 'push' and i.op_str.startswith('0x'):
        t = s(int(i.op_str, 16))
        if t and i.address not in handler_name: handler_name[i.address] = t
tbl = struct.unpack('<%dI' % 54, data[0x1005eae9 - base: 0x1005eae9 - base + 54 * 4])
print('model id -> name (id = 76 + index)')
out = []
for idx, a in enumerate(tbl):
    out.append(f'{76 + idx}={handler_name.get(a, "?" + hex(a))}')
print(', '.join(out))
