"""The six fund actions: each one is recorded immediately as a single signed row."""
from datetime import date

import pytest

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.changes import service as changes
from fridayfree.modules.errors import ValidationError
from tests.conftest import add_project, approve_items


def rows(conn):
    return [tuple(r) for r in conn.execute("SELECT * FROM allocation_ledger ORDER BY id")]


def signed(conn, project, entry_type):
    return [r[0] for r in conn.execute(
        "SELECT hours FROM allocation_ledger WHERE project_id = ? AND entry_type = ? ORDER BY id",
        (project, entry_type))]


def act(conn, fy, project, action, hours, note=None):
    return changes.record_fund_action(conn, fy["id"], project, action, hours, note)


def test_allocate_writes_one_row_and_one_approval(conn, fy, project):
    result = act(conn, fy, project, "allocate", 40, note="new funding")
    assert result.sentence == "Allocate 40 h to alpha_main"
    assert (result.before.allocated, result.after.allocated) == (0, 40)
    assert result.after.available == 40
    assert signed(conn, project, "fund") == [40]
    assert conn.execute("SELECT COUNT(*) FROM change_sets").fetchone()[0] == 1
    assert conn.execute("SELECT reason FROM allocation_ledger").fetchone()[0] == "new funding"


def test_note_is_optional_and_the_approval_still_says_what_happened(conn, fy, project):
    result = act(conn, fy, project, "allocate", 10)
    assert conn.execute("SELECT reason FROM allocation_ledger").fetchone()[0] is None
    assert conn.execute("SELECT note FROM change_sets").fetchone()[0] == result.sentence


@pytest.mark.parametrize("action, entry_type, expected", [
    ("deallocate", "fund", [100, -25]),
    ("reserve", "reserve", [25]),
    ("freeze", "freeze", [25]),
])
def test_each_action_appends_its_own_signed_row(conn, fy, project, action, entry_type, expected):
    act(conn, fy, project, "allocate", 100)
    act(conn, fy, project, action, 25)
    assert signed(conn, project, entry_type) == expected


def test_opposite_actions_return_to_the_starting_balance(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    for action, opposite in (("reserve", "unreserve"), ("freeze", "unfreeze"), ("deallocate", "allocate")):
        before = allocation.get_balance(conn, project)
        act(conn, fy, project, action, 30)
        act(conn, fy, project, opposite, 30)
        after = allocation.get_balance(conn, project)
        assert (after.allocated, after.reserved, after.frozen, after.available) == (
            before.allocated, before.reserved, before.frozen, before.available)


def test_nothing_already_written_is_ever_touched(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    snapshot = rows(conn)
    act(conn, fy, project, "reserve", 10)
    act(conn, fy, project, "deallocate", 20)
    assert rows(conn)[: len(snapshot)] == snapshot
    assert len(rows(conn)) == 3


@pytest.mark.parametrize("action, hours, message", [
    ("deallocate", 61, "60 h available"),
    ("reserve", 61, "60 h available"),
    ("freeze", 61, "60 h available"),
    ("unreserve", 11, "10 h currently reserved"),
    ("unfreeze", 31, "30 h currently frozen"),
])
def test_actions_are_limited_by_what_the_project_has(conn, fy, person, project, action, hours, message):
    act(conn, fy, project, "allocate", 100)
    act(conn, fy, project, "reserve", 10)
    act(conn, fy, project, "freeze", 30)
    assert allocation.get_balance(conn, project).available == 60
    with pytest.raises(ValidationError, match=message):
        act(conn, fy, project, action, hours)
    assert len(rows(conn)) == 3      # nothing was written


def test_spent_hours_are_not_deallocatable(conn, fy, person, project):
    act(conn, fy, project, "allocate", 100)
    approve_items(conn, fy["id"], changes.WorkItem(project, "week_hours", 30, date(2025, 10, 6), person))
    with pytest.raises(ValidationError, match="70 h available"):
        act(conn, fy, project, "deallocate", 71)
    act(conn, fy, project, "deallocate", 70)
    assert allocation.get_balance(conn, project).available == 0


@pytest.mark.parametrize("hours", [0, -5, None])
def test_hours_must_be_a_positive_number(conn, fy, project, hours):
    with pytest.raises(ValidationError, match="positive number"):
        act(conn, fy, project, "allocate", hours)


def test_allocating_to_a_cancelled_project_is_blocked_but_taking_back_is_not(conn, fy, cost_code):
    dead = add_project(conn, cost_code, "old_thing")
    act(conn, fy, dead, "allocate", 50)
    allocation.update_project(conn, dead, "old_thing", "cancelled")
    with pytest.raises(ValidationError, match="cancelled"):
        act(conn, fy, dead, "allocate", 10)
    act(conn, fy, dead, "deallocate", 50)          # taking the funds back is exactly what you want to do
    assert allocation.get_balance(conn, dead).allocated == 0


def test_preview_writes_nothing_and_reports_the_result(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    snapshot = rows(conn)
    after, errors, warnings = changes.preview_fund_action(conn, project, "reserve", 40)
    assert (after.reserved, after.available) == (40, 60) and errors == [] and warnings == []
    assert rows(conn) == snapshot
    _, errors, _ = changes.preview_fund_action(conn, project, "reserve", 140)
    assert errors and "100 h available" in errors[0]


def test_funds_can_be_pulled_back_off_a_project_that_is_not_active(conn, fy, cost_code):
    """available is 0 for a completed project, but its unspent hours must still be reclaimable."""
    done = add_project(conn, cost_code, "finished_thing")
    act(conn, fy, done, "allocate", 50)
    allocation.update_project(conn, done, "finished_thing", "completed")
    balance = allocation.get_balance(conn, done)
    assert balance.available == 0 and balance.free_hours == 50
    act(conn, fy, done, "deallocate", 50)
    assert allocation.get_balance(conn, done).allocated == 0


def test_max_hours_tells_the_ui_the_limit(conn, fy, project):
    act(conn, fy, project, "allocate", 100)
    act(conn, fy, project, "freeze", 25)
    balance = allocation.get_balance(conn, project)
    assert changes.max_hours(balance, "allocate") == float("inf")
    assert changes.max_hours(balance, "deallocate") == 75
    assert changes.max_hours(balance, "unfreeze") == 25
    assert changes.max_hours(balance, "unreserve") == 0


def test_recent_actions_read_back_with_an_undo(conn, fy, project):
    act(conn, fy, project, "allocate", 100, note="start of year")
    act(conn, fy, project, "freeze", 25)
    recent = changes.recent_fund_actions(conn, fy["id"])
    assert [(r["sentence"], r["undo_action"]) for r in recent] == [
        ("Freeze 25 h on alpha_main", "unfreeze"), ("Allocate 100 h to alpha_main", "deallocate")]
    assert recent[1]["reason"] == "start of year"
