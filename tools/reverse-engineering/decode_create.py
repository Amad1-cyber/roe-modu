import re, struct, sys
lines = open(sys.argv[1]).read().splitlines()
msgs = {}
for l in lines:
    m = re.search(r'\[game\] <- type (0x[0-9a-f]+) \((\d+)\) len (\d+): ([0-9a-f]*)$', l)
    if m and m.group(1) in ('0x006c', '0x0098'): msgs[m.group(1)] = bytes.fromhex(m.group(4))
def dump(b, title):
    print(f'=== {title}: {len(b)} payload bytes')
    for i in range(0, len(b), 16):
        row = b[i:i+16]
        print(f'  {i:04x}  {row.hex(" "):47s}  ' + ''.join(chr(c) if 32 <= c < 127 else '.' for c in row))
b = msgs['0x006c']; dump(b, 'client 0x6c (identity/appearance)')
print('  first name  :', b[0:18].split(b"\0")[0], '| bytes 18..:', b[18:30].hex(' '))
b2 = msgs['0x0098']; dump(b2[:96], 'client 0x98 (first 96 bytes)')
print('  as u32 from +24 :', [struct.unpack_from('<I', b2, o)[0] for o in range(24, 96, 4)])
print('  tail u32 (last 24 bytes):', [struct.unpack_from('<I', b2, o)[0] for o in range(len(b2) - 24, len(b2), 4)])
