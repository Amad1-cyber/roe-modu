import sys
sys.path.insert(0, sys.argv[1])
import pefile
game = r'C:\Program Files (x86)\Rubies of Eventide'
for rel in (r'rez\CShell.dll', 'CWIRpc4.dll', 'server.dll', r'rez\SRes.dll'):
    pe = pefile.PE(game + '\\' + rel)
    print('=====', rel, 'base', hex(pe.OPTIONAL_HEADER.ImageBase), 'size', hex(pe.OPTIONAL_HEADER.SizeOfImage))
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            names = [i.name.decode() if i.name else f'#{i.ordinal}' for i in d.imports]
            if d.dll.decode().lower().startswith(('ws2', 'wsock', 'wininet', 'cwi', 'ltmsg', 'lt')) or 'sock' in d.dll.decode().lower():
                print('  IMPORT', d.dll.decode(), len(names), names[:60])
            else:
                print('  import', d.dll.decode(), len(names))
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        ex = [e.name.decode() if e.name else f'#{e.ordinal}' for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
        print('  EXPORTS', len(ex), ex[:80])
