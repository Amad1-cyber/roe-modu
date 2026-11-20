import sys, struct, re
sys.path.insert(0, sys.argv[1])
import pefile
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
for t in sys.argv[2:]:
    target = int(t, 16)
    pat = struct.pack('<I', target)
    hits = [base + m.start() for m in re.finditer(re.escape(pat), data)]
    # direct calls
    text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
    ts = text.VirtualAddress; code = data[ts:ts+text.Misc_VirtualSize]
    calls = []
    for m in re.finditer(b'\xe8(....)', code, re.S):
        site = base + ts + m.start(); rel = struct.unpack('<i', m.group(1))[0]
        if (site + 5 + rel) & 0xFFFFFFFF == target: calls.append(hex(site))
    print(t, 'abs refs (tables/imm):', [hex(h) for h in hits][:10], ' direct calls:', calls)
