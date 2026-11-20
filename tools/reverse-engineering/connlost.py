import sys, re, struct
sys.path.insert(0, sys.argv[1])
import pefile
for rel in (r'rez\CShell.dll', r'Lithtech.exe'):
    pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide' + '\\' + rel)
    data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
    ts = text.VirtualAddress; code = data[ts:ts+text.Misc_VirtualSize]
    for m in re.finditer(rb'(Connection lost[ -~]{0,80}|[ -~]{0,40}disconnect[ -~]{0,60}|[ -~]{0,30}timed? ?out[ -~]{0,40})', data):
        t = m.group().decode(); va = base + m.start()
        refs = [hex(base + ts + r.start()) for r in re.finditer(re.escape(struct.pack('<I', va)), code)][:4]
        if refs: print(rel, hex(va), repr(t[:90]), refs)
