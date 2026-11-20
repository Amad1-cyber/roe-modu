# Reverse-engineering helpers

Small analysis scripts used to work out the protocol from your own installed client (`C:\Program Files (x86)\Rubies of Eventide`).
Requires `pip install pefile capstone`. Each script's first argument is a directory to put on `sys.path` for those packages
(pass `.` if they are installed normally). See `docs/REVERSE-ENGINEERING.md` for the workflow.

| Script | Purpose |
|---|---|
| `imports.py` | List imports/exports of the client DLLs (finds networking APIs). |
| `crypto_scan.py` | Scan a binary for well-known crypto constants (rules out standard ciphers). |
| `dis.py` | Disassemble an address range with thunk/string annotations: `dis.py LIBS DLL START END`. |
| `annot.py` | Same, but also maps `[ebp-K]` locals to message offsets: `annot.py LIBS START END BASE_K`. |
| `callers.py` / `xref_all.py` | Find direct callers of an address / any absolute reference to it. |
| `dispatch_table.py`, `find_ctor.py` | Extract the game-message handler table (type -> handler). |
| `states.py` | Map `GameStateHandler` state constants to the functions that set them. |
| `charhandlers.py`, `connlost.py`, `sockcalls.py`, `ninety.py` | Targeted searches used for specific questions. |
| `gob_ids.py` | Resolve the monster model-id table from the server shell. |
| `decode_create.py` | Decode captured character-creation records from `server.log`. |

Some scripts have the client path and the load addresses hard-coded for the 0.95 build; adapt them if your install differs.
**Do not commit disassembly output, game binaries or assets.**
