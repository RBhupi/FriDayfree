from datetime import date

import pytest

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.changes.service import WorkItem
from fridayfree.modules.errors import ValidationError
from tests.conftest import CHARGE_STRING, add_cost_code, add_project, approve_items

WEEK = date(2025, 10, 6)


def test_create_cost_code_deciphers_the_string(conn, fy):
    code_id = allocation.create_cost_code(conn, fy["id"], f"  {CHARGE_STRING}\n")
    code = allocation.list_cost_codes(conn, fy["id"])[0]
    assert code["id"] == code_id
    assert code["charge_string"] == CHARGE_STRING          # stored verbatim, trimmed
    assert (code["prj_code"], code["pt_code"]) == ("PRJ0001234", "PT00567")
    assert code["name"] == "SAMPLE STUDY – ALPHA / Analysis"
    assert code["project_count"] == 0


def test_same_charge_string_twice_in_one_fy_rejected(conn, fy, cost_code):
    with pytest.raises(ValidationError, match="already set up"):
        allocation.create_cost_code(conn, fy["id"], CHARGE_STRING)
    with pytest.raises(ValidationError, match="empty"):
        allocation.create_cost_code(conn, fy["id"], "  ")


def test_add_project_from_string_creates_then_reuses_cost_code(conn, fy):
    main = allocation.add_project_from_string(conn, fy["id"], "alpha_main", CHARGE_STRING)
    extra = allocation.add_project_from_string(conn, fy["id"], "alpha_travel", CHARGE_STRING)
    assert len(allocation.list_cost_codes(conn, fy["id"])) == 1            # one string, shared
    a, b = allocation.get_project(conn, main), allocation.get_project(conn, extra)
    assert a["cost_code_id"] == b["cost_code_id"]
    assert a["charge_string"] == b["charge_string"] == CHARGE_STRING


def test_project_tag_required_and_unique_within_cost_code(conn, fy, cost_code, project):
    with pytest.raises(ValidationError, match="tag"):
        allocation.create_project(conn, cost_code, " ")
    with pytest.raises(ValidationError, match="already exists"):
        allocation.create_project(conn, cost_code, "alpha_main")
    with pytest.raises(ValidationError, match="tag"):
        allocation.add_project_from_string(conn, fy["id"], "", CHARGE_STRING)


def test_balances_are_zero_without_ledger_rows(conn, fy, project):
    b = allocation.get_balance(conn, project)
    assert (b.allocated, b.spent, b.reserved, b.frozen, b.balance, b.available) == (0, 0, 0, 0, 0, 0)
    assert b.pct_remaining is None and not b.overdrawn
    assert b.charge_string == CHARGE_STRING


def test_balance_math_and_no_join_fan_out(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 120), WorkItem(project, "reserved", 30),
                  WorkItem(project, "frozen", 10))
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 8, WEEK, person),
                  WorkItem(project, "week_hours", 12, date(2025, 10, 13), person))
    b = allocation.get_balance(conn, project)
    assert (b.allocated, b.reserved, b.frozen, b.spent) == (120, 30, 10, 20)
    assert b.balance == 100 and b.available == 60 and b.held == 40
    assert b.pct_remaining == pytest.approx(0.5)
    assert allocation.available_hours(conn, project) == 60


def test_overdrawn_and_held_breach_flags(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 40), WorkItem(project, "frozen", 35))
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 10, WEEK, person))
    b = allocation.get_balance(conn, project)
    assert b.available == -5 and b.held_breach and not b.overdrawn
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 50, WEEK, person))
    b = allocation.get_balance(conn, project)
    assert b.overdrawn and not b.held_breach and b.balance == -10


def test_non_active_project_has_nothing_available(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    allocation.update_project(conn, project, "alpha_main", "completed")
    b = allocation.get_balance(conn, project)
    assert b.balance == 100 and b.available == 0


def test_balances_are_scoped_to_the_fiscal_year(conn, fy, project):
    other_fy = conn.execute(
        "INSERT INTO fiscal_years(label, start_date, end_date) VALUES ('FY27', '2026-10-01', '2027-09-30')"
    ).lastrowid
    add_project(conn, add_cost_code(conn, other_fy), "next_year")
    assert [b.project_name for b in allocation.list_balances(conn, fy["id"])] == ["alpha_main"]
    assert [b.project_name for b in allocation.list_balances(conn, other_fy)] == ["next_year"]


def test_update_project_validation(conn, project):
    with pytest.raises(ValidationError, match="Status"):
        allocation.update_project(conn, project, "x", "paused")
    allocation.update_project(conn, project, "alpha_core", "cancelled")
    assert allocation.get_project(conn, project)["name"] == "alpha_core"


def test_list_projects_hides_cancelled_by_default(conn, fy, cost_code, project):
    add_project(conn, cost_code, "old", status="cancelled")
    assert [p["name"] for p in allocation.list_projects(conn, fy["id"])] == ["alpha_main"]
    assert len(allocation.list_projects(conn, fy["id"], include_cancelled=True)) == 2


def test_delete_project_only_when_nothing_points_at_it(conn, fy, cost_code, project):
    empty = add_project(conn, cost_code, "mistake")
    allocation.delete_project(conn, empty)
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 10))
    with pytest.raises(ValidationError, match="cancelled"):
        allocation.delete_project(conn, project)


def test_saved_intention_also_blocks_project_delete(conn, fy, project):
    from fridayfree.modules.changes import service as changes
    changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 10)])
    assert not allocation.can_delete_project(conn, project)
    changes.discard(conn, fy["id"])
    assert allocation.can_delete_project(conn, project)


def test_delete_cost_code_removes_empty_projects_or_refuses(conn, fy):
    code = add_cost_code(conn, fy["id"], charge_string="9>PRJ1 - A>PT1: B")
    add_project(conn, code, "empty")
    allocation.delete_cost_code(conn, code)
    assert allocation.list_cost_codes(conn, fy["id"]) == []

    code = add_cost_code(conn, fy["id"], charge_string="9>PRJ2 - A>PT2: B")
    used = add_project(conn, code, "used")
    approve_items(conn, fy["id"], WorkItem(used, "allocated", 5))
    with pytest.raises(ValidationError, match="used"):
        allocation.delete_cost_code(conn, code)
    assert len(allocation.list_projects(conn, fy["id"])) == 1   # nothing was removed


def test_ledger_listing_filters(conn, fy, cost_code, project):
    other = add_project(conn, cost_code, "alpha_travel")
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), WorkItem(other, "allocated", 40))
    assert len(allocation.list_ledger(conn, fy["id"])) == 2
    rows = allocation.list_ledger(conn, fy["id"], project_id=other)
    assert [(r["project_name"], r["entry_type"], r["hours"]) for r in rows] == [("alpha_travel", "fund", 40)]
    assert len(allocation.list_ledger(conn, fy["id"], cost_code_id=cost_code)) == 2
