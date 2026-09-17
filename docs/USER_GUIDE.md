# FriDayfree — User Guide

FriDayfree keeps track of the hours you are allowed to charge, the hours you have charged, and the exact
Dayforce cost code string for each of your projects. It runs entirely on your own computer.

- [1. Install](#1-install)
- [2. Start and stop](#2-start-and-stop)
- [3. Where your data lives](#3-where-your-data-lives)
- [4. First-time setup](#4-first-time-setup-5-minutes)
- [5. Funds: allocate, deallocate, reserve, freeze](#5-funds-allocate-deallocate-reserve-freeze)
- [6. Your week](#6-your-week)
- [7. What is saved when](#7-what-is-saved-when)
- [8. The pages](#8-the-pages)
- [9. End of year: carry forward](#9-end-of-year-carry-forward)
- [10. Backup, restore, move to another computer](#10-backup-restore-move-to-another-computer)
- [11. Command reference](#11-command-reference)
- [12. Update or uninstall](#12-update-or-uninstall)
- [13. Troubleshooting](#13-troubleshooting)

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
2. **Settings → Person / rate** — your name and badge. Hourly rate and FTE are optional; with a rate you also
   see dollars.
3. **Funds → Cost codes → Add a cost code.** A cost code is a **pot of funds**. You are asked for every field:

   | Field | |
   |---|---|
   | Name | what you call this pot, e.g. `Gamma campaign` |
   | Cost code string | exactly as your timesheet system shows it, e.g. `310>PRJ0007788 - EXAMPLE CAMPAIGN – GAMMA>General>PT00321: Modelling` (an invented example). This is what the **Copy** button gives you. |
   | PRJ code · PT code | offered from the string if they can be recognised — correct them if they are wrong |
   | Expires on | optional; the card warns when the date is near or past |
   | Notes | optional |

4. **Add the projects that use it.** On the cost code's card, type your tag (`gamma_main`) and press
   **Add project**. A project always belongs to exactly one cost code; one cost code can have many projects.
5. **Give the projects hours** — next section.

---

## 5. Funds: allocate, deallocate, reserve, freeze

Everything about money happens on **Funds → Adjust funds**, and always to a **project** (a cost code has no
buttons of its own — it is just the pot the projects draw from).

1. Pick the **project**.
2. Pick the **action**.
3. Type the **hours** (an "All 42 h" button fills in the maximum), optionally a note.
4. Press the button — it says exactly what it will do, e.g. **“Allocate 40 h to gamma_main”**.

It is recorded **straight away**. There is no Save or Approve for funds.

| Action | What it does |
|---|---|
| **Allocate** | Gives the project hours from this cost code. This is how a project gets its funds. |
| **Deallocate** | Takes hours back off the project. |
| **Reserve** | Holds hours back for something planned. They stop being available until you unreserve them. |
| **Unreserve** | Releases held hours so they can be charged again. |
| **Freeze** | Hours you may not use, e.g. pending a sponsor decision. |
| **Unfreeze** | Lifts the freeze. |

**Available = allocated − spent − reserved − frozen.** The app never lets you take out more than is there,
and tells you the limit if you try.

**Made a mistake?** Nothing is ever erased — you do the **opposite action**. The list at the bottom of the
page, *Last few fund changes*, has an **Undo** button that fills the opposite action in for you; you still
press the button to confirm.

Moving hours from one project to another is two steps: **Deallocate** from one, **Allocate** to the other.

Colours: 🟢 more than 30 % left · 🟠 10–30 % · 🔴 under 10 % or overdrawn · ⚪ nothing allocated.

---

## 6. Your week

**During the week — plan.** On **This week** (or at the bottom of the Dashboard) type the hours you intend to
charge next to each project and press **Save plan**. That is an *intention*: it is written to a JSON file, it
survives restarts, it shows on the dashboard marked “planned”, and it is **not** in the system yet. Change it
as often as you like — each Save replaces the last plan.

**While filling in your timesheet.** Press **Copy code** next to a project and paste.

**Once, when the week is settled — approve.** Press **Approve week**. Everything you typed goes into the
system in one step and the plan file is emptied.

One total per project per week. Fixed a number after approving? Type the correct total and approve again — the
correction is recorded and the total is right. Type `0` to remove an entry. Projects you leave at 0 and never
touched are simply not recorded.

---

## 7. What is saved when

| | Funds actions | Weekly hours |
|---|---|---|
| When you press the button | recorded immediately | **Save plan** keeps it in `fridayfree.intentions.json`, outside the database |
| In the system | at once | after **Approve week** |
| Undo | the opposite action | change the number, or **Discard plan** before approving |

**Nothing is ever edited or deleted.** Every change is a new signed line: allocate 100 then 40 more then take
20 back is stored as `+100`, `+40`, `−20`. You only ever see the resulting totals; the lines themselves are
under **History → Everything recorded**.

---

## 8. The pages

| Page | Use it for |
|---|---|
| **Dashboard** | Panels you switch with *Show*: **Total** (available / allocated / spent / reserved / frozen, with dollars if you set a rate) · **By cost code** (available, spent bar, copy button) · **By project** (what you can charge, what is held, what is overdrawn) — then this week's hours, the tables and the charts |
| **This week** | The weekly list: one hours box per project, Save plan / Approve week |
| **Funds → Adjust funds** | The six actions, your projects' numbers, and the last few changes with Undo |
| **Funds → Cost codes** | Add a cost code (all fields), add projects to it, copy its string, edit or delete it |
| **Funds → Projects** | Rename a project, set it *active / completed / cancelled*, delete an unused one |
| **History → Everything recorded** | Every entry ever made, grouped by when it was recorded, filterable by cost code or project |
| **History → Weekly hours** | One line per project per week, with the corrections behind any entry |
| **Tasks** | A light to-do list, optionally linked to a project |
| **Settings** | Fiscal years · your name, badge, rate · **Carry forward** |

The **Fiscal year** box in the sidebar switches years. Every table has **Export as markdown**.

---

## 9. End of year: carry forward

**Settings → Carry forward** moves what is left into the new year. It is available once

- the fiscal year has **ended**, and
- **nothing is left unapproved** in it (or in the year you are carrying into).

You see a preview — cost code, project, what is left, what carries, reserved, frozen — then press
**Carry forward to FY27**. It rebuilds every cost code and project in the new year and allocates each
project's leftover hours to it, keeping reserved and frozen hours as they were.

- Cancelled projects are **left behind**; overdrawn projects carry **0** and the overdraft stays in the old year.
- If the new year already exists (with the same cost codes or projects), the hours are **added** to it — the
  preview shows what was already there.
- The old year is never changed, and the same year cannot be carried twice.
- Tasks stay where they are.

---

## 10. Backup, restore, move to another computer

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

## 11. Command reference

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

## 12. Update or uninstall

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

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: fridayfree` (or `fdf`) | Use the full path `~/.venvs/fridayfree/bin/fridayfree`, or add that folder to PATH (section 1) and open a new terminal |
| Browser did not open | Go to `http://localhost:8501` yourself |
| "Port 8501 is already in use" | Another copy is running — use it, stop it with `Ctrl+C`, or start with `--port 8600` |
| pip fails with an SSL/certificate error | You are behind a proxy; ask IT for the pip proxy/certificate settings, or install from a network without one |
| "Something went wrong" on a page | Your data is safe. The details are in `~/FriDayfree/app_errors.log` |
| No hours boxes on This week | Fill in *Settings → Person / rate* for that fiscal year |
| Cannot allocate more than X | That is all the project has left; deallocate elsewhere first, or allocate more to it |
| Carry forward is greyed out | The year has not ended, or hours are still planned and unapproved (section 9) |
| A project shows 0 h available | It has no hours yet — Funds → Adjust funds → **Allocate** (section 5) |
| Cannot delete a project | Hours are recorded on it — set its status to *cancelled* instead (Funds → Projects) |
| Copy button says "Copy failed" | Select the string in the grey box next to it and copy it manually |
| I approved a wrong number | Weekly hours: type the right number and approve again. Funds: do the opposite action (or press **Undo**). Either way the correction is recorded and the total is right. |
