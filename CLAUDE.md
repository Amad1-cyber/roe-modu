# ROE MODU - project notes for Claude Code

This folder is a community server for **Rubies of Eventide 0.95** (Lithtech engine, 2004) and its control panel.

## Rules
* **Localhost is the default** (`bind` 127.0.0.1, `advertise_host` localhost). Never change the default to public; public hosting is opt-in via the Public tab / `config.json`.
* Never publish, upload or commit `accounts.json`, `characters.json`, `config.json`, `tunnel.log`, Cloudflare credentials (`*.json` in `.cloudflared`) or the game files.
* Ask before opening firewall ports or editing the registry. The client's login address is `HKLM\SOFTWARE\WOW6432Node\Cyber Warrior\LithtechRubies\LoginServer` (needs admin).
* The wire "encryption" is a public-key obfuscation: treat passwords as sent in the clear unless tunnelled (Cloudflare Tunnel).

## Layout
* `roe_server.py` server - `roe_store.py` data layer - `roecrypt.py` stream cipher - `roe_modu.pyw` tkinter control panel.
* Logs: `server.log` (server), `tunnel.log` (cloudflared). Live status: `status.json`.

## Protocol essentials
Frames `[s16 len incl header][u16 type][payload]`, stream cipher in `roecrypt.py`. Login 3142, game 3143. See README section 6 for the message table.
Hard-won facts: the client disconnects after 90 s without any server message (keepalive = no-op type 0x67 every 30 s); the HUD only builds if the server sends 0x73 (InitGame) before the zone load; zones run locally in Lithtech.exe; fullscreen quits on focus loss (use windowed).

## Reverse-engineering workflow that worked
Disassemble `rez\CShell.dll` (a *debug* build, so it is readable) with capstone/pefile; message handlers are in a 369-slot table (type = (slot_offset - 4)/4, constructor near 0x10237980 in the DLL's preferred base); handlers for LT-engine messages use index (slot + 0x120)/4. Capture real client requests by logging unknown types in `server.log`.

## Not implemented (good next tasks)
NPC/monster/item/quest content (needs authoring), other zones, character deletion, inventory/skills in-game, stats persistence.
