# ROE MODU

An open-source **server and control panel for Rubies of Eventide 0.95**, the 2003 Lithtech MMORPG whose official servers have been shut down.

* **`roe_server.py`** - a clean-room login + game server written from what the real client sends and expects.
* **`roe_modu.pyw`** - ROE MODU, a Windows control panel (tkinter, standard library only): start/stop the server, **PLAY** on localhost in one click,
  manage accounts and characters, see the live **player count**, and optionally publish through a free Cloudflare Tunnel.
* Documentation of the wire protocol and the reverse-engineering method, plus the helper scripts, so others can extend it.

> **Unofficial.** Not affiliated with, endorsed by, or connected to the original developers or operators of Rubies of Eventide.
> **No game files are included**; you need your own copy of the 0.95 client. The original operators have stated that they do not license
> personal servers - running one is your decision and responsibility. Keep it non-commercial. The MIT license covers this repository's code only.

## What works today
Login with real (hashed) accounts, server list with player count, character creation (name check, race/looks, class, attribute and skill points),
character select, entering zone 1100 with the full HUD, a keepalive so the client stays connected, level-1 goblin spawns with a 5-minute respawn
timer, and a starter kit message. See **Limitations** below - this is a work in progress, not the original game.

## Requirements
* Windows 10/11 (the game client and the control panel are Windows-only; the server itself is plain Python and runs anywhere)
* Python 3.10+ with tkinter (the standard Windows installer includes it)
* Rubies of Eventide **0.95** installed (default `C:\Program Files (x86)\Rubies of Eventide`)

## Install and run
```
git clone https://github.com/YOUR-USERNAME/roe-modu.git
cd roe-modu
pythonw roe_modu.pyw
```
Press **PLAY**. ROE MODU starts the server, points the client at `127.0.0.1` (one administrator prompt the first time, because the client reads the
address from the registry) and launches the game **windowed**. In the game, log in with any account name and password (new names create the account
while *open registration* is on), pick the server, create a character and **Enter Game**.

Server only (any OS): `python roe_server.py`. Settings live in `config.json` (copy `config.example.json`). Run the tests with
`python -m unittest discover -s tests -v`.

## Repository layout
| Path | What |
|---|---|
| `roe_server.py`, `roe_store.py`, `roecrypt.py` | Server, data layer (config/accounts/characters), stream cipher |
| `roe_modu.pyw` | ROE MODU control panel |
| `docs/PROTOCOL.md` | The wire protocol as observed |
| `docs/REVERSE-ENGINEERING.md`, `tools/reverse-engineering/` | How it was figured out, and the helper scripts |
| `launcher-legacy/` | The original PowerShell "ROE:MOD" launcher (superseded by ROE MODU) |
| `tests/` | Unit tests (no game client needed); CI runs them on every push |
| `CLAUDE.md` | Project notes for Claude Code / AI assistants working in this repo |

The rest of this README is the detailed guide.

## Files in the working folder (runtime data)

| File | Purpose |
|---|---|
| `roe_modu.pyw` | The ROE MODU control panel (Play, Accounts, Characters, Public/Cloudflare, Content, Log). |
| `roe_server.py` | The server (login port 3142, game port 3143). |
| `roe_store.py` | Config + hashed accounts + characters (JSON files, written atomically). |
| `roecrypt.py` | The client's stream obfuscation (reverse-engineered). |
| `config.json` | Server settings (bind address, ports, advertised host, open registration). |
| `accounts.json`, `characters.json` | Your data. Back these up. |
| `server.log`, `status.json` | Log and live status (player count) read by ROE MODU. |

## Accounts and characters

* **Accounts tab**: create accounts, set passwords, delete. Passwords are stored as salted PBKDF2-SHA256 hashes.
* **Open registration** (Accounts tab): ON = logging in with an unknown name creates it (fine solo). **Turn it OFF for any
  public server** and create accounts yourself.
* **Characters tab**: lists every character; delete from here.
* Character creation works in-game: name check, race/sex/looks, class, attribute + skill points. The creation record is stored
  exactly as the client sends it and replayed in the character list.
* Logins are rate-limited (6 failures/minute per address by default, `max_login_failures_per_minute`).

## Making it a public server (with VS Code + Claude Code)

### Read this first
* The original operators have said they do not license personal servers. Whether to run one is your decision; keep it
  non-commercial, do not redistribute the game client, and don't claim any affiliation.
* **The wire protocol is not secure.** The client's "encryption" is a fixed obfuscation whose keys are public, so a
  password sent over a raw TCP port is effectively plain text. Never ask players to reuse real passwords. Prefer the
  Cloudflare Tunnel route below, which wraps the traffic in TLS between each player and Cloudflare.
* The server has no admin/GM tools, no anti-cheat, and trusts the client for movement. Treat it as a hobby server.

### Route A (recommended, free): Cloudflare Tunnel
Cloudflare **Workers / `wrangler` deployments cannot be used**: the game speaks raw TCP and Workers cannot accept inbound
raw TCP. A **Cloudflare Tunnel** (`cloudflared`) can carry it, on the free plan, with no port forwarding.
Requirements: a free Cloudflare account and a domain whose DNS is on Cloudflare.

On the **host PC** (the one running the server):

1. ROE MODU -> **Public / Cloudflare** -> **Download cloudflared** (from `github.com/cloudflare/cloudflared`).
2. In a terminal (VS Code: *Terminal -> New Terminal*), from the `tools` folder next to `roe_modu.pyw`:
   ```
   cloudflared tunnel login
   cloudflared tunnel create roe-modu
   cloudflared tunnel route dns roe-modu roe-login.YOURDOMAIN.com
   cloudflared tunnel route dns roe-modu roe-game.YOURDOMAIN.com
   ```
   `create` prints the tunnel ID and the path of its credentials file (`C:\Users\<you>\.cloudflared\<ID>.json`).
3. In ROE MODU fill **Tunnel name** (`roe-modu`), **Credentials .json**, **Login hostname**, **Game hostname**, then
   **Write tunnel config** and **Start tunnel**.
4. Keep the server settings on the safe defaults: *Listen on* `127.0.0.1`, *Advertised host* `localhost`
   (the tunnel connects to the server locally). Turn **Open registration OFF** and create player accounts.

On **each player's PC** (they only need the normal game client + `cloudflared.exe`; they can also use ROE MODU):
```
cloudflared access tcp --hostname roe-login.YOURDOMAIN.com --url localhost:3142
cloudflared access tcp --hostname roe-game.YOURDOMAIN.com  --url localhost:3143
```
Leave both running, then in ROE MODU -> **Play -> Join someone else's server** enter `127.0.0.1` -> **Join server**.
(The server list tells the client to use `localhost:3143` for the game connection, which is exactly the second command.)

### Route B: direct (port forwarding or a VPS)
1. Public tab: *Listen on* `0.0.0.0`, *Advertised host* = your public DNS name or IP, **Save**, then **Restart server**.
2. Allow inbound **TCP 3142 and 3143** in Windows Firewall and forward them on your router (or open them on the VPS).
3. Players: **Join someone else's server** -> your DNS name/IP.
4. Remember the security note above: this exposes obfuscated-but-readable traffic to the internet.

### Doing it with Claude Code in VS Code
1. Install the **Claude Code** extension in VS Code and sign in.
2. `File -> Open Folder...` -> the cloned `roe-modu` folder. The included `CLAUDE.md` gives Claude Code the
   project rules and protocol notes automatically.
3. Paste prompts like these into the Claude Code panel:
   * *"Read README.md and walk me through Route A. Run each cloudflared command in the terminal and explain the output."*
   * *"Turn off open registration, then add accounts for these players: ..."*
   * *"Server players can't connect. Read server.log and tunnel.log and tell me why."*
   * *"Add a Windows Task Scheduler entry that starts roe_server.py and the tunnel when I log in."*
   * *"Back up accounts.json and characters.json to a dated folder every night."*
4. Review every command Claude Code proposes before approving it, especially anything that opens ports or changes the firewall.

## Settings reference (`config.json`)

| Key | Default | Meaning |
|---|---|---|
| `bind` | `127.0.0.1` | Interface the server listens on (`0.0.0.0` = all). |
| `login_port` / `game_port` | `3142` / `3143` | The client hard-codes login port 3142. |
| `advertise_host` | `localhost` | Host the client is told to use for the game connection. |
| `open_registration` | `true` | Unknown login names create accounts. |
| `max_login_failures_per_minute` | `6` | Per-address login throttle. |
| `start_zone`, `start_pos` | `1100`, spawn coordinates | Where characters enter the world. |
| `keepalive_seconds` | `30` | The client disconnects after 90 s of server silence; this prevents it. |
| `spawns` | six level-1 goblins | Monsters placed around the start point (see *New content*). |
| `respawn_seconds` | `300` | Dead monsters return after this many seconds (5 minutes). |

## Protocol notes (for contributors)

TCP, packets are `[s16 total_len][u16 type][payload]`, whole stream obfuscated with `roecrypt.Stream`
(client->server key *"You know who lives in his own world."*, server->client key *"You know who is a blithering moron."*).

| Type | Direction | Meaning |
|---|---|---|
| `0x65` | C->S | Login (account[17], password[51], version) / game auth (adds the 16-byte token) |
| `0x66` / `0x67` | S->C | Login OK + token / login error text (on the game link `0x67` is a no-op used as keepalive) |
| `0x2778` -> `0x2779`,`0x2776`,`0x277c`,`0x2784` | | Server list, entry (host, port), status (0 = OPEN), player count |
| `0x277c` -> `0x277e` | | Server chosen / accepted |
| `0x67` -> `0x6b`,`0x6c`...,`0x6d` | | Character list request / begin / entries / end |
| `0xe7` -> `0x142` | | Name check -> verdict (flag byte + text, 508 bytes) |
| `0x6c` + `0x98` -> `0x76` | C->S, S->C | Create character (identity/appearance + skills) -> success |
| `0x6a` -> `0x73`,`0x89`,`0xf4`,`0x91`,`0xd2`,`0xf3` | | Enter world: InitGame, zone load, run world, zone ready, player object, player stats |
| `0x74` | C->S | Movement updates (zone, x, y, z, ...) |

The client runs each zone's world locally inside `Lithtech.exe`; the server only feeds game state.

## New content (authored, not the original game's)

**Monsters** - `config.json` -> `spawns` and `respawn_seconds` (default 300 = **5 minutes**). The default is six level-1 goblins
placed around the start point. Monster model ids live in 76-129 (found in the server shell): 76 goblin, 77 kobold, 78 imp, 79 wolf,
80 boar, 81 bear, 82 tiger, 83 snake, 90 spider, 94 werewolf, 97 troll, 108 skeleton, 110 dire kobold, 111 hobgoblin, 112 rat,
114 lizardman, 120 hill giant, 121 stone troll... Example entry:
`{"name": "Goblin", "model": 76, "level": 1, "kind": 1, "count": 6, "radius": 700}`. The level is shown in the name ("Goblin (Lv 1)").
When a monster dies the server removes it (`0xD4`) and re-adds it after `respawn_seconds`. Combat is not decoded yet, so to test the
timer put a monster uid (2001-2006) or the word `all` into a file called `kill.txt` in this folder; the next second it "dies".
`kind` (0/1/2) selects which world-object class the client builds; **which kind renders as a monster still has to be confirmed in game**.

**Starter kit** - `STARTER_KIT` in `roe_server.py`: Iron Longsword, Steel Dirk, Studded Leather Chest, Round Wooden Shield, Flask of Mead,
sent through the inventory-add message (`0xFE`) using real icons from `rez\Interface\Icon\Item`. Item *type* numbers (0-10) are guesses
until verified in game.

**Start point** - zone 1100 `StartPoint0` (-32576, 352, 28664), now facing away from the rocks (yaw pi).

## Limitations (what is NOT restored)

* **No NPCs, monsters, items, quests, shops, doors/switches, marks/flags or town populations.** The original spawn tables,
  stats, loot, quest scripts and item definitions were server-side and are not in the client. They would have to be
  **authored** (the *Content* tab lists the models, icons, zones and info pages the client does provide).
* Only zone 1100 is wired up. Other zones exist in the client (`rez\Worlds`) but need spawn points and travel messages.
* Character deletion and some character-screen buttons are not implemented yet.
* Vitals are derived from the creation screen's own formulas; skills/inventory are not yet sent to the in-game UI.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Lost focus exiting game" | Use windowed mode (ROE MODU default). |
| "Connection lost from server" after ~90 s | Update to this server version (keepalive) and restart it. |
| "Login server unavailable" | Server not running -> press PLAY / Start server; or wrong login address. |
| Stuck on "Requesting name verification" | Old server version; restart the server. |
| Game won't start | Install the client at `C:\Program Files (x86)\Rubies of Eventide` or set the folder in `modu.json`. |


