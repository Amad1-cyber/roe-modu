import sys, struct, re
sys.path.insert(0, sys.argv[1])
import pefile, capstone
dll, start, end = sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4], 16)
pe = pefile.PE(dll)
data = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
iat = {}
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for i in d.imports:
        iat[i.address] = (d.dll.decode().split('.')[0] + '!' + (i.name.decode() if i.name else '#%d' % i.ordinal))
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
tstart = text.VirtualAddress
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
# thunk map: jmp dword ptr [iat]
thunks = {}
code = data[tstart:tstart+text.Misc_VirtualSize]
for m in re.finditer(b'\xff\x25(....)', code, re.S):
    a = struct.unpack('<I', m.group(1))[0]
    if a in iat: thunks[base + tstart + m.start()] = iat[a]
def cstr(va):
    o = va - base
    if 0 <= o < len(data) - 1:
        e = data.find(b'\0', o, o + 120)
        s = data[o:e] if e > o else b''
        if len(s) >= 3 and all(32 <= c < 127 for c in s): return s.decode()
    return None
lo = start - base
for ins in md.disasm(data[lo:lo + (end - start)], start):
    note = ''
    if ins.mnemonic in ('call', 'jmp') and ins.op_str.startswith('0x'):
        t = int(ins.op_str, 16)
        if t in thunks: note = '  ; ' + thunks[t]
    for tok in re.findall(r'0x[0-9a-f]{6,8}', ins.op_str):
        v = int(tok, 16)
        s = cstr(v)
        if s and ins.mnemonic in ('push', 'mov', 'lea'): note += '  ; "%s"' % s
    print('%08x  %-6s %s%s' % (ins.address, ins.mnemonic, ins.op_str, note))

