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
| Intentions | `~/FriDayfree/fridayfree.intentions.json` — what you have **saved but not approved** (plain JSON, never in the database; removed once approved or discarded) |
| Backups | `~/FriDayfree/backups/` |
| Error log | `~/FriDayfree/app_errors.log` |

Change it with `FRIDAYFREE_HOME=/folder`, `FRIDAYFREE_DB=/file.db`, or `--db FILE`.
Updating or uninstalling never touches this folder.

## How it works in one minute

1. Create the fiscal year → Settings → Person → **Allocations → Cost codes**: paste a string such as
   `205>PRJ0004321 - DEMO PROGRAM – BETA>General>PT00890: Field Work` (invented example) and add projects to it
   by tag (`beta_main`, `beta_travel` …). Several projects can share a string.
2. **Allocations → Funds**: type each project's **Allocated** hours → **Approve**. Same place to remove,
   reserve or freeze hours — always type the *final number you want*.
3. During the week type the **Hours** you intend to charge and **Save** — intentions go to a JSON file, not the
   database. When the week is settled press **Approve**: everything goes into the system at once.
4. The **Dashboard** shows what is available in total, per cost code and per project — switch panels with
   *Show*, or see them all at once — each with a **Copy cost code** button.
5. Hours are **append-only**: additions are positive rows, removals negative rows; the database refuses to
   change or delete them. You see only the resulting totals; the trail is under Allocations → History.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/pytest
```

Design docs: [REQUIREMENTS.md](REQUIREMENTS.md) · [ARCHITECTURE.md](ARCHITECTURE.md)
