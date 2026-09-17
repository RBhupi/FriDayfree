"""A database created by v1.0 (intentions stored in change_sets/change_items) upgrades without losing anything."""
import json
import sqlite3

from fridayfree.db.connection import get_connection, init_db
from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.changes import service as changes

LEGACY = """
CREATE TABLE fiscal_years (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL UNIQUE,
  start_date DATE NOT NULL, end_date DATE NOT NULL);
CREATE TABLE people (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, badge TEXT,
  fy_id INTEGER NOT NULL REFERENCES fiscal_years(id), rate_dollar REAL, fte REAL, UNIQUE(badge, fy_id));
CREATE TABLE cost_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, fy_id INTEGER NOT NULL REFERENCES fiscal_years(id),
  charge_string TEXT NOT NULL, prj_code TEXT NOT NULL DEFAULT '', pt_code TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL, notes TEXT, UNIQUE(fy_id, charge_string));
CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, cost_code_id INTEGER NOT NULL REFERENCES cost_codes(id),
  name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(cost_code_id, name));
CREATE TABLE change_sets (id INTEGER PRIMARY KEY AUTOINCREMENT, fy_id INTEGER NOT NULL REFERENCES fiscal_years(id),
  status TEXT NOT NULL DEFAULT 'saved' CHECK(status IN ('saved','approved')), note TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_at TIMESTAMP);
CREATE UNIQUE INDEX uq_open_change_set ON change_sets(fy_id) WHERE status = 'saved';
CREATE TABLE change_items (id INTEGER PRIMARY KEY AUTOINCREMENT,
  change_set_id INTEGER NOT NULL REFERENCES change_sets(id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(id), field TEXT NOT NULL, person_id INTEGER REFERENCES people(id),
  week_start DATE, target_value REAL NOT NULL, dollars REAL, reason TEXT);
CREATE TABLE allocation_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT,
  change_set_id INTEGER NOT NULL REFERENCES change_sets(id), project_id INTEGER NOT NULL REFERENCES projects(id),
  entry_type TEXT NOT NULL, hours REAL NOT NULL, dollars REAL, reason TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE spending_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT,
  change_set_id INTEGER NOT NULL REFERENCES change_sets(id), person_id INTEGER NOT NULL REFERENCES people(id),
  project_id INTEGER NOT NULL REFERENCES projects(id), week_start DATE NOT NULL, hours REAL NOT NULL,
  dollars REAL, notes TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TRIGGER allocation_ledger_no_delete BEFORE DELETE ON allocation_ledger
BEGIN SELECT RAISE(ABORT, 'allocation_ledger is append-only'); END;
CREATE TRIGGER change_sets_approved_no_delete BEFORE DELETE ON change_sets WHEN OLD.status = 'approved'
BEGIN SELECT RAISE(ABORT, 'approved change sets are immutable'); END;
CREATE TRIGGER change_items_approved_no_delete BEFORE DELETE ON change_items
WHEN (SELECT status FROM change_sets WHERE id = OLD.change_set_id) = 'approved'
BEGIN SELECT RAISE(ABORT, 'approved change sets are immutable'); END;

INSERT INTO fiscal_years VALUES (1, 'FY26', '2025-10-01', '2026-09-30');
INSERT INTO people VALUES (1, 'Example', 'B00001', 1, NULL, NULL);
INSERT INTO cost_codes VALUES (1, 1, '101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis',
  'PRJ0001234', 'PT00567', 'ALPHA / Analysis', NULL);
INSERT INTO projects(id, cost_code_id, name) VALUES (1, 1, 'alpha_main'), (2, 1, 'alpha_travel');
INSERT INTO change_sets(id, fy_id, status, note, approved_at) VALUES (1, 1, 'approved', 'kickoff', '2025-10-02 09:00:00');
INSERT INTO change_items(change_set_id, project_id, field, target_value) VALUES (1, 1, 'allocated', 100);
INSERT INTO allocation_ledger(change_set_id, project_id, entry_type, hours) VALUES (1, 1, 'fund', 100);
INSERT INTO spending_ledger(change_set_id, person_id, project_id, week_start, hours) VALUES (1, 1, 1, '2025-10-06', 8);
INSERT INTO change_sets(id, fy_id, status, note) VALUES (2, 1, 'saved', 'next week');
INSERT INTO change_items(change_set_id, project_id, field, person_id, week_start, target_value, reason) VALUES
  (2, 2, 'allocated', NULL, NULL, 40, 'travel funds'), (2, 1, 'week_hours', 1, '2025-10-13', 6, NULL);
"""


def _legacy_db(tmp_path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(str(path))
    raw.executescript(LEGACY)
    raw.commit()
    raw.close()
    return path


def test_legacy_database_upgrades_in_place(tmp_path):
    path = _legacy_db(tmp_path)
    conn = get_connection(path)
    init_db(conn)

    # approved data is untouched and still linked to its approval
    assert allocation.get_balance(conn, 1).allocated == 100 and allocation.get_balance(conn, 1).spent == 8
    assert [(h["id"], h["note"], h["amendments"]) for h in changes.list_change_sets(conn, 1)] == [(1, "kickoff", 2)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "change_items" not in tables and "change_sets_new" not in tables

    # the saved intentions moved to the JSON file
    stored = json.loads((tmp_path / "old.intentions.json").read_text())
    assert stored["fiscal_years"]["1"]["note"] == "next week"
    assert {(i.project_id, i.field, i.target_value) for i in changes.get_saved_items(conn, 1)} == {
        (2, "allocated", 40), (1, "week_hours", 6)}

    # a safety copy was made, and approving afterwards works
    assert len(list((tmp_path / "backups").glob("old-before-upgrade-*.db"))) == 1
    result = changes.approve(conn, 1)
    assert result.rows_written == 2 and allocation.get_balance(conn, 2).allocated == 40
    conn.close()


def test_upgrade_runs_only_once(tmp_path):
    path = _legacy_db(tmp_path)
    for _ in range(3):
        conn = get_connection(path)
        init_db(conn)
        conn.close()
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
