import sys, struct, re
sys.path.insert(0, sys.argv[1])
import pefile, capstone
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
iat = {}
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for i in d.imports: iat[i.address] = d.dll.decode().split('.')[0] + '!' + (i.name.decode() if i.name else '#%d' % i.ordinal)
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
ts = text.VirtualAddress; code = data[ts:ts+text.Misc_VirtualSize]
want = {n: a for a, n in iat.items() if n.split('!')[1] in ('send','recv','connect','WSAAsyncSelect','select','closesocket','WSAAccept','listen','bind')}
# indirect calls: call dword ptr [iat]  => ff 15 <addr>
sites = {}
for m in re.finditer(b'\xff\x15(....)', code, re.S):
    a = struct.unpack('<I', m.group(1))[0]
    if a in iat and iat[a].split('!')[1] in ('send','recv','connect','WSAAsyncSelect','select','closesocket','bind','listen','WSAAccept'):
        sites.setdefault(iat[a], []).append(hex(base + ts + m.start()))
for k, v in sorted(sites.items()): print(k, v)
