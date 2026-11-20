"""ROE MODU server: a clean-room emulator of the Rubies of Eventide 0.95 login + game server, written from observation of
the client (CShell.dll) protocol. Not affiliated with the original operators.

Protocol summary (all verified against the real client):
  * TCP; every packet is [s16 total_len][u16 type][payload]; the stream is obfuscated by roecrypt.Stream.
  * Login port (default 3142): 0x65 login -> 0x66 ok / 0x67 error text; 0x2778 server list; 0x277c pick server -> 0x277e.
  * Game port (default 3143): 0x65 auth (token from login) -> 0x66; 0x67 char list; 0xe7 name check -> 0x142;
    0x6c+0x98 create character -> 0x76; 0x6a enter world -> 0x73 (InitGame), 0x89 (zone), 0xf4, 0x91, 0xd2 (player), 0xf3 (stats).
  * The client drops the link after 90 s of server silence, so a no-op keepalive (0x67) is sent every 30 s.
Run:  python roe_server.py        (settings live in config.json next to this file; see roe_store.py)
"""
import json, math, os, secrets, socket, struct, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roe_store as store
from roecrypt import Stream, KEY_CLIENT_SEND, KEY_SERVER_SEND

CFG = store.load_config()
KEEPALIVE_TYPE = 0x67
STARTED = time.time()
TOKENS = {}                      # login token (hex) -> (account, issued_at)
FAILS = {}                       # ip -> [timestamps of recent failed logins]
ONLINE = {}                      # id(game session) -> account  (the player count)
_loglock = threading.Lock()
_seen_unhandled = set()
STATUS_FILE = os.path.join(store.BASE, 'status.json')


def log(msg):
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    with _loglock:
        try:
            if os.path.exists(store.LOG_FILE) and os.path.getsize(store.LOG_FILE) > 4_000_000:
                os.replace(store.LOG_FILE, store.LOG_FILE + '.old')
        except OSError:
            pass
        with open(store.LOG_FILE, 'a', encoding='utf8') as f:
            f.write(line + '\n')


def cstr(b):
    return b.split(b'\0', 1)[0].decode('latin-1')


def frame(mtype, payload=b''):
    return struct.pack('<hH', 4 + len(payload), mtype) + payload


def write_status():
    """Publish live status for the ROE MODU GUI (player count, who is online, uptime)."""
    while True:
        try:
            players = sorted(ONLINE.values())
            tmp = STATUS_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf8') as f:
                json.dump({'pid': os.getpid(), 'started': STARTED, 'updated': time.time(), 'online': len(players),
                           'players': players, 'bind': CFG['bind'], 'advertise': CFG['advertise_host'],
                           'login_port': CFG['login_port'], 'game_port': CFG['game_port']}, f)
            os.replace(tmp, STATUS_FILE)
        except OSError:
            pass
        time.sleep(1.5)


# ------------------------------------------------------------------ message builders
def player_state(name, hp, bp, mp, ep, level=1):
    """Server msg 0xF3 (700 bytes, header added by send()). Flag bits enable fields (offsets include the 4-byte header)."""
    m = bytearray(700)
    struct.pack_into('<hH', m, 0, 700, 0xF3)
    flags = 0x800
    m[8:28] = name.encode().ljust(20, b'\0')[:20]
    for off, bit, val in ((0x2c, 0x1, hp), (0x30, 0x2, bp), (0x38, 0x8, mp), (0x34, 0x4, ep), (0x3c, 0x10, level),
                          (0x40, 0x20, hp), (0x44, 0x40, bp)):
        struct.pack_into('<i', m, off, val)
        flags |= bit
    struct.pack_into('<I', m, 4, flags)
    return bytes(m[4:])


def model_add(uid, kind, pos, name=''):
    """Server msg 0xD2 ServerOModelAdd (360 bytes): uid@+4, pos floats@+8/+0xc/+0x10, kind(0..5)@+0x2c, name@+0x3c."""
    m = bytearray(360)
    struct.pack_into('<hH', m, 0, 360, 0xD2)
    struct.pack_into('<I', m, 4, uid)
    struct.pack_into('<3f', m, 8, *pos)
    struct.pack_into('<I', m, 0x2c, kind)
    m[0x3c:0x5c] = name.encode().ljust(32, b'\0')[:32]
    return bytes(m[4:])


MODEL_GOBLIN = 76        # monster model ids are 76..129 (see README "Content"): 76 goblin, 77 kobold, 79 wolf, 80 boar, 81 bear...

# Starter kit: (item id, inventory type, display name, icon name from rez\Interface\Icon\Item without _16.dtx)
STARTER_KIT = [
    (1001, 0, 'Iron Longsword', 'sword_longsword'),
    (1002, 0, 'Steel Dirk', 'dagger_dirk'),
    (1003, 1, 'Studded Leather Chest', 'chest_studdedleather'),
    (1004, 2, 'Round Wooden Shield', 'shield_roundwood'),
    (1005, 3, 'Flask of Mead', 'vial'),
]


def npc_add(uid, kind, pos, model_id, name):
    """Server msg 0xD2 for a monster/NPC: model id (76..129) at +0x18, object kind at +0x2c (0/1/2 build different classes)."""
    m = bytearray(360)
    struct.pack_into('<hH', m, 0, 360, 0xD2)
    struct.pack_into('<I', m, 4, uid)
    struct.pack_into('<3f', m, 8, *pos)
    struct.pack_into('<I', m, 0x18, model_id)
    struct.pack_into('<I', m, 0x2c, kind)
    m[0x3c:0x5c] = name.encode().ljust(32, b'\0')[:32]
    return bytes(m[4:])


def item_add(item_id, itype, name, icon):
    """Server msg 0xFE inventory add (452 bytes): id@+4, type@+0x10 (<=10), name@+0x14 (50), icon@+0x46 (item/<icon>_16.dtx)."""
    m = bytearray(452)
    struct.pack_into('<hH', m, 0, 452, 0xFE)
    struct.pack_into('<I', m, 4, item_id)
    struct.pack_into('<I', m, 0x10, itype)
    m[0x14:0x46] = name.encode().ljust(50, b'\0')[:50]
    m[0x46:0x78] = icon.encode().ljust(50, b'\0')[:50]
    return bytes(m[4:])


def vitals_from_record(rec):
    """Starting vitals reproduce the character-creation screen's own numbers (STR/INT/DEX/CON at record +0x14..0x17)."""
    intel, con = rec[0x15], rec[0x17]
    return con + 5, round(con * 0.8), intel + 5, round(intel * 2 / 3 + 4)


def entry_payload(idx, first, rec, override=None, extra=None):
    """Character-list entry (server 0x6c, 56 bytes with header): name[20], 4 u32, u16, 4 appearance bytes, pad, 2 u32."""
    pick = {'sex': rec[0x11], 'b12': rec[0x12], 'race': rec[0x13], 'zero': 0, 'one': 1}
    app = bytes(pick.get(k, 0) for k in CFG['entry_bytes'])[:4].ljust(4, b'\0')
    if override:
        app = bytes(override)[:4].ljust(4, b'\0')
    u32 = [idx + 1, 0, 0, 0]
    word = 1
    if extra:
        u32 = (list(extra.get('u32', u32)) + [0, 0, 0, 0])[:4]
        word = extra.get('word', word)
    return struct.pack('<20s4IH4B2x2I', first.encode()[:19], *u32, word, *app, 0, 0)


# ------------------------------------------------------------------ monsters
class Spawner:
    """Keeps monsters in the world. When one dies it is removed (0xD4) and comes back `respawn_seconds` later
    (default 300 = 5 minutes). `definitions` come from config.json ("spawns"). send(type, payload) delivers to the client."""

    def __init__(self, send, definitions, respawn_seconds, origin):
        self.send, self.respawn_seconds = send, respawn_seconds
        self.slots = {}                      # uid -> {'def': definition, 'pos': (x, y, z), 'alive': bool}
        self.lock = threading.RLock()
        self.timers = []
        uid = 2000
        for d in definitions:
            count = int(d.get('count', 1))
            for i in range(count):
                uid += 1
                ang = (i + 0.5) * (2 * math.pi / max(count, 1)) + 0.4
                r = float(d.get('radius', 600)) * (0.7 + 0.3 * ((i * 37) % 10) / 10)
                self.slots[uid] = {'def': d, 'alive': False,
                                   'pos': (origin[0] + r * math.cos(ang), origin[1] - 20, origin[2] + r * math.sin(ang))}

    def spawn_all(self):
        for uid in list(self.slots):
            self._spawn(uid)

    def _spawn(self, uid):
        with self.lock:
            s = self.slots[uid]
            d = s['def']
            s['alive'] = True
            label = f"{d.get('name', 'Monster')} (Lv {int(d.get('level', 1))})"
            self.send(0xd2, npc_add(uid, int(d.get('kind', 1)), s['pos'], int(d['model']), label))

    def on_death(self, uid):
        """Call when monster `uid` is killed (combat will call this; kill.txt can too). Returns True if it was alive."""
        with self.lock:
            s = self.slots.get(uid)
            if not s or not s['alive']:
                return False
            s['alive'] = False
            self.send(0xd4, struct.pack('<I', uid))
            t = threading.Timer(self.respawn_seconds, self._spawn, (uid,))
            t.daemon = True
            t.start()
            self.timers.append(t)
            log(f'  monster {uid} died; respawns in {self.respawn_seconds:g}s')
            return True

    def stop(self):
        for t in self.timers:
            t.cancel()


# ------------------------------------------------------------------ sessions
class Session:
    kind = 'login'

    def __init__(self, conn, addr):
        self.conn, self.addr = conn, addr
        self.rx = Stream(KEY_CLIENT_SEND)     # decrypts what the client sends
        self.tx = Stream(KEY_SERVER_SEND)     # encrypts what the client will decrypt
        self.account = None
        self.alive = True
        self.send_lock = threading.Lock()     # the cipher is stateful: never let two senders interleave

    def send(self, mtype, payload=b''):
        pkt = frame(mtype, payload)
        if mtype != KEEPALIVE_TYPE:
            log(f'  [{self.kind}] -> {mtype:#06x} len {len(pkt)}')
        with self.send_lock:
            self.conn.sendall(self.tx.encrypt(pkt))

    def recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            d = self.conn.recv(n - len(buf))
            if not d:
                raise ConnectionError('closed')
            buf += d
        return buf

    def run(self):
        log(f'[{self.kind}] connect {self.addr[0]}')
        try:
            while True:
                length, mtype = struct.unpack('<hH', self.rx.decrypt(self.recv_exact(4)))
                if length < 4 or length > 4096:
                    raise ConnectionError(f'bad frame length {length}')
                body = self.rx.decrypt(self.recv_exact(length - 4)) if length > 4 else b''
                if mtype != 0x74:
                    log(f'[{self.kind}] <- {mtype:#06x} len {length}')
                self.dispatch(mtype, body)
        except Exception as e:
            log(f'[{self.kind}] end {self.addr[0]}: {e!r}')
        finally:
            self.alive = False
            ONLINE.pop(id(self), None)
            self.conn.close()

    def dispatch(self, mtype, body):
        raise NotImplementedError

    def unhandled(self, mtype, body):
        key = (self.kind, mtype)
        if key not in _seen_unhandled:
            _seen_unhandled.add(key)
            log(f'  (unhandled {self.kind} type {mtype:#x}; payload {body[:48].hex()})')


class LoginSession(Session):
    kind = 'login'

    def throttled(self):
        now = time.time()
        recent = [t for t in FAILS.get(self.addr[0], []) if now - t < 60]
        FAILS[self.addr[0]] = recent
        return len(recent) >= CFG['max_login_failures_per_minute']

    def dispatch(self, mtype, body):
        if mtype == 0x65:                                       # login: account[17] password[51] version u32
            account, password = cstr(body[0:17]), cstr(body[17:68])
            if self.throttled():
                self.send(0x67, b'Too many failed logins. Wait a minute and try again.'.ljust(500, b'\0'))
                return
            ok, msg, name = store.check_login(account, password, CFG['open_registration'])
            log(f'  LOGIN account={account!r} -> {ok} ({msg})')
            if not ok:
                FAILS.setdefault(self.addr[0], []).append(time.time())
                self.send(0x67, msg.encode().ljust(500, b'\0'))
                return
            self.account = name
            token = secrets.token_bytes(16)
            TOKENS[token.hex()] = (name, time.time())
            self.send(0x66, token + struct.pack('<I', 1))
        elif mtype == 0x2778:                                   # server list (+ per-server status and player count)
            host = CFG['advertise_host']
            self.send(0x2779, struct.pack('<II', 0, 1))
            self.send(0x2776, struct.pack('<I', 1) + host.encode().ljust(100, b'\0') + struct.pack('<III', CFG['game_port'], 0, 0))
            self.send(0x277c, struct.pack('<II', 1, 0))         # status: 0 = OPEN
            self.send(0x2784, struct.pack('<II', 1, len(ONLINE)))   # second per-server value = players online
        elif mtype == 0x277c:                                   # server picked
            self.send(0x277e, struct.pack('<II', struct.unpack_from('<I', body, 0)[0], 1))
        else:
            self.unhandled(mtype, body)


class GameSession(Session):
    kind = 'game'

    def __init__(self, conn, addr):
        super().__init__(conn, addr)
        self.pending_record = None
        self.pending_name = None

    def characters(self):
        out = []
        for c in store.characters_of(self.account or ''):
            out.append((c['first'], bytes.fromhex(c['record']), None, None))
        for e in CFG['experiment_chars']:
            out.append((e['name'], bytes(56), e.get('bytes'), e))
        return out

    def populate(self, name, pos, hp, bp, mp, ep):
        """Fill the world once the zone is ready: the player's own object, stats, a few goblins and the starter kit."""
        try:
            time.sleep(5.0)
            self.send(0xd2, model_add(1, 0, pos[:3], name))
            time.sleep(1.0)
            self.send(0xf3, player_state(name, hp, bp, mp, ep))
            self.spawner = Spawner(self.send, CFG['spawns'], CFG['respawn_seconds'], pos)
            self.spawner.spawn_all()
            for item in STARTER_KIT:
                self.send(0xfe, item_add(*item))
            log(f'  populated: {len(self.spawner.slots)} monsters (respawn {CFG["respawn_seconds"]}s) + starter kit')
            self.watch_commands()
        except Exception as e:
            log(f'  populate failed: {e!r}')

    def watch_commands(self):
        """Debug hook until combat is decoded: put a monster uid (or the word all) in kill.txt to 'kill' it."""
        path = os.path.join(store.BASE, 'kill.txt')
        while self.alive:
            if os.path.exists(path):
                try:
                    words = open(path, encoding='utf-8-sig').read().split()
                    os.remove(path)
                    for w in words:
                        for uid in (list(self.spawner.slots) if w.lower() == 'all' else [int(w)]):
                            self.spawner.on_death(uid)
                except (OSError, ValueError) as e:
                    log(f'  kill.txt ignored: {e!r}')
            time.sleep(1.0)
        self.spawner.stop()

    def keepalive(self):
        while self.alive:
            time.sleep(CFG['keepalive_seconds'])
            try:
                if self.alive:
                    self.send(KEEPALIVE_TYPE)
            except Exception:
                return

    def dispatch(self, mtype, body):
        if mtype == 0x65:                                       # auth: account[17] password[51] token[16] version u32
            entry = next((TOKENS[body[o:o + 16].hex()] for o in range(0, max(0, len(body) - 15)) if body[o:o + 16].hex() in TOKENS), None)
            if not entry or time.time() - entry[1] > 900:
                log('  game auth rejected (unknown/expired token)')
                self.conn.close()
                return
            self.account = entry[0]
            ONLINE[id(self)] = self.account
            self.send(0x66)
            threading.Thread(target=self.keepalive, daemon=True).start()
        elif mtype == 0x67:                                     # character list
            self.send(0x6b)
            for i, (first, rec, override, extra) in enumerate(self.characters()):
                self.send(0x6c, entry_payload(i, first, rec, override, extra))
            self.send(0x6d)
        elif mtype == 0xe7:                                     # name check {first[18], last[18]}
            first, last = cstr(body[0:18]), cstr(body[18:36])
            ok = bool(first) and first.isalpha() and (not last or last.isalpha())
            text = 'Name accepted.' if ok else 'Names may only contain letters.'
            if ok and store.name_taken(first, last):
                ok, text = False, 'That name is already taken.'
            log(f'  name check {first!r} {last!r} -> {ok}')
            self.send(0x142, bytes([1 if ok else 0]) + text.encode().ljust(503, b'\0'))
        elif mtype == 0x6c:                                     # create: identity/appearance record (56 bytes)
            self.pending_record = bytes(body[:56])
            self.pending_name = (cstr(body[0:17]), cstr(body[0x18:0x2c]))
        elif mtype == 0x98:                                     # create: skills record -> finish
            if not self.pending_record:
                return
            first, last = self.pending_name
            try:
                store.add_character(self.account, first, last, self.pending_record.hex(), body.hex())
                log(f'  CREATED character {first} {last} for {self.account}')
                self.send(0x76, bytes(0x11) + b'\x01' + bytes(2))     # success flag at message byte +0x15
            except ValueError as e:
                log(f'  create failed: {e}')
                self.send(0x77, bytes([0]) + str(e).encode().ljust(499, b'\0'))
            self.pending_record = None
        elif mtype == 0x6a:                                     # enter world: name[24]
            name = cstr(body[:24])
            rec = next((ch[1] for ch in self.characters() if ch[0].lower() == name.lower()), None)
            rec = rec if rec and any(rec) else bytes(0x14) + bytes([40, 45, 50, 30]) + bytes(36)
            hp, bp, mp, ep = vitals_from_record(rec)
            log(f'  ENTER WORLD as {name!r}: hp={hp} bp={bp} mp={mp} ep={ep}')
            pos = CFG['start_pos']
            self.send(0x73)                                     # UI state: InitGame (makes the 3D-world switch build the HUD)
            self.send(0x89, struct.pack('<I4f2B2x', CFG['start_zone'], *pos, 1, 0))
            self.send(0xf4)
            threading.Timer(4.0, lambda: self.send(0x91, struct.pack('<I', 0))).start()
            threading.Thread(target=self.populate, args=(name, pos, hp, bp, mp, ep), daemon=True).start()
        elif mtype in (0x74, 0x82, 0xd4):                       # movement / housekeeping: nothing to answer yet
            pass
        else:
            self.unhandled(mtype, body)


def serve(host, port, cls):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(16)
    log(f'{cls.kind} listener on {host}:{port}')
    while True:
        c, a = srv.accept()
        threading.Thread(target=cls(c, a).run, daemon=True).start()


def main():
    log(f'ROE MODU server starting (bind {CFG["bind"]}, advertise {CFG["advertise_host"]}, open_registration={CFG["open_registration"]})')
    threading.Thread(target=write_status, daemon=True).start()
    threading.Thread(target=serve, args=(CFG['bind'], CFG['game_port'], GameSession), daemon=True).start()
    serve(CFG['bind'], CFG['login_port'], LoginSession)


if __name__ == '__main__':
    main()



