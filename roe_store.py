"""ROE MODU shared data layer: config, accounts (salted PBKDF2 hashes) and characters, stored as JSON next to this file.

Used by both the emulator (roe_server.py) and the ROE MODU GUI (roe_modu.pyw), so changes made in the GUI are seen by a
running server immediately (files are re-read on every access and written atomically).
"""
import base64, hashlib, hmac, json, os, re, secrets, threading, time

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, 'config.json')
ACCOUNTS_FILE = os.path.join(BASE, 'accounts.json')
CHARACTERS_FILE = os.path.join(BASE, 'characters.json')
LOG_FILE = os.path.join(BASE, 'server.log')
PBKDF2_ROUNDS = 200_000

DEFAULT_CONFIG = {
    # Where the emulator listens. 127.0.0.1 = this PC only (safe default). 0.0.0.0 = every network adapter (public/LAN).
    'bind': '127.0.0.1',
    'login_port': 3142,
    'game_port': 3143,
    # Host name the client is told to use for the game connection. 'localhost' for solo play; your public DNS name
    # (or IP) for a public server. The part before the first dot is what the server list displays.
    'advertise_host': 'localhost',
    # True: logging in with an unknown account creates it (handy for solo play). False: accounts must be created
    # by the owner in ROE MODU (recommended for a public server).
    'open_registration': True,
    'max_login_failures_per_minute': 6,
    'start_zone': 1100,
    'start_pos': [-32576.0, 380.0, 28664.0, 0.0],
    'keepalive_seconds': 30,
    # Monsters placed around the start point. model: 76 goblin, 77 kobold, 79 wolf, 80 boar, 81 bear, 90 spider, 111 hobgoblin...
    # kind selects the client's world-object class (0/1/2; verify which renders as a monster). Level is shown in the name.
    'spawns': [{'name': 'Goblin', 'model': 76, 'level': 1, 'kind': 1, 'count': 6, 'radius': 700}],
    'respawn_seconds': 300,   # dead monsters come back after 5 minutes
    # Development aid: extra fake characters appended to every list, e.g. [{"name": "A", "bytes": [1, 0, 1, 0]}]
    'experiment_chars': [],
    # Which create-record fields fill the 4 appearance bytes of a character-list entry (see roe_server.py).
    'entry_bytes': ['sex', 'b12', 'race', 'zero'],
}

_lock = threading.RLock()


def _read(path, default):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(_read(CONFIG_FILE, {}))
    return cfg


def save_config(cfg):
    with _lock:
        _write(CONFIG_FILE, cfg)


def _hash(password, salt):
    return base64.b64encode(hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ROUNDS)).decode()


# ---------------------------------------------------------------- accounts
ACCOUNT_RE = re.compile(r'^[A-Za-z0-9_\-]{3,16}$')


def list_accounts():
    with _lock:
        return sorted(v['name'] for v in _read(ACCOUNTS_FILE, {}).values())


def create_account(name, password):
    if not ACCOUNT_RE.match(name):
        raise ValueError('Account names are 3-16 letters, digits, _ or -.')
    if len(password) < 4:
        raise ValueError('Use a password of at least 4 characters.')
    with _lock:
        accounts = _read(ACCOUNTS_FILE, {})
        if name.lower() in accounts:
            raise ValueError('That account already exists.')
        salt = secrets.token_bytes(16)
        accounts[name.lower()] = {'name': name, 'salt': base64.b64encode(salt).decode(), 'hash': _hash(password, salt),
                                  'created': time.strftime('%Y-%m-%d %H:%M:%S')}
        _write(ACCOUNTS_FILE, accounts)


def set_password(name, password):
    with _lock:
        accounts = _read(ACCOUNTS_FILE, {})
        a = accounts.get(name.lower())
        if not a:
            raise ValueError('No such account.')
        salt = secrets.token_bytes(16)
        a['salt'], a['hash'] = base64.b64encode(salt).decode(), _hash(password, salt)
        _write(ACCOUNTS_FILE, accounts)


def delete_account(name):
    with _lock:
        accounts = _read(ACCOUNTS_FILE, {})
        accounts.pop(name.lower(), None)
        _write(ACCOUNTS_FILE, accounts)


def check_login(name, password, allow_create):
    """Return (ok, message, canonical_name)."""
    with _lock:
        accounts = _read(ACCOUNTS_FILE, {})
        a = accounts.get(name.lower())
    if a is None:
        if allow_create:
            try:
                create_account(name, password)
                return True, 'Account created.', name
            except ValueError as e:
                return False, str(e), name
        return False, 'Unknown account. Ask the server owner to create one for you.', name
    salt = base64.b64decode(a['salt'])
    if hmac.compare_digest(_hash(password, salt), a['hash']):
        return True, 'OK', a['name']
    return False, 'Incorrect password.', a['name']


# -------------------------------------------------------------- characters
def all_characters():
    with _lock:
        return _read(CHARACTERS_FILE, {})


def characters_of(account):
    return list(all_characters().get(account.lower(), []))


def name_taken(first, last):
    full = (first + ' ' + last).strip().lower()
    for chars in all_characters().values():
        for c in chars:
            if (c['first'] + ' ' + c.get('last', '')).strip().lower() == full or c['first'].lower() == first.lower():
                return True
    return False


def add_character(account, first, last, record_hex, skills_hex=''):
    with _lock:
        data = _read(CHARACTERS_FILE, {})
        chars = data.setdefault(account.lower(), [])
        if len(chars) >= 8:
            raise ValueError('An account can hold at most 8 characters.')
        chars.append({'first': first, 'last': last, 'record': record_hex, 'skills': skills_hex,
                      'created': time.strftime('%Y-%m-%d %H:%M:%S')})
        _write(CHARACTERS_FILE, data)


def delete_character(account, first):
    with _lock:
        data = _read(CHARACTERS_FILE, {})
        data[account.lower()] = [c for c in data.get(account.lower(), []) if c['first'].lower() != first.lower()]
        _write(CHARACTERS_FILE, data)
