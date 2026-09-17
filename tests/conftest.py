import sqlite3
from datetime import date

import pytest

from fridayfree.db import intentions
from fridayfree.db.connection import init_db

CHARGE_STRING = "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis"


def make_conn(path=":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    intentions.forget(conn)   # in-memory stores are keyed by id(conn), which Python may reuse
    return conn


@pytest.fixture
def conn():
    conn = make_conn()
    yield conn
    conn.close()


@pytest.fixture
def fy(conn):
    """FY26 as a dict, the same shape settings.service returns."""
    cur = conn.execute(
        "INSERT INTO fiscal_years(label, start_date, end_date) VALUES ('FY26', '2025-10-01', '2026-09-30')"
    )
    conn.commit()
    return {"id": cur.lastrowid, "label": "FY26", "start_date": date(2025, 10, 1), "end_date": date(2026, 9, 30)}


@pytest.fixture
def person(conn, fy):
    cur = conn.execute(
        "INSERT INTO people(name, badge, fy_id, rate_dollar, fte) VALUES ('Example', 'B00001', ?, 125.5, 1.0)",
        (fy["id"],),
    )
    conn.commit()
    return cur.lastrowid


def add_cost_code(conn, fy_id, charge_string=CHARGE_STRING, prj="PRJ0001234", pt="PT00567", name="ALPHA / Analysis"):
    cur = conn.execute(
        "INSERT INTO cost_codes(fy_id, charge_string, prj_code, pt_code, name) VALUES (?, ?, ?, ?, ?)",
        (fy_id, charge_string, prj, pt, name),
    )
    conn.commit()
    return cur.lastrowid


def add_project(conn, cost_code_id, name="alpha_main", status="active"):
    cur = conn.execute(
        "INSERT INTO projects(cost_code_id, name, status) VALUES (?, ?, ?)", (cost_code_id, name, status)
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def cost_code(conn, fy):
    return add_cost_code(conn, fy["id"])


@pytest.fixture
def project(conn, cost_code):
    return add_project(conn, cost_code)


def approve_items(conn, fy_id, *items, note=None):
    """Save the given WorkItems as intentions and approve them. Returns the ApproveResult."""
    from fridayfree.modules.changes import service as changes

    changes.save_items(conn, fy_id, list(items), note=note)
    return changes.approve(conn, fy_id)
