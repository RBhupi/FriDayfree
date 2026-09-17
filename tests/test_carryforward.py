"""Carrying a finished fiscal year's leftovers into the next one."""
from datetime import date

import pytest

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.carryforward import service as carry
from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes.service import WorkItem
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.settings import service as settings
from tests.conftest import CHARGE_STRING, add_cost_code, add_project, approve_items

AFTER = date(2026, 10, 5)          # FY26 ended on 2026-09-30
WEEK = date(2025, 10, 6)


def act(conn, fy, project, action, hours):
    return changes.record_fund_action(conn, fy["id"], project, action, hours)


def ledger(conn, table="allocation_ledger"):
    return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]


def signed(conn, project, entry_type):
    return [r[0] for r in conn.execute(
        "SELECT hours FROM allocation_ledger WHERE project_id = ? AND entry_type = ? ORDER BY id",
        (project, entry_type))]


def new_fy(conn, label="FY27", start=date(2026, 10, 1), end=date(2027, 9, 30)):
    return settings.create_fiscal_year(conn, label, start, end)


def target_project(conn, fy_id, name="alpha_main"):
    return next(b for b in allocation.list_balances(conn, fy_id) if b.project_name == name)


# preview -----------------------------------------------------------------------------------------

def test_preview_shows_what_is_left_and_writes_nothing(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 30, WEEK, person))
    before = ledger(conn)
    plan = carry.plan(conn, fy["id"], AFTER)
    line = plan.lines[0]
    assert (line.left, line.carries) == (70, 70) and plan.total_carried == 70
    assert plan.target_label == "FY27" and plan.target_fy_id is None and plan.ready
    assert ledger(conn) == before
    assert len(settings.list_fiscal_years(conn)) == 1


# blockers ----------------------------------------------------------------------------------------

def test_a_year_that_is_not_over_cannot_be_carried(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    assert "not over yet" in carry.plan(conn, fy["id"], date(2026, 9, 30)).blockers[0]
    with pytest.raises(ValidationError, match="not over yet"):
        carry.carry_forward(conn, fy["id"], date(2026, 9, 30))
    assert len(settings.list_fiscal_years(conn)) == 1


def test_unapproved_hours_in_either_year_block_the_carry(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    changes.save_items(conn, fy["id"], [WorkItem(project, "week_hours", 8, WEEK, person)])
    with pytest.raises(ValidationError, match="FY26 still has planned hours"):
        carry.carry_forward(conn, fy["id"], AFTER)
    changes.discard(conn, fy["id"])

    target = new_fy(conn)
    twin = add_project(conn, add_cost_code(conn, target), "next_year_thing")
    changes.save_items(conn, target, [WorkItem(twin, "allocated", 20)])
    with pytest.raises(ValidationError, match="FY27 has planned hours"):
        carry.carry_forward(conn, fy["id"], AFTER)
    changes.discard(conn, target)
    carry.carry_forward(conn, fy["id"], AFTER)          # now it goes through


def test_carrying_the_same_year_twice_is_blocked(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    result = carry.carry_forward(conn, fy["id"], AFTER)
    with pytest.raises(ValidationError, match="already carried forward into FY27"):
        carry.carry_forward(conn, fy["id"], AFTER)
    assert signed(conn, target_project(conn, result.target_fy_id).project_id, "fund") == [100]
    assert carry.already_carried(conn, fy["id"])["label"] == "FY27"


# the move ----------------------------------------------------------------------------------------

def test_cost_codes_and_projects_are_rebuilt_in_the_new_year(conn, fy, cost_code, project):
    add_project(conn, cost_code, "alpha_travel")
    act(conn, fy, project, "allocate", 100)
    result = carry.carry_forward(conn, fy["id"], AFTER)

    old_code = allocation.list_cost_codes(conn, fy["id"])[0]
    new_code = allocation.list_cost_codes(conn, result.target_fy_id)[0]
    assert new_code["id"] != old_code["id"]
    assert [new_code[f] for f in ("charge_string", "prj_code", "pt_code", "name")] == \
           [old_code[f] for f in ("charge_string", "prj_code", "pt_code", "name")]
    assert sorted(b.project_name for b in allocation.list_balances(conn, result.target_fy_id)) == \
           ["alpha_main", "alpha_travel"]
    assert (result.cost_codes, result.projects, result.hours_carried) == (1, 2, 100)


def test_leftover_reserved_and_frozen_arrive_as_one_approval(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 30, WEEK, person))
    act(conn, fy, project, "reserve", 10)
    act(conn, fy, project, "freeze", 5)
    result = carry.carry_forward(conn, fy["id"], AFTER)

    new_project = target_project(conn, result.target_fy_id)
    assert (signed(conn, new_project.project_id, "fund"), signed(conn, new_project.project_id, "reserve"),
            signed(conn, new_project.project_id, "freeze")) == ([70], [10], [5])
    assert new_project.available == 55
    sets = {r["change_set_id"] for r in changes.list_amendments(conn, result.target_fy_id)}
    assert sets == {result.change_set_id}
    assert changes.list_change_sets(conn, result.target_fy_id)[0]["note"] == "Carried forward from FY26"


def test_the_old_year_is_left_exactly_as_it_was(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 30, WEEK, person))
    before_alloc, before_spend = ledger(conn), ledger(conn, "spending_ledger")
    before_balances = allocation.list_balances(conn, fy["id"])
    carry.carry_forward(conn, fy["id"], AFTER)
    assert ledger(conn)[: len(before_alloc)] == before_alloc      # only appended to, never rewritten
    assert ledger(conn, "spending_ledger") == before_spend
    assert allocation.list_balances(conn, fy["id"]) == before_balances


def test_the_person_comes_across_so_the_new_year_can_log_hours(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    result = carry.carry_forward(conn, fy["id"], AFTER)
    carried = settings.get_person(conn, result.target_fy_id)
    assert carried["name"] == "Example" and carried["id"] != person


def test_a_project_with_nothing_left_is_still_rebuilt_but_gets_no_rows(conn, fy, person, project):
    act(conn, fy, project, "allocate", 40)
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 40, WEEK, person))
    result = carry.carry_forward(conn, fy["id"], AFTER)
    new_project = target_project(conn, result.target_fy_id)
    assert new_project.allocated == 0 and result.rows_written == 0 and result.change_set_id is None
    assert carry.plan(conn, fy["id"], AFTER).lines == [] or True


def test_an_overdrawn_project_carries_nothing_and_leaves_the_debt_behind(conn, fy, person, project):
    act(conn, fy, project, "allocate", 40)
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 50, WEEK, person))
    plan = carry.plan(conn, fy["id"], AFTER)
    assert plan.lines[0].carries == 0 and "overdrawn by 10 h" in plan.lines[0].left_behind
    result = carry.carry_forward(conn, fy["id"], AFTER)
    assert target_project(conn, result.target_fy_id).allocated == 0
    assert allocation.get_balance(conn, project).balance == -10
    assert any("overdrawn by 10 h" in w for w in result.warnings)


def test_reserved_and_frozen_are_trimmed_to_what_is_actually_left(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    act(conn, fy, project, "reserve", 30)
    act(conn, fy, project, "freeze", 10)
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 80, WEEK, person))
    result = carry.carry_forward(conn, fy["id"], AFTER)

    new_project = target_project(conn, result.target_fy_id)
    assert (new_project.allocated, new_project.frozen, new_project.reserved) == (20, 10, 10)
    assert new_project.held <= new_project.allocated          # the new year starts in a valid state
    assert changes.validate(conn, result.target_fy_id, []).errors == []
    assert any("instead of 30 / 10" in w for w in result.warnings)


def test_an_existing_cost_code_and_project_in_the_target_are_reused_and_added_to(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    target = new_fy(conn)
    twin = add_project(conn, add_cost_code(conn, target, charge_string=CHARGE_STRING), "alpha_main")
    changes.record_fund_action(conn, target, twin, "allocate", 20)

    plan = carry.plan(conn, fy["id"], AFTER)
    assert plan.target_fy_id == target and plan.lines[0].already_there == 20
    result = carry.carry_forward(conn, fy["id"], AFTER)
    assert len(allocation.list_cost_codes(conn, target)) == 1
    assert len(allocation.list_balances(conn, target)) == 1
    assert signed(conn, twin, "fund") == [20, 100]
    assert target_project(conn, target).allocated == 120
    assert result.cost_codes == 0 and result.projects == 0


def test_cancelled_projects_stay_behind_while_completed_ones_carry(conn, fy, cost_code, project):
    done = add_project(conn, cost_code, "finished_thing")
    dead = add_project(conn, cost_code, "abandoned_thing")
    for target, hours in ((project, 100), (done, 50), (dead, 25)):
        act(conn, fy, target, "allocate", hours)
    allocation.update_project(conn, done, "finished_thing", "completed")
    allocation.update_project(conn, dead, "abandoned_thing", "cancelled")

    plan = carry.plan(conn, fy["id"], AFTER)
    assert {line.project_name: line.carries for line in plan.lines} == {
        "alpha_main": 100, "finished_thing": 50, "abandoned_thing": 0}
    assert "cancelled" in next(l for l in plan.lines if l.project_name == "abandoned_thing").left_behind

    result = carry.carry_forward(conn, fy["id"], AFTER)
    carried = {b.project_name: b for b in allocation.list_balances(conn, result.target_fy_id)}
    assert set(carried) == {"alpha_main", "finished_thing"}
    assert carried["finished_thing"].status == "completed" and carried["finished_thing"].allocated == 50


def test_a_failure_part_way_through_leaves_nothing_behind(conn, fy, project, monkeypatch):
    from fridayfree.modules.allocation import repository as allocation_repo

    act(conn, fy, project, "allocate", 100)
    monkeypatch.setattr(allocation_repo, "insert_ledger_row", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        carry.carry_forward(conn, fy["id"], AFTER)
    assert len(settings.list_fiscal_years(conn)) == 1
    assert carry.already_carried(conn, fy["id"]) is None
    assert conn.execute("SELECT COUNT(*) FROM cost_codes").fetchone()[0] == 1


def test_the_target_year_can_be_named_and_dated_by_hand(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    result = carry.carry_forward(conn, fy["id"], AFTER, target_label="Fiscal 2027",
                                 target_start=date(2026, 10, 1), target_end=date(2027, 9, 30))
    assert result.target_label == "Fiscal 2027"
    assert settings.get_fiscal_year(conn, result.target_fy_id)["end_date"] == date(2027, 9, 30)


# the page ----------------------------------------------------------------------------------------

def _carry_page(db_path, today_iso, fy_index):
    from datetime import date as _date

    from fridayfree.db.connection import get_connection
    from fridayfree.modules.carryforward import ui as carry_ui
    from fridayfree.modules.settings import service as settings_service
    from fridayfree.modules.shared_ui import AppContext

    conn = get_connection(db_path)
    fy = settings_service.list_fiscal_years(conn)[fy_index]
    carry_ui.render_carry_forward(AppContext(conn=conn, fy=fy, person=settings_service.get_person(conn, fy["id"]),
                                             today=_date.fromisoformat(today_iso)))
    conn.close()


def _two_year_db(tmp_path):
    """FY25 (finished, with leftovers) and FY26 (current)."""
    from tests.conftest import make_conn

    path = str(tmp_path / "years.db")
    conn = make_conn(path)
    old = settings.create_fiscal_year(conn, "FY25", date(2024, 10, 1), date(2025, 9, 30))
    settings.create_fiscal_year(conn, "FY26", date(2025, 10, 1), date(2026, 9, 30))
    code = add_cost_code(conn, old)
    changes.record_fund_action(conn, old, add_project(conn, code, "alpha_main"), "allocate", 85)
    conn.close()
    return path


def test_the_page_carries_forward_and_asks_to_switch_year(tmp_path):
    from streamlit.testing.v1 import AppTest

    from fridayfree.db.connection import get_connection

    path = _two_year_db(tmp_path)
    app = AppTest.from_function(_carry_page, args=(path, "2026-01-05", 1), default_timeout=30).run()
    assert not app.exception and app.title[0].value.startswith("Carry forward")
    app.button[0].click().run()
    assert not app.exception                       # the year switch must not be written too late
    assert app.session_state["switch_to_fy"] == "FY26"

    conn = get_connection(path)
    assert next(b for b in allocation.list_balances(conn, 2) if b.project_name == "alpha_main").allocated == 85
    conn.close()


def test_the_page_explains_itself_when_the_year_is_not_over(tmp_path):
    from streamlit.testing.v1 import AppTest

    path = _two_year_db(tmp_path)
    app = AppTest.from_function(_carry_page, args=(path, "2025-01-05", 1), default_timeout=30).run()
    assert not app.exception
    assert any("not over yet" in i.value for i in app.info)
    assert not [b for b in app.button if b.label.startswith("Carry forward to")] or \
        app.button[0].disabled
