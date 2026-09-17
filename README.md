# FriDayfree

Local, single-user tracker for cost code allocations and weekly hours — with a **Copy cost code** button
that gives you the exact Dayforce string for each of your projects. Runs on your own computer; nothing
leaves it.

**Full user documentation: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

## Install (pip, local)

Python 3.10+ is required. From inside this folder:

```bash
python3 -m venv ~/.venvs/fridayfree
```

```bash
~/.venvs/fridayfree/bin/pip install .
```

```bash
echo 'export PATH="$HOME/.venvs/fridayfree/bin:$PATH"' >> ~/.zshrc
```

(`pipx install .` or `pip install .` into an environment you already use work as well.)

## Run

```bash
fridayfree
```

or the short alias — same program:

```bash
fdf
```

It opens `http://localhost:8501`. Stop with `Ctrl+C`. It can be started from any folder.

| Command | |
|---|---|
| `fdf` / `fridayfree` | start the app |
| `fdf where` | show where your data is |
| `fdf backup [--to FOLDER]` | dated copy of the database (safe while running) |
| `fdf demo` | demo data into an **empty** database |
| `fdf --port 8600` · `fdf --db FILE …` · `fdf --no-browser` | options (before the command) |

## Where the data is saved

| | |
|---|---|
| Data folder | `~/FriDayfree/` — created on first start, independent of where you run the command and of the installed package |
| Database | `~/FriDayfree/fridayfree.db` — everything you have **approved** |
| Plan | `~/FriDayfree/fridayfree.intentions.json` — the week's hours you **saved but have not approved** (plain JSON, never in the database; removed once approved or discarded) |
| Backups | `~/FriDayfree/backups/` |
| Error log | `~/FriDayfree/app_errors.log` |

Change it with `FRIDAYFREE_HOME=/folder`, `FRIDAYFREE_DB=/file.db`, or `--db FILE`.
Updating or uninstalling never touches this folder.

## How it works in one minute

1. **Funds → Cost codes**: add a cost code — the pot of funds. You type every field: name, the full string to
   copy, PRJ/PT codes (offered from the string, editable), optional expiry, notes.
2. On its card, add the **projects** that draw from it (`beta_main`, `beta_travel` …).
3. **Funds → Adjust funds**: pick a project, pick **Allocate · Deallocate · Reserve · Unreserve · Freeze ·
   Unfreeze**, type the hours, press the button — which reads *“Allocate 40 h to beta_main”*. It is recorded
   at once. To undo, do the opposite action (there is an **Undo** shortcut).
4. **This week**: one hours box per project. **Save plan** during the week (kept in a JSON file, not the
   database), **Approve week** when it is settled. **Copy code** pastes the cost code into your timesheet.
5. **Dashboard**: what is available in total, per cost code and per project — switch panels or see them all.
6. **Settings → Carry forward**: at the end of the year, rebuild everything in the new year with what is left.

Nothing is ever edited or deleted: every change is a new signed line (`+100`, `+40`, `−20`), and you only see
the totals. The lines are under History.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/pytest
```

Design docs: [REQUIREMENTS.md](REQUIREMENTS.md) · [ARCHITECTURE.md](ARCHITECTURE.md)
