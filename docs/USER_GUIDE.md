# FriDayfree — User Guide

FriDayfree keeps track of the hours you are allowed to charge, the hours you have charged, and the exact
Dayforce cost code string for each of your projects. It runs entirely on your own computer.

- [1. Install](#1-install)
- [2. Start and stop](#2-start-and-stop)
- [3. Where your data lives](#3-where-your-data-lives)
- [4. First-time setup](#4-first-time-setup-5-minutes)
- [5. How do I add allocation (hours) to a project?](#5-how-do-i-add-allocation-hours-to-a-project)
- [6. Your week](#6-your-week)
- [7. Save, Approve, Discard](#7-save-approve-discard)
- [8. The pages](#8-the-pages)
- [9. Backup, restore, move to another computer](#9-backup-restore-move-to-another-computer)
- [10. Command reference](#10-command-reference)
- [11. Update or uninstall](#11-update-or-uninstall)
- [12. Troubleshooting](#12-troubleshooting)

---

## 1. Install

You need **Python 3.10 or newer** (`python3 --version`).

Get the FriDayfree folder (clone it or unzip it), then install it with pip **from that folder** into its
own environment so it cannot disturb your other Python tools:

```bash
cd /path/to/FriDayfree
```

```bash
python3 -m venv ~/.venvs/fridayfree
```

```bash
~/.venvs/fridayfree/bin/pip install .
```

That gives you the command `~/.venvs/fridayfree/bin/fridayfree` and its short alias `~/.venvs/fridayfree/bin/fdf`.
**`fdf` and `fridayfree` are the same program** — wherever this guide says `fridayfree` you can type `fdf`
(`fdf`, `fdf where`, `fdf backup` …).

To be able to type just `fridayfree` or `fdf` from anywhere, add that folder to your PATH once
(macOS / Linux, zsh shown — use `~/.bashrc` for bash):

```bash
echo 'export PATH="$HOME/.venvs/fridayfree/bin:$PATH"' >> ~/.zshrc
```

Open a new terminal and check:

```bash
fdf --version
```

**Alternatives**

| You prefer | Command (run inside the FriDayfree folder) |
|---|---|
| pipx (isolated, PATH handled for you) | `pipx install .` |
| an environment you already have active (conda, mamba, venv) | `pip install .` |
| to edit the source and see changes immediately | `pip install -e ".[dev]"` |

On Windows the environment's programs are in `Scripts` instead of `bin`
(`%USERPROFILE%\.venvs\fridayfree\Scripts\fridayfree.exe`).

The install downloads Streamlit, pandas and Plotly (about 150 MB). After that FriDayfree never needs the
internet.

---

## 2. Start and stop

```bash
fridayfree
```

or simply

```bash
fdf
```

It prints where your data file is, starts a small web server **on your machine only**, and opens
`http://localhost:8501` in your browser. You can run the command from any folder.

**Stop it** with `Ctrl+C` in that terminal. Closing the browser tab does not stop it; reopening
`http://localhost:8501` brings the page back. Your data is written the moment you press Save or Approve,
so stopping is always safe.

If port 8501 is busy: `fridayfree --port 8600`.

---

## 3. Where your data lives

Everything is in **one folder in your home directory**:

| What | Path |
|---|---|
| Data folder | `~/FriDayfree/` (macOS/Linux: `/Users/<you>/FriDayfree` or `/home/<you>/FriDayfree`; Windows: `C:\Users\<you>\FriDayfree`) |
| Database — everything you have **approved** | `~/FriDayfree/fridayfree.db` |
| Intentions — what you have **saved but not approved** | `~/FriDayfree/fridayfree.intentions.json` (exists only while something is pending) |
| Backups made by `fridayfree backup` | `~/FriDayfree/backups/` |
| Error log (only if something crashed) | `~/FriDayfree/app_errors.log` |

The folder is created the first time you start the app. It does **not** depend on which folder you run the
command from, and it is **not** inside the installed package — so updating or uninstalling FriDayfree never
touches your data.

Ask the app at any time:

```bash
fridayfree where
```

**Keeping the data somewhere else** (a synced drive, a project folder, one file per role …):

| Goal | How |
|---|---|
| Different folder, permanently | add `export FRIDAYFREE_HOME="$HOME/Documents/FriDayfree"` to `~/.zshrc` |
| A specific file, permanently | add `export FRIDAYFREE_DB="/path/to/my-hours.db"` to `~/.zshrc` |
| A specific file, just this once | `fridayfree --db /path/to/my-hours.db` |

`FRIDAYFREE_DB` / `--db` wins over `FRIDAYFREE_HOME`. The intentions file, error log and backups folder always
sit next to the database (`my-hours.db` ↔ `my-hours.intentions.json`).

The database is a standard SQLite file and only ever contains approved data. The intentions file is plain,
readable JSON — one entry per number you plan to change — and is deleted automatically as soon as you approve
or discard. Nothing else is stored anywhere (no cloud, no telemetry).

---

## 4. First-time setup (5 minutes)

1. **Fiscal year** — the app opens on this screen the first time. The label `FY26` fills in
   Oct 1 2025 → Sep 30 2026 for you. Press **Create fiscal year**.
2. **Settings → Person / rate** — your name and badge. Hourly rate and FTE are optional; with a rate the
   dashboard also shows dollars.
3. **Allocations → Cost codes → Add a cost code** — paste the string exactly as your timesheet system shows
   it, e.g. `310>PRJ0007788 - EXAMPLE CAMPAIGN – GAMMA>General>PT00321: Modelling` (an invented example).
   FriDayfree deciphers it (PRJ0007788 · EXAMPLE CAMPAIGN – GAMMA · PT00321 · Modelling) and stores it untouched.
4. **Add projects to it** — on the cost code's card type your own tag (e.g. `gamma_main`) and press
   **Add project**. One project has exactly one string; one string can serve many projects.
   (*Allocations → Projects* does the same in one step: tag + string.)
5. **Give the projects hours** — see the next section.

---

## 5. How do I add allocation (hours) to a project?

A new project starts with **0 hours**. Open **Allocations → Funds** (the same columns are also in the
Dashboard grid):

1. Find the project's row.
2. Double-click its **Allocated** cell, type the total hours it should have (e.g. `120`), press Enter.
   The *Available* column and the dashboard update immediately so you can see the effect.
3. Press **Approve**. The hours are now in the system.

Later changes work the same way — always type the **final number**:

| Situation | What to type (then Approve) |
|---|---|
| New funds arrived (+40 h on a 100 h project) | **Allocated** → `140` |
| Funds were removed | **Allocated** → the new lower number |
| Move 10 h from project A to B | A **Allocated** −10, B **Allocated** +10, approve together |
| Hold 40 h for a conference | **Reserved** → `40` (write "conference" in *Note* if you like) |
| The conference week has come | **Reserved** → `0`; the hours are chargeable again |
| 60 h were frozen | **Frozen** → `60` |
| Freeze lifted | **Frozen** → `0` |

**Available = Allocated − Spent − Reserved − Frozen.** Reserved and frozen hours are listed under
*Held — do not charge these hours* until you set them back to 0.

Colours: 🟢 more than 30 % left · 🟠 10–30 % · 🔴 under 10 % or overdrawn · ⚪ nothing allocated.

---

## 6. Your week

**Any day — plan.** On the **Dashboard** (or *Weekly spending → Log hours*) type the hours you intend to
charge in the **Hours · wk of …** column and press **Save**. These are *intentions*: they are written to the
JSON file, survive restarts, show up in the dashboard totals marked ✎, and are **not** in the system.
Change them as often as you like; each Save replaces the previous plan.

**While filling in your timesheet.** Press **Copy cost code** next to a project and paste the string.

**Once, when the week is settled — approve.** Press **Approve**. Everything saved and unsaved goes into the
system in one step and the intentions file is emptied.

It is **one total per project per week**. Made a mistake after approving? Type the correct total and approve
again. To remove an entry, type `0`. Another week: pick it in the *Week* box.

---

## 7. Save, Approve, Discard

You always type **the final number you want** — never "+20" or "−3". FriDayfree works out the difference.

| Button | Meaning |
|---|---|
| *(just typing)* | **Unsaved.** Totals on the page update so you can see the effect, but nothing is stored. Lost if you close the browser. |
| **Save** | Stored as your **intention** in `fridayfree.intentions.json`. Still there after a restart. **Not in the database, not in the system.** |
| **Approve** | **Now it is in the system** (written to the database). Approves everything saved *and* unsaved in one go and empties the intentions file. |
| **Discard** | Forgets saved and unsaved changes. Approved data is never affected. |

While anything is unsaved or unapproved you see a yellow reminder in the sidebar, a ✎ in the grid's
*Pending* column, and a banner on the dashboard. The dashboard shows the **final state including your
intentions**; switch on **Show approved only** to see what is officially in the system.

Red messages block Save/Approve (for example reserved + frozen larger than the allocation). Yellow warnings
(overdrawn, or charging into held hours) do not block — you may need to record what really happened.

**Nothing approved is ever changed or deleted.** Behind the scenes every approval adds signed lines:
allocation 100 → 120 → 90 is stored as `+100`, `+20`, `−30`; a week 8 → 5 → 0 as `+8`, `−3`, `−5`.
You normally never see these — only the resulting totals. They are on *Allocations → History* if you
need an audit trail. A note/reason is always optional.

---

## 8. The pages

| Page | Use it for |
|---|---|
| **Dashboard** | **Panels you switch with *Show*: All panels · Total · Cost codes · Projects** — available hours in total, per cost code (with copy buttons and a spent bar) and per project (what can I charge, held, overdrawn) · the editing grid · cost code and project summaries (with $ when you set a rate) · charts: weekly burn, available by project, cumulative spend vs allocation with an end-of-year projection from your last 4 completed weeks |
| **Allocations → Funds** | The grid with only Allocated / Reserved / Frozen — add, remove, reserve and freeze hours |
| **Allocations → Cost codes** | Add a cost code (paste the string) · add projects to it · copy button · edit its display name and notes |
| **Allocations → Projects** | Add a project (tag + string), rename, set status *active / completed / cancelled*, copy its string. A project can be deleted only while nothing is recorded or planned on it; otherwise set it to *cancelled* (hidden unless you switch on *Show cancelled*) |
| **Allocations → History** | Every approval, newest first, collapsed; open one to see its signed lines. Filter by cost code or project |
| **Weekly spending → Log hours** | The hours-only grid with the week's total |
| **Weekly spending → Spending history** | One line per project per week; *Corrections behind an entry* shows how a number was amended |
| **Tasks** | A light to-do list, optionally linked to a project, with due dates |
| **Settings** | Fiscal years · your name, badge, rate, FTE |

The **Fiscal year** box in the sidebar switches years. Each year has its own projects and strings
(the same string can be added again in a new year).

Every table has **Export as markdown**: a copyable block and a **Download .md** button.

---

## 9. Backup, restore, move to another computer

```bash
fridayfree backup
```

writes `~/FriDayfree/backups/fridayfree-YYYYMMDD-HHMMSS.db` (plus a copy of the intentions file when something is
pending). It is safe while the app is running.
Send it elsewhere with `fridayfree backup --to ~/Dropbox/fridayfree-backups`.

Copying `~/FriDayfree/fridayfree.db` by hand works too (stop the app first).

**Restore / move:** stop the app, put the backup file at `~/FriDayfree/fridayfree.db` (rename it to exactly
that), start the app. On a new computer: install FriDayfree, then copy that one file across.

---

## 10. Command reference

| Command | What it does |
|---|---|
| `fridayfree` · `fdf` (or `fridayfree run`) | start the app and open the browser |
| `fridayfree --port 8600` | use another port |
| `fridayfree --no-browser` | start without opening a browser window |
| `fridayfree --db FILE <command>` | use another database file for this command |
| `fridayfree where` | print the data folder, database and error-log paths |
| `fridayfree backup [--to FOLDER]` | write a dated copy of the database |
| `fridayfree demo` | fill an **empty** database with demo data to explore (refuses if you already have data) |
| `fridayfree --version` · `fridayfree --help` | version · help |

Every command also works as `fdf …`. Options such as `--db` and `--port` go **before** the command: `fdf --db test.db demo`.

Try the demo without touching your real data:

```bash
fridayfree --db /tmp/fridayfree-demo.db demo
```

```bash
fridayfree --db /tmp/fridayfree-demo.db
```

---

## 11. Update or uninstall

Update — get the new FriDayfree folder, then:

```bash
~/.venvs/fridayfree/bin/pip install --upgrade /path/to/FriDayfree
```

Uninstall:

```bash
~/.venvs/fridayfree/bin/pip uninstall fridayfree
```

After an update just start the app: an older database is upgraded automatically the first time (a safety copy
named `fridayfree-before-upgrade-….db` is put in `backups/` first, and anything you had saved but not approved
is moved into the intentions file).

Neither touches `~/FriDayfree/`. Delete that folder yourself only if you really want your data gone.

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: fridayfree` (or `fdf`) | Use the full path `~/.venvs/fridayfree/bin/fridayfree`, or add that folder to PATH (section 1) and open a new terminal |
| Browser did not open | Go to `http://localhost:8501` yourself |
| "Port 8501 is already in use" | Another copy is running — use it, stop it with `Ctrl+C`, or start with `--port 8600` |
| pip fails with an SSL/certificate error | You are behind a proxy; ask IT for the pip proxy/certificate settings, or install from a network without one |
| "Something went wrong" on a page | Your data is safe. The details are in `~/FriDayfree/app_errors.log` |
| The *Hours* column is missing | Fill in *Settings → Person / rate* for that fiscal year |
| A project shows 0 h available | It has no allocation yet — *Allocations → Funds*, type **Allocated**, **Approve** (section 5) |
| Cannot delete a project | Hours are recorded or planned on it — set its status to *cancelled* instead |
| Copy button says "Copy failed" | Select the string in the grey box next to it and copy it manually |
| I approved a wrong number | Type the right number and approve again; the correction is recorded, the total is right |
