import sys, struct
sys.path.insert(0, sys.argv[1])
import pefile
pe = pefile.PE(r'C:\Program Files (x86)\Rubies of Eventide\rez\CShell.dll')
data = pe.get_memory_mapped_image(); base = pe.OPTIONAL_HEADER.ImageBase
off = 0x10079cd0 - base
tbl = struct.unpack('<9I', data[off:off+36])
for i, a in enumerate(tbl): print(f'type {0x277c+i:#x} ({0x277c+i}) -> {a:#x}')
