import sqlite3

import pytest

from fridayfree.db.connection import init_db

TABLES = {
    "fiscal_years", "people", "cost_codes", "projects",
    "change_sets", "allocation_ledger", "spending_ledger", "tasks",
}


def _approved_set(conn, fy_id):
    cur = conn.execute("INSERT INTO change_sets(fy_id) VALUES (?)", (fy_id,))
    return cur.lastrowid


def test_all_tables_created(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert TABLES <= names


def test_init_db_is_idempotent(conn, fy):
    init_db(conn)
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM fiscal_years").fetchone()[0] == 1


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO cost_codes(fy_id, charge_string, name) VALUES (999, 'x', 'x')")


def test_fiscal_year_dates_must_be_ordered(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO fiscal_years(label, start_date, end_date) VALUES ('bad', '2026-09-30', '2025-10-01')")


def test_charge_string_unique_per_fy(conn, fy, cost_code):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cost_codes(fy_id, charge_string, name) "
            "SELECT fy_id, charge_string, 'dup' FROM cost_codes WHERE id = ?",
            (cost_code,),
        )


@pytest.mark.parametrize("sql", [
    "UPDATE allocation_ledger SET hours = 1",
    "DELETE FROM allocation_ledger",
])
def test_allocation_ledger_is_append_only(conn, fy, project, sql):
    cs = _approved_set(conn, fy["id"])
    conn.execute(
        "INSERT INTO allocation_ledger(change_set_id, project_id, entry_type, hours) VALUES (?, ?, 'fund', 100)",
        (cs, project),
    )
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute(sql)


@pytest.mark.parametrize("sql", [
    "UPDATE spending_ledger SET hours = 1",
    "DELETE FROM spending_ledger",
])
def test_spending_ledger_is_append_only(conn, fy, person, project, sql):
    cs = _approved_set(conn, fy["id"])
    conn.execute(
        "INSERT INTO spending_ledger(change_set_id, person_id, project_id, week_start, hours) "
        "VALUES (?, ?, ?, '2025-10-06', 8)",
        (cs, person, project),
    )
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE change_sets SET note = 'x'", "DELETE FROM change_sets"])
def test_approvals_are_append_only(conn, fy, sql):
    _approved_set(conn, fy["id"])
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute(sql)


def test_database_has_no_staging_tables(conn):
    """Intentions live in the JSON file; the database only knows approved data."""
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "change_items" not in names
    assert "status" not in {r[1] for r in conn.execute("PRAGMA table_info(change_sets)")}


def test_spending_week_must_be_monday(conn, fy, person, project):
    cs = _approved_set(conn, fy["id"])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO spending_ledger(change_set_id, person_id, project_id, week_start, hours) "
            "VALUES (?, ?, ?, '2025-10-07', 8)",
            (cs, person, project),
        )


def test_allocation_row_cannot_be_zero_hours(conn, fy, project):
    cs = _approved_set(conn, fy["id"])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO allocation_ledger(change_set_id, project_id, entry_type, hours) VALUES (?, ?, 'fund', 0)",
            (cs, project),
        )


def test_bad_entry_type_rejected(conn, fy, project):
    cs = _approved_set(conn, fy["id"])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO allocation_ledger(change_set_id, project_id, entry_type, hours) VALUES (?, ?, 'gift', 1)",
            (cs, project),
        )
