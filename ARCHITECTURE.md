# FriDayfree — Architecture

## Principles

- **Append-only ledgers**: hours are signed rows (+ add / − remove); nothing written is ever updated or deleted. Enforced by database triggers.
- **Save ≠ Approve**: edits are *targets* (the final number wanted). Saved = intention, kept in a **JSON file next to the database — never in the database**. Approved = ledger rows appended. One write path.
- **Final state only**: every screen shows totals; amendments live on the History page.
- **SOLID / DRY / YAGNI / TDD**: each layer has one job; one balance formula, one week util, one export function; repositories and services are tested before the UI is wired.

---

## Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| UI | Streamlit ≥ 1.40 (`st.navigation`, `st.data_editor`, components v2) | Fastest path to a local dashboard; the editable grid is the workspace |
| Database | SQLite (stdlib) | Single file, zero config, triggers enforce append-only |
| Data wrangling | Pandas | Weekly aggregation; Streamlit-native |
| Charts | Plotly | Interactive hover, themed by Streamlit |
| Testing | Pytest + `streamlit.testing.v1.AppTest` | In-memory DB for logic, render smoke test per page |
| Export | Built-in Python | Hand-written markdown table (no `tabulate`) |

**No ORM.** Raw SQL via `sqlite3`.

---

## Project Structure

```
pyproject.toml               # pip package "fridayfree"; console commands `fridayfree` and `fdf`
README.md  REQUIREMENTS.md  ARCHITECTURE.md  docs/USER_GUIDE.md
fridayfree/
  __init__.py                # __version__
  cli.py                     # fridayfree / fdf: run (default) · where · backup · demo · --db · --port
  app.py                     # st.navigation shell, FY selector, per-rerun connection, friendly error guard
  db/
    schema.sql               # single source of truth: tables, indexes, append-only triggers (shipped as package data)
    connection.py            # data_dir(), db_path(), intentions_path(), error_log_path(), get_connection(), init_db(conn)
    intentions.py            # JSON store for saved-not-approved items: load / save / clear / count_for_project
    migrations.py            # one-time upgrades of older databases (backs up first), run by init_db
    seed.py                  # demo data, built through the services (`fdf demo`)
  modules/
    errors.py                # ValidationError
    shared_ui.py             # AppContext, run_action, flash, export_controls, copy_button
    settings/    repository.py service.py ui.py     # fiscal_years, people
    allocation/  repository.py service.py ui.py     # cost_codes (charge strings), projects, balance query, ledger read/insert
    spending/    repository.py service.py ui.py     # spending_ledger read/insert, weekly nets
    changes/     repository.py service.py ui.py     # save · approve · discard · validate · load_state; workspace grid + action bar
    dashboard/   service.py charts.py ui.py         # pure aggregations over State; plotly figures
    tasks/       repository.py service.py ui.py
  utils/
    dates.py                 # week_start, fy_weeks, pickable_weeks, default_week, week_label, fy_default_dates
    formatting.py            # format_hours, format_dollar, to_dollars, risk_color + status palette
    charge_string.py         # parse_charge_string("101>PRJ… - NAME>General>PT…: TASK")
    export.py                # df_to_markdown, markdown_filename
tests/                       # conftest + one file per layer, test_charts, test_cli, test_app_smoke
```

### Install, run, data location

`pip install .` installs one package (`fridayfree`) and two identical commands (`fridayfree`, `fdf`).
The command starts `python -m streamlit run <package>/app.py` bound to `localhost`.

User data never lives in the package or the working directory: `~/FriDayfree/fridayfree.db`
(+ `backups/`, `app_errors.log`). Overrides: `FRIDAYFREE_HOME` (folder), `FRIDAYFREE_DB` or `--db` (file, wins).
`connection.py` is the only module that knows this.

---

## Database Schema

See `fridayfree/db/schema.sql` (authoritative). Summary:

| Table | Kind | Notes |
|---|---|---|
| `fiscal_years`, `people` | metadata (mutable) | person is per FY; rate/FTE nullable |
| `cost_codes` | metadata | `charge_string` verbatim, `UNIQUE(fy_id, charge_string)`; deciphered `prj_code`, `pt_code`, editable `name`, `notes` |
| `projects` | metadata | user tag, `status`; FY comes from its cost code |
| `change_sets` | **append-only** | one row per approval (`fy_id`, `note`, `approved_at`); ledger rows point at it |
| `allocation_ledger` | **append-only** | `entry_type ∈ fund/reserve/freeze`, signed `hours ≠ 0`, `change_set_id`, optional `reason` |
| `spending_ledger` | **append-only** | signed `hours`, `week_start` must be a Monday, `change_set_id`, optional `notes` |
| `tasks` | metadata | `project_id` → `ON DELETE SET NULL` |

Triggers: `BEFORE UPDATE/DELETE` on both ledgers and on `change_sets` → `RAISE(ABORT, '… is append-only')`.

**Not in the database:** saved intentions. `<database>.intentions.json` holds, per fiscal year, a note and a list of
items (`project_id`, `field ∈ allocated/reserved/frozen/week_hours`, **`target_value` = final number wanted**,
`week_start` + `person_id` for weekly hours, optional `reason`; the project name is included for readability only).
Writes are atomic (temp file + rename); the file is removed when nothing is pending.

---

## Layer Responsibilities

- **`repository.py`** — SQL only. Takes a connection, returns dicts. Never commits. Dates cross the boundary as `datetime.date` (explicit ISO conversion).
- **`service.py`** — business rules. Every write runs inside `with conn:` (atomic). Raises `ValidationError` for user-correctable problems; returns non-blocking `warnings`.
- **`ui.py`** — Streamlit widgets only; calls services, never repositories.
- **`utils/`** — stateless pure functions.

---

## Key Business Logic

### Balance (single definition: `allocation.service.ProjectBalance`)
```
allocated = Σ fund      reserved = Σ reserve      frozen = Σ freeze      spent = Σ spending_ledger
balance   = allocated − spent
available = balance − reserved − frozen        (0 if project status ≠ active)
overdrawn = balance < 0       held_breach = balance ≥ 0 and available < 0
pct_remaining = available / allocated           (None when nothing allocated → grey)
```
One SQL constant (`_BALANCE_SQL`, correlated `SUM` subqueries so ledger rows never multiply each other) serves per-FY and per-project lookups. Cost code figures are sums over its projects.

### Save / Approve (`changes.service`)
```
WorkItem(project_id, field, target_value, week_start?, person_id?, reason?)     key = (project, field, week)
merge_items(saved, working)      working (unsaved) overrides saved on the same cell
load_state(conn, fy, items)      approved balances + weekly hours with targets applied, in memory → State
validate(conn, fy, items)        errors block; warnings don't
save_items(...)                  rewrite the FY's entry in the intentions JSON; no-op targets are dropped; empty → entry removed
approve(conn, fy)                re-validate → one transaction: insert the approval row + a signed ledger row per delta ≠ 0
                                 → after the commit, clear the JSON entry (a crash in between leaves harmless no-ops)
discard(conn, fy)                clear the JSON entry; database untouched
```
**Errors:** negative target · reserved + frozen > allocated · week not a Monday inside the FY · weekly hours without a person · *raising* hours on a cancelled project.
**Warnings:** project or cost code overdrawn · spending dips into reserved/frozen hours.

### Dashboard is pure over `State`
`chargeable_now`, `cost_code_summary`, `overdraft_alerts`, `weekly_burn`, `cumulative_vs_allocation`, `project_end_of_fy` take a `State`, so the same code renders **approved-only** (`load_state(items=())`) or the **final state including intentions**.

Projection: average of the last ≤ 4 *completed* weeks (zeros count, current week excluded) × remaining weeks; a remaining week already logged above pace keeps its real hours.

### Workspace grid state
`approved` (ledgers) → `saved` (intentions JSON) → `working` (`st.session_state`, survives page switches). The grid shows all three merged; after each edit the working store is re-derived from the editor (cells that differ from approved + saved) and the page reruns so every number reflects it. Save/Approve/Discard clear the working store and bump the editor key.

### Risk colours
`> 30 %` green · `10–30 %` amber · `< 10 %` red · overdrawn red · nothing allocated grey. Status palette (`#0ca30c / #fab219 / #d03b3b`), always paired with a text label.

### Week picker
Mondays from the week containing FY start to the week containing FY end, capped at today + 4 weeks, newest first, default current week.

### Charge string
`parse_charge_string` splits on `>`; `PRJ<digits> - <name>` and `PT<digits>: <name>` are recognised, everything else is kept. Unknown shapes are accepted (stored and copyable as-is). The copy button is a components-v2 widget; the string reaches it as data, never as HTML.

---

## Navigation

```
📊 Dashboard                 ← default: panels (Total · Cost codes · Projects, or all) · workspace grid · tables · charts
Allocations   🧮 Funds · 💰 Cost codes · 🏷️ Projects · 🧾 History
Weekly spending   ⏱️ Log hours · 🗓️ Spending history
✅ Tasks
Settings   📅 Fiscal year · 👤 Person / rate
```

---

## Testing Strategy

Order of development (each step test-first): schema → utils → settings → allocation → spending → **changes** → dashboard service → charts → UI smoke.

- `tests/conftest.py`: in-memory DB, FY26, person, cost code (`101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis`), project `alpha_main`, helper `approve_items`.
- Ledger immutability is asserted by snapshotting rows before/after every kind of change.
- Approve atomicity is asserted by forcing a failure mid-transaction.
- `test_app_smoke.py` renders every page on a seeded DB and boots the whole app, including the first-run screen.

---

## Extensibility Notes (v2 hooks, zero v1 work)

| Future feature | How it is already supported |
|---|---|
| Multi-user | `people` table; `person_id` on spending rows and week items |
| Hand-entered dollars | nullable `dollars` on ledger rows and change items |
| Timesheet import | build `WorkItem`s → `save_items` → user reviews → `approve` |
| Multi-FY comparison | everything is scoped through `cost_codes.fy_id` |
| Review by someone else | intentions are a portable JSON file; approval is a single service call |
