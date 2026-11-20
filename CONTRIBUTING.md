# Contributing

Thanks for helping keep Rubies of Eventide playable.

## Ground rules
* **No game assets or code.** Do not add client binaries, models, textures, sounds, icons, disassembly dumps or decompiled code. Link to
  nothing that redistributes them either.
* **Localhost stays the default.** Public hosting must remain opt-in (`bind` 127.0.0.1, `advertise_host` localhost).
* **No secrets or player data.** `accounts.json`, `characters.json`, `config.json`, logs and Cloudflare credentials are gitignored; keep it that way.
* Be honest in docs about what is verified in the real client and what is a guess.

## Workflow
1. Fork, branch, change.
2. `python -m unittest discover -s tests -v` must pass (it needs no game client).
3. If you decoded a new message, add it to `docs/PROTOCOL.md`, mark it *verified* or *guess*, and add a builder + a size/field test.
4. Open a pull request describing how you verified it (screenshot or log excerpt is ideal).

## Good first tasks
Which `0xD2` object kind renders as a monster; the in-world avatar's race field; monster level; item type numbers; character deletion;
combat and death messages (so respawns trigger from real kills); other zones' spawn points and travel messages.
