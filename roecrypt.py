import sys
KEY_CLIENT_SEND = b"You know who lives in his own world."   # client -> server (cipher key1)
KEY_SERVER_SEND = b"You know who is a blithering moron."   # server -> client (cipher key2)

def prep_key(k: bytes) -> bytearray:
    s = 0
    for b in k:
        s = (s + (b - 256 if b > 127 else b)) & 0xFFFFFFFF
    s = ((s >> 24) + ((s >> 16) & 0xFF) + ((s >> 8) & 0xFF) + (s & 0xFF)) & 0xFF
    return bytearray(((b if b < 128 else b - 256) ^ s ^ 0x12) & 0xFF for b in k)

def nib(c): return ((c & 0xF) << 4) | ((c & 0xF0) >> 4)

class Stream:
    def __init__(self, key: bytes, state: int = 0):
        self.k = prep_key(key); self.pos = 0; self.s = state
    def encrypt(self, data: bytes) -> bytes:
        out = bytearray()
        for p in data:
            kb = self.k[self.pos]
            c = (nib(p) ^ self.s ^ (kb ^ 0xA8)) & 0xFF
            out.append(c)
            self.s = c
            self.k[self.pos] = kb ^ c
            self.pos += 1
            if self.pos >= len(self.k): self.pos = 0
        return bytes(out)
    def decrypt(self, data: bytes) -> bytes:
        out = bytearray()
        for c in data:
            kb = self.k[self.pos]
            p = nib((c ^ self.s ^ (kb ^ 0xA8)) & 0xFF)
            out.append(p)
            self.s = c
            self.k[self.pos] = kb ^ c
            self.pos += 1
            if self.pos >= len(self.k): self.pos = 0
        return bytes(out)

if __name__ == '__main__':
    cap = bytes.fromhex(sys.argv[1])
    for name, key in (('client-send key', KEY_CLIENT_SEND), ('server-send key', KEY_SERVER_SEND)):
        for st in (0,):
            pt = Stream(key, st).decrypt(cap)
            print(f'{name}, state0={st}:')
            print('  hex  :', pt.hex())
            print('  ascii:', ''.join(chr(b) if 32 <= b < 127 else '.' for b in pt))
