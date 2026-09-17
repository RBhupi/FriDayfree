-- FriDayfree schema. Single source of truth; safe to run repeatedly.
--
-- Metadata tables (fiscal_years, people, cost_codes, projects, tasks) are ordinary mutable rows.
-- Hours and dollars live ONLY in the two append-only ledgers, written by changes.service.approve.
-- Saved intentions are NOT stored here: they live in <database>.intentions.json until approved.
-- change_sets records each approval; every ledger row points at the approval that wrote it.

CREATE TABLE IF NOT EXISTS fiscal_years (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  label               TEXT NOT NULL UNIQUE,              -- "FY26"
  start_date          DATE NOT NULL,                     -- "2025-10-01"
  end_date            DATE NOT NULL,                     -- "2026-09-30"
  carried_from_fy_id  INTEGER REFERENCES fiscal_years(id),  -- set on the NEW year by carry forward; NULL = never carried into
  CHECK(start_date < end_date)
);

CREATE TABLE IF NOT EXISTS people (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  badge        TEXT,
  fy_id        INTEGER NOT NULL REFERENCES fiscal_years(id),
  rate_dollar  REAL CHECK(rate_dollar IS NULL OR rate_dollar >= 0),
  fte          REAL CHECK(fte IS NULL OR (fte > 0 AND fte <= 1)),
  UNIQUE(badge, fy_id)
);

-- A cost code is the BUCKET of funds: one charge string per fiscal year, stored verbatim so it can be
-- copied straight back into the timesheet system. Every field is typed by the user.
CREATE TABLE IF NOT EXISTS cost_codes (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  fy_id          INTEGER NOT NULL REFERENCES fiscal_years(id),
  charge_string  TEXT NOT NULL CHECK(length(trim(charge_string)) > 0),  -- "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis"
  prj_code       TEXT NOT NULL DEFAULT '',       -- "PRJ0001234"
  pt_code        TEXT NOT NULL DEFAULT '',       -- "PT00567"
  name           TEXT NOT NULL,                  -- the user's own name for the bucket
  notes          TEXT,
  expires_on     DATE,                           -- optional
  UNIQUE(fy_id, charge_string)
);

-- A project is the user's own tag (e.g. "alpha_main") drawing from exactly one cost code;
-- several projects may share the same bucket. All fund actions happen on projects, never on cost codes.
CREATE TABLE IF NOT EXISTS projects (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  cost_code_id  INTEGER NOT NULL REFERENCES cost_codes(id),
  name          TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(cost_code_id, name)
);

-- Approvals -------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS change_sets (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  fy_id        INTEGER NOT NULL REFERENCES fiscal_years(id),
  note         TEXT,
  approved_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Ledgers (append-only) -------------------------------------------------------------------------

-- fund: +add / -remove.  reserve: +reserve / -unreserve.  freeze: +freeze / -unfreeze.
CREATE TABLE IF NOT EXISTS allocation_ledger (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  change_set_id  INTEGER NOT NULL REFERENCES change_sets(id),
  project_id     INTEGER NOT NULL REFERENCES projects(id),
  entry_type     TEXT NOT NULL CHECK(entry_type IN ('fund','reserve','freeze')),
  hours          REAL NOT NULL CHECK(hours <> 0),
  dollars        REAL,
  reason         TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Rows are signed deltas; the net per (person, project, week) is what the UI shows.
CREATE TABLE IF NOT EXISTS spending_ledger (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  change_set_id  INTEGER NOT NULL REFERENCES change_sets(id),
  person_id      INTEGER NOT NULL REFERENCES people(id),
  project_id     INTEGER NOT NULL REFERENCES projects(id),
  week_start     DATE NOT NULL CHECK(strftime('%w', week_start) = '1'),   -- always a Monday
  hours          REAL NOT NULL,
  dollars        REAL,
  notes          TEXT,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alloc_project ON allocation_ledger(project_id);
CREATE INDEX IF NOT EXISTS idx_spend_project_week ON spending_ledger(project_id, week_start);

CREATE TRIGGER IF NOT EXISTS allocation_ledger_no_update BEFORE UPDATE ON allocation_ledger
BEGIN SELECT RAISE(ABORT, 'allocation_ledger is append-only'); END;

CREATE TRIGGER IF NOT EXISTS allocation_ledger_no_delete BEFORE DELETE ON allocation_ledger
BEGIN SELECT RAISE(ABORT, 'allocation_ledger is append-only'); END;

CREATE TRIGGER IF NOT EXISTS spending_ledger_no_update BEFORE UPDATE ON spending_ledger
BEGIN SELECT RAISE(ABORT, 'spending_ledger is append-only'); END;

CREATE TRIGGER IF NOT EXISTS spending_ledger_no_delete BEFORE DELETE ON spending_ledger
BEGIN SELECT RAISE(ABORT, 'spending_ledger is append-only'); END;

CREATE TRIGGER IF NOT EXISTS change_sets_no_update BEFORE UPDATE ON change_sets
BEGIN SELECT RAISE(ABORT, 'change_sets is append-only'); END;

CREATE TRIGGER IF NOT EXISTS change_sets_no_delete BEFORE DELETE ON change_sets
BEGIN SELECT RAISE(ABORT, 'change_sets is append-only'); END;

-- Tasks -----------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  title       TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','in_progress','done')),
  notes       TEXT,
  due_date    DATE,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
