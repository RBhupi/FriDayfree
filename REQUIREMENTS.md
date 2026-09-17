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

### FR-3: Cost codes — the bucket of funds
- [x] A cost code is added by hand with **every field asked for**: name, full string, PRJ code, PT code,
      optional expiry date, notes. PRJ/PT are *offered* from the string but never decided for the user
- [x] The string is stored verbatim, is unique per fiscal year, and has a **Copy** button everywhere it appears
- [x] A cost code starts at 0 and has **no action buttons** — it gains funds only because hours are allocated
      to its projects; its figures are the sum of its projects
- [x] Edit every field later; delete only when no hours are recorded on any of its projects
- [x] The card warns when the expiry date is near or past

### FR-4: Projects — what the user works with
- [x] A project has the user's own tag and draws from **exactly one** cost code; many projects may share one
- [x] Added from the cost code's card or from the Projects page by picking a cost code
- [x] Rename; set status `active` | `completed` | `cancelled`; delete only when nothing is recorded on it
- [x] A new project starts with 0 hours — it is given hours with the Allocate action
- [x] **Copy-cost-code button per project**

### FR-5: Fund actions (append-only, recorded immediately)
- [x] Six actions, always on a project, always a positive number of hours:
      **Allocate** (`fund +`), **Deallocate** (`fund −`), **Reserve** (`reserve +`), **Unreserve** (`reserve −`),
      **Freeze** (`freeze +`), **Unfreeze** (`freeze −`)
- [x] The button reads as a sentence — "Allocate 40 h to alpha_main" — and the result is shown before pressing
- [x] Recorded the moment it is pressed: one approval + one signed ledger row, in one transaction
- [x] Limits: deallocate/reserve/freeze at most the free hours (allocated − spent − reserved − frozen, ignoring
      status so a finished project's funds can still be reclaimed); unreserve/unfreeze at most what is held;
      allocating to a cancelled project is refused
- [x] A note is always optional. Mistakes are corrected with the opposite action, never by editing
- [x] "Last few fund changes" with an **Undo** shortcut that pre-fills the opposite action to confirm
- [x] Moving hours between projects is deallocate + allocate (no separate move action)

### FR-6: The week (plan, then approve)
- [x] One box per project for the selected week, with its available hours and a copy button
- [x] **Save plan** stores the week's intentions in a JSON file outside the database; they survive restarts
- [x] **Approve week** writes everything at once; **Discard plan** forgets it. Approved data is never affected
- [x] One total per project per week; a later correction appends the difference; 0 removes the entry
- [x] Projects left at zero and never touched are not recorded at all
- [x] Cannot increase hours on a cancelled project; overdraw warns without blocking

### FR-7: Dashboard (read-only, plus this week)
- [x] Panels switchable or all at once: **Total**, **By cost code** (spent bar, copy button), **By project**
      (chargeable · held · overdrawn)
- [x] Banner when the numbers include a plan that is not approved, and a "Show approved only" toggle
- [x] This week's hours list at the bottom
- [x] Cost-code and project tables (with $ when a rate is set) and charts: weekly burn, available by project,
      cumulative spend vs allocation with the end-of-year projection
- [x] Overdraft alerts

### FR-8: Export
- [x] Copy any table as markdown (code block with copy button) and download as `.md`
- [x] Available on: cost code summary, project breakdown, cost codes, weekly spending log, audit log

### FR-9: Tasks / Notes (secondary)
- [x] Task with title, optional project link, status `todo` | `in_progress` | `done`, optional due date, notes
- [x] Flat list or grouped by project; inline status change; overdue highlight

### FR-10: Plan / approve workflow (weekly hours only)
- [x] **Save** stores them as intentions in a **JSON file next to the database** (never in the database) — persisted across restarts; each Save replaces the previous plan
- [x] **Approve** appends the ledger rows for every saved and unsaved change in one transaction, records the approval, then empties the intentions file
- [x] Typical rhythm: save intended hours during the week, approve once when the week is settled
- [x] **Discard** forgets saved and unsaved changes; approved data is untouched
- [x] Sidebar reminder on every page while hours are planned but not approved
- [x] History page: every recorded entry grouped by approval, newest first, collapsed

### FR-11: Carry forward to the next fiscal year
- [x] Available only once the year has ended **and** nothing is unapproved in it or in the target year
- [x] Preview first: cost code, project, left, carries, reserved, frozen, what is already in the new year
- [x] Rebuilds every cost code and project in the new year and allocates each project's leftover balance,
      keeping reserved and frozen hours as they were; the person is copied so the new year can log hours
- [x] Cancelled projects are left behind; overdrawn projects carry 0 and the overdraft stays put;
      reserved + frozen are trimmed to what is actually left
- [x] An existing target year is reused and added to; the old year is never modified; cannot be run twice

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
