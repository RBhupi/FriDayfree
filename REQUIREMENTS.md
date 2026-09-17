# FriDayfree — v1 Requirements

## Overview

A lightweight, local, single-user web app for tracking project cost code allocations and weekly spending. Built for researchers who charge time in Dayforce to multiple cost codes across fiscal years and need to know — at a glance — where their budget stands, what they can charge this week, which hours are reserved or frozen, and **the exact cost code string to paste into Dayforce**.

---

## Context

- Fiscal Year runs **October 1 → September 30**
- Time is tracked in **hours** (primary unit); dollars are **derived** from an optional hourly rate
- A **cost code** is one Dayforce charge string, e.g. `101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis`
- A **project** is the user's own tag (e.g. `alpha_main`). One project has exactly one string; one string may serve several projects
- Hours are added, removed, reserved and frozen over the year
- v1 is **single-user, local machine only**

### Core principles (non-negotiable)

1. **Append-only.** Hours are never edited in place. An addition is a positive row, a removal a negative row. Nothing already written is updated or deleted. A reason is always optional.
2. **Save ≠ Approve.** The user edits the *final numbers they want*. **Save** persists them as *intentions*. **Approve** puts them *in the system* (ledger rows are appended). Both survive restarts.
3. **Final state only.** The dashboard shows resulting numbers (including saved intentions, subtly marked) — never a list of amendments. History lives on a secondary page.

---

## Users

**v1:** Single researcher running the app on their own laptop.
**v2 (future):** Multiple contributors on the same team, each managing their own allocations.

---

## Functional Requirements

### FR-1: Fiscal Year Management
- [x] Create a fiscal year with label (e.g. "FY26"), start date, end date (dates default from the label)
- [x] Switch between fiscal years in the sidebar
- [x] All cost codes, projects, and spending are scoped to a fiscal year

### FR-2: Person / Rate Setup
- [x] One person per FY with name, badge number, optional hourly rate ($), optional FTE
- [x] Rate and FTE are nullable — hours are always required, dollars are not
- [x] Schema supports multiple people for v2

### FR-3: Cost Codes (charge strings)
- [x] A cost code is created by **pasting the Dayforce string**; the app deciphers PRJ code, PT code and a readable name
- [x] The string is stored verbatim and unique per FY
- [x] Strings the parser does not recognise are still accepted and copyable
- [x] Edit name and free-text notes; delete only if none of its projects has hours recorded or planned
- [x] **Copy button** for the string wherever a cost code appears

### FR-4: Projects
- [x] Add a project with **a tag + a charge string** (pasted new, or picked from existing strings); the cost code is reused or created
- [x] Rename; set status `active` | `completed` | `cancelled`
- [x] Delete only if nothing is recorded or planned on it; otherwise cancel (cancelled projects are hidden by default)
- [x] **Copy-cost-code button per project** (dashboard and Projects page)
- [x] A new project has 0 hours; hours are set under **Allocations → Funds** (or the dashboard grid)
- [x] Cost codes can be added on their own (paste the string) and projects added to an existing cost code

### FR-5: Allocation, Reserve, Freeze (append-only)
- [x] Per project the user edits three final numbers: **Allocated**, **Reserved**, **Frozen**
- [x] On approval the difference is appended as a signed row: `fund` (+add / −remove), `reserve` (+reserve / −unreserve), `freeze` (+freeze / −unfreeze)
- [x] A move between projects is "A −10, B +10" approved together (same change set)
- [x] Reserved hours become chargeable only after unreserving; frozen hours only after unfreezing
- [x] Reason/note optional on every change
- [x] Blocked: negative numbers; reserved + frozen greater than the allocation

### FR-6: Weekly Spending (append-only)
- [x] Week picker: Mon–Sun weeks of the FY up to four weeks ahead, default current week
- [x] **One net number per project per week**; typing a new total appends the signed difference, typing 0 appends a full reversal
- [x] Optional note per entry (a note-only change is recorded too)
- [x] Cannot increase hours on a cancelled project (reductions allowed)
- [x] Warning (not block) when hours overdraw a project or dip into reserved/frozen hours

### FR-7: Dashboard
- [x] **Panels, switchable or all at once**: **Total** (available / allocated / spent / reserved / frozen), **By cost code** (available, spent bar, copy button), **By project — what can I charge this week** (by available hours with copy buttons; held projects listed as "do not charge"; overdrawn in red)
- [x] Banner when numbers include not-yet-approved changes + "Show approved only" toggle
- [x] **Workspace grid** to edit Allocated / Reserved / Frozen / Hours for the selected week, with live Available and status
- [x] Per cost code summary: allocated / spent / reserved / frozen / available (and $ if rate set); per project breakdown
- [x] Color coding, always with a text label: green (>30% remaining) / amber (10–30%) / red (<10% or overdrawn)
- [x] Charts: weekly burn; available by project; cumulative spend vs allocation with **projected end-of-FY spend** at the average pace of the last 4 completed weeks
- [x] Overdraft alerts for any overdrawn project or cost code

### FR-8: Export
- [x] Copy any table as markdown (code block with copy button) and download as `.md`
- [x] Available on: cost code summary, project breakdown, cost codes, weekly spending log, audit log

### FR-9: Tasks / Notes (secondary)
- [x] Task with title, optional project link, status `todo` | `in_progress` | `done`, optional due date, notes
- [x] Flat list or grouped by project; inline status change; overdue highlight

### FR-10: Save / Approve workflow
- [x] Edits in the grid are **unsaved** until the user acts; they survive switching pages within a session
- [x] **Save** stores them as intentions in a **JSON file next to the database** (never in the database) — persisted across restarts; each Save replaces the previous plan
- [x] **Approve** appends the ledger rows for every saved and unsaved change in one transaction, records the approval, then empties the intentions file
- [x] Typical rhythm: save intended hours during the week, approve once when the week is settled
- [x] **Discard** forgets saved and unsaved changes; approved data is untouched
- [x] Sidebar reminder on every page while anything is unsaved or unapproved
- [x] History page: approved change sets, newest first, collapsed; each expands to its signed rows

---

## Non-Functional Requirements

### NFR-1: Local only
- Installed with `pip install .`; started with the `fridayfree` command (alias `fdf`) from any folder
- Runs on `localhost` via Streamlit; no authentication in v1
- All data in one file, `~/FriDayfree/fridayfree.db` (overridable) — never inside the package; `fdf backup` makes dated copies

### NFR-2: Performance
- All pages load in under 2 seconds with a full FY of data

### NFR-3: Reliability
- All writes are transactional — no partial saves (approve is all-or-nothing)
- Append-only is enforced **in the database** by triggers, not just in code
- DB initialises cleanly on first run
- Friendly error messages; tracebacks go to `app_errors.log`, never to the screen

### NFR-4: Maintainability
- SOLID, DRY, YAGNI; TDD for repository and service layers
- No business logic in the UI layer; no UI code or business rules in repositories

### NFR-5: Portability
- macOS and Linux (Windows nice-to-have); `pip install .`; no Docker

---

## Out of Scope for v1

- Multi-user / shared access, cloud sync, authentication
- Email or push alerts
- Import from timesheet dumps
- Historical FY comparison
- Entering dollar amounts by hand (schema keeps nullable dollar columns for v2; v1 derives $ from the rate)

---

## Acceptance Criteria

### Allocation
- FY → person → project (tag + pasted string) → hours, in sequence without errors
- Pasted string is deciphered; two projects can share it; copy button yields the exact string
- Changing 100 → 120 → 90 leaves rows `+100, +20, −30`; earlier rows are byte-for-byte unchanged
- Reserving/freezing lowers Available; unreserving/unfreezing restores it
- `UPDATE`/`DELETE` on a ledger fails at the database level

### Save / Approve
- Saved intentions are still there after restarting the app, live in the JSON file, and the database contains no trace of them
- A database from an earlier version upgrades automatically (backup first; pending intentions carried over)
- Approve is atomic; Discard never touches approved data
- Dashboard numbers include intentions by default and match the ledgers with "Show approved only"

### Spending
- Week 8 h → 5 h → 0 h shows nets only; the correction trail is `+8, −3, −5`
- Overdraft warning shown; entry still approvable

### Dashboard
- All charts render; "What can I charge this week" is accurate; thresholds match; page loads under 2 seconds

### Export
- Copied and downloaded markdown tables are valid

### Tests
- Every service and repository function is covered by pytest against an in-memory DB
- Every page has an automated render smoke test (`streamlit.testing`); interaction is checked manually

---

## Glossary

| Term | Definition |
|---|---|
| Charge string / Cost code | The Dayforce string hours are charged to, e.g. `101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis` |
| Project | The user's own tag for a work effort (e.g. `alpha_main`) with its own hours under one charge string |
| Ledger | Append-only table of signed hour rows; totals are sums |
| Allocated | Σ `fund` rows for a project |
| Reserved | Hours the user is holding back for a planned event; chargeable only after unreserving |
| Frozen | Hours that cannot be used until unfrozen (e.g. pending sponsor decision) |
| Available | Allocated − spent − reserved − frozen (0 for non-active projects) |
| Net hours | The one number per project per week the user sees; the sum of that week's signed rows |
| Intention | A saved but not yet approved change |
| Change set | The group of changes saved/approved together; History is organised by it |
| Week | Monday–Sunday, identified by its Monday |
| Overdraft | Spent hours exceed allocated hours for a project or cost code |
| FTE | Full-time equivalent; optional |
