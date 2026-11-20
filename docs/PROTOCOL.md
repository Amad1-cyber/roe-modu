# Rubies of Eventide 0.95 wire protocol (as observed)

Everything here was learned by observing the 0.95 client (a debug build, so its behaviour is readable) and by capturing what it
sends. It is **not** official documentation and may be incomplete or wrong in places. Offsets below are message offsets
**including the 4-byte header** unless stated otherwise.

## Transport and framing
* Plain TCP. Two kinds of server: the **login server** (the client always connects to port **3142** on the registry's `LoginServer`
  host) and the **game server** (host and port come from the server-list entry; this project uses 3143).
* Every packet: `s16 total_length` (includes the 4 header bytes) | `u16 type` | payload.
* The whole stream, both directions, is obfuscated by a stateful "autokey" stream cipher (`roecrypt.py`). Header and body are
  decrypted as one continuous stream.

## The stream cipher
Two keys, one per direction (the strings are constants in the client):
* client -> server: `You know who lives in his own world.`
* server -> client: `You know who is a blithering moron.`

Key preparation: `S = sum(signed bytes of key)`; fold the four bytes of `S` into one byte (`(S>>24)+((S>>16)&255)+((S>>8)&255)+(S&255)) & 255`);
every key byte becomes `byte ^ S ^ 0x12`.
Encrypt each byte `p`: `c = nibble_swap(p) ^ state ^ (key[pos] ^ 0xA8)`; then `state = c`, `key[pos] ^= c`, `pos = (pos+1) % len(key)`.
Decrypt is the exact inverse. Because the keys are public constants this is obfuscation, **not** security.

## Login connection (port 3142)
| Type | Dir | Payload |
|---|---|---|
| `0x65` | C->S | `account[17]`, `password[51]`, `u32 clientVersion` at +68 (95 for 0.95) |
| `0x66` | S->C | `token[16]`, `u32 accountId` - login accepted |
| `0x67` | S->C | `text[500]` - login refused, shown on the login screen |
| `0x2778` | C->S | request server list |
| `0x2779` | S->C | `u32 ?`, `u32 count` |
| `0x2776` | S->C | server entry: `u32 id`, `host[100]` (also what the client connects to; the part before the first `.` is displayed), `u32 gamePort`, `u32 ?`, `u32 ?` |
| `0x277c` | S->C | `u32 id`, `u32 status` (0 = OPEN, otherwise "Offline") |
| `0x2784` | S->C | `u32 id`, `u32 playerCount` |
| `0x277c` | C->S | `u32 id` - user pressed Connect |
| `0x277e` | S->C | `u32 id`, `u32 accepted` - then the client opens the game connection |

## Game connection
| Type | Dir | Meaning |
|---|---|---|
| `0x65` | C->S | auth: account, password, the 16-byte token from `0x66`, version |
| `0x66` | S->C | auth OK -> client shows character select |
| `0x67` | C->S | `u32 1` - request character list |
| `0x6b`, `0x6c`*, `0x6d` | S->C | list begin / entries (56 bytes each) / end |
| `0xe7` | C->S | name check `first[18]`, `last[18]` |
| `0x142` | S->C | verdict: `u8 ok` + `text` (508-byte message) |
| `0x6c` | C->S | create: 56-byte record: `first[17]`, `sex`, `?`, `race`, `STR`, `INT`, `DEX`, `CON`, `last[20]`... |
| `0x98` | C->S | create: 228-byte skills record |
| `0x76` | S->C | create result, success flag at message byte +0x15 (`0x77` = failure with text) |
| `0x6a` | C->S | `name[24]` - enter world with this character |
| `0x73` | S->C | UI state -> InitGame. **Required before the zone load or the HUD is not built** |
| `0x89` | S->C | zone load: `u32 zone`, 4 floats (x, y, z, facing), 2 flag bytes |
| `0xf4` | S->C | run the world (client starts its local world server) |
| `0x91` | S->C | zone ready (hides the "Loading Zone" dialog) |
| `0xd2` | S->C | add world object (360 bytes): uid +4, x/y/z floats +8/+0xc/+0x10, model id +0x18 (monsters 76-129), kind +0x2c, name +0x3c |
| `0xd4` | S->C | remove world object `u32 uid` |
| `0xf3` | S->C | player state (700 bytes), flag dword at +4 enabling fields (HP/BP/MP/EP at +0x2c/+0x30/+0x38/+0x34, level +0x3c, name +8) |
| `0xfe` | S->C | inventory add (452 bytes): id +4, type +0x10 (<=10), name +0x14 (50), icon +0x46 (`item/<icon>_16.dtx`) |
| `0x74` | C->S | movement: `u32 zone`, x, y, z, ... (y is height) |
| `0x67` | S->C | no-op handler in the client; used as a **keepalive** |

Other things worth knowing:
* The client disconnects after **90 s** without any server message, so a keepalive every ~30 s is required.
* Zones run **locally** inside `Lithtech.exe` (it embeds the Lithtech server). The remote server only supplies game state.
* A `0x6c` list entry is 56 bytes: `name[20]`, `u32` x4 (the first is the **class index**, alphabetical: 0 Adventurer, 1 Alchemist, 2 Archer...), `u16`, 4 bytes, 2 pad bytes, `u32` x2.
* Monster model ids (0xD2 +0x18): 76 goblin, 77 kobold, 78 imp, 79 wolf, 80 boar, 81 bear, 82 tiger, 83 snake, 90 spider, 94 werewolf,
  97 troll, 108 skeleton, 110 dire kobold, 111 hobgoblin, 112 rat, 114 lizardman, 120 hill giant, 121 stone troll (76-129 in total).

## Known gaps
Which `0xd2` object kind (0/1/2) draws as a monster, the field holding race for the in-world avatar, the level field of monsters,
the type numbers of inventory items, combat, chat, trade, and every message not listed above.
