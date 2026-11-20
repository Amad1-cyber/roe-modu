import sys, struct
path = sys.argv[1]
data = open(path, 'rb').read()
sigs = {
 'Blowfish P-array 0x243F6A88': struct.pack('<I', 0x243F6A88),
 'Blowfish S-box0 0xD1310BA6': struct.pack('<I', 0xD1310BA6),
 'TEA delta 0x9E3779B9': struct.pack('<I', 0x9E3779B9),
 'AES sbox 637c777b': bytes.fromhex('637c777bf26b6fc5'),
 'AES inv sbox 52096ad5': bytes.fromhex('52096ad53036a538'),
 'MD5 T[0] 0xD76AA478': struct.pack('<I', 0xD76AA478),
 'SHA1 init 0x67452301': struct.pack('<I', 0x67452301),
 'SHA1 K 0x5A827999': struct.pack('<I', 0x5A827999),
 'CRC32 table (00000000 77073096)': struct.pack('<II', 0, 0x77073096),
 'DES sbox1 0e04 0d01': bytes.fromhex('0e040d0102 0f0b08'.replace(' ','')),
 'RC5/RC6 P32 0xB7E15163': struct.pack('<I', 0xB7E15163),
 'CAST/other 0x30FB40D4': struct.pack('<I', 0x30FB40D4),
 'Twofish/others 0xA9 q0': bytes.fromhex('a967b3e804'),
 'RC2 pitable d978f9c4': bytes.fromhex('d978f9c419dd'),
 'SHA256 K 0x428A2F98': struct.pack('<I', 0x428A2F98),
}
for n, b in sigs.items():
    hits = []; i = data.find(b)
    while i != -1 and len(hits) < 4:
        hits.append(hex(i)); i = data.find(b, i + 1)
    print(f'{n:40s}', hits if hits else '-')
