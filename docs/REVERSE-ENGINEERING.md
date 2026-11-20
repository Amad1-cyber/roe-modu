# How the protocol was reverse-engineered

No game code or disassembly is included in this repository; the scripts in `tools/reverse-engineering/` operate on *your own* installed
client. You need Python plus `pip install pefile capstone`. Most scripts take a directory containing those packages as their first
argument (use `.` if they are installed globally).

## What made it tractable
* `rez\CShell.dll` (the client-side game logic) is a **debug build** (MSVC, `/Od`, debug runtime). Functions are not inlined, locals live
  in obvious `[ebp-N]` slots, and strings give every handler a name. That makes static reading practical.
* The DLLs `server.dll`, `Object.lto`, `CShell.dll` and `SRes.dll` all prefer base `0x10000000`, so at run time only one gets it; the
  others are relocated. When you read addresses from a live process, find each module's real base first (`Get-Process` modules from
  32-bit PowerShell).

## Method that worked
1. **Imports first** (`imports.py`): `CShell.dll` imports plain Winsock (`connect`, `send`, `recv`) -> a custom TCP protocol. No standard crypto
   tables (`crypto_scan.py`) -> a homemade cipher.
2. **Find the connect call** from strings such as "Connecting to login server" (`dis.py`, `callers.py`). The port is an immediate (`0xC46` = 3142).
3. **Capture, then decode**: run a listener on the port the client uses and log the first bytes; reproduce the cipher from the disassembly and
   check it against the capture (`tests/test_roe.py` replays a real packet).
4. **Message tables**: the game handlers are a 369-slot function-pointer table filled by one constructor (`dispatch_table.py`, `find_ctor.py`);
   `type = (slot_offset - 4) / 4`. Engine-level messages use `(slot + 0x120) / 4`.
5. **Annotate handlers with message offsets** (`annot.py`): handlers copy the message into a stack struct, so `[ebp - K]` maps to `msg + (base - K)`.
6. **Drive the real client** with scripted input and read the server log to see what it asks for next. Unknown request types are logged by
   `roe_server.py` precisely so they can be decoded this way.
7. **Verify visually** (screenshots) and keep notes; several early guesses were wrong until a real run contradicted them.

## Useful findings (see `docs/PROTOCOL.md` for the message table)
* The state machine lives in a `GameStateHandler` (states: 5 = 3D world, 9 = server select, 11 = char select, 13 = init game, 14 = connection lost).
  `ChangeStateTo3DWorld` only builds the HUD when the previous state is 13 or 4.
* 90-second silence timeout: the network manager compares `now - lastServerMessage` against 90.0 and raises "Connection lost to game server".
* Monster model ids come from a 54-entry jump table in the server shell (`gob_ids.py`).
* Fullscreen mode quits on focus loss ("Lost focus exiting game"); windowed does not.

## Ethics and legality
Interoperability research on software you own, for a game whose servers were shut down. The original operators have stated that they do not
license personal servers; run this at your own discretion, keep it non-commercial, and do not redistribute the game client or its assets.
