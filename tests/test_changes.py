import json
from datetime import date

import pytest

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes.service import WorkItem
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.spending import repository as spending_repo
from fridayfree.modules.spending import service as spending
from tests.conftest import add_cost_code, add_project, approve_items, make_conn

WEEK = date(2025, 10, 6)


def ledger(conn, table="allocation_ledger"):
    return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]


def signed(conn, project, entry_type):
    rows = conn.execute(
        "SELECT hours FROM allocation_ledger WHERE project_id = ? AND entry_type = ? ORDER BY id", (project, entry_type)
    )
    return [r[0] for r in rows]


# pure --------------------------------------------------------------------------------------------

def test_merge_items_working_overrides_saved_on_same_cell():
    saved = [WorkItem(1, "allocated", 100), WorkItem(1, "reserved", 10)]
    working = [WorkItem(1, "allocated", 150), WorkItem(2, "frozen", 5)]
    merged = {i.key: i.target_value for i in changes.merge_items(saved, working)}
    assert merged == {(1, "allocated", None): 150, (1, "reserved", None): 10, (2, "frozen", None): 5}


# load_state --------------------------------------------------------------------------------------

def test_load_state_without_items_is_the_approved_state(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), WorkItem(project, "week_hours", 8, WEEK, person))
    state = changes.load_state(conn, fy["id"])
    assert state.balances == allocation.list_balances(conn, fy["id"])
    assert state.pending_keys == frozenset()
    assert state.weekly.to_dict("records") == [{"week_start": WEEK, "project_id": project, "hours": 8.0}]


def test_load_state_applies_targets_without_writing(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), WorkItem(project, "week_hours", 8, WEEK, person))
    before = ledger(conn) + ledger(conn, "spending_ledger")
    items = [
        WorkItem(project, "allocated", 150), WorkItem(project, "reserved", 40), WorkItem(project, "frozen", 10),
        WorkItem(project, "week_hours", 20, WEEK, person),
        WorkItem(project, "week_hours", 5, date(2025, 10, 13), person),
    ]
    state = changes.load_state(conn, fy["id"], items)
    b = state.balances[0]
    assert (b.allocated, b.reserved, b.frozen, b.spent, b.available) == (150, 40, 10, 25, 75)
    assert state.pending_keys == frozenset(i.key for i in items)
    assert dict(zip(state.weekly["week_start"], state.weekly["hours"])) == {WEEK: 20.0, date(2025, 10, 13): 5.0}
    assert ledger(conn) + ledger(conn, "spending_ledger") == before


def test_targets_equal_to_approved_are_not_pending(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    assert changes.load_state(conn, fy["id"], [WorkItem(project, "allocated", 100)]).pending_keys == frozenset()


# save --------------------------------------------------------------------------------------------

def test_save_persists_across_connections(tmp_path):
    path = str(tmp_path / "t.db")
    conn = make_conn(path)
    fy_id = conn.execute(
        "INSERT INTO fiscal_years(label, start_date, end_date) VALUES ('FY26', '2025-10-01', '2026-09-30')"
    ).lastrowid
    project = add_project(conn, add_cost_code(conn, fy_id))
    items = [WorkItem(project, "allocated", 100, reason="initial"), WorkItem(project, "reserved", 40)]
    changes.save_items(conn, fy_id, items, note="plan for Q1")
    conn.close()

    stored = json.loads((tmp_path / "t.intentions.json").read_text())             # a JSON file, not the database
    assert [i["project"] for i in stored["fiscal_years"][str(fy_id)]["items"]] == ["alpha_main", "alpha_main"]

    reopened = make_conn(path)
    assert changes.get_saved_items(reopened, fy_id) == items
    assert changes.get_saved_note(reopened, fy_id) == "plan for Q1"
    assert changes.pending_count(reopened, fy_id) == 2
    assert ledger(reopened) == []                      # saved is an intention, not in the system
    assert allocation.get_balance(reopened, project).allocated == 0
    reopened.close()


def test_resave_replaces_what_was_saved(conn, fy, project):
    assert changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 100)]) == 1
    assert changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 120), WorkItem(project, "frozen", 5)]) == 2
    assert {i.key: i.target_value for i in changes.get_saved_items(conn, fy["id"])} == {
        (project, "allocated", None): 120, (project, "frozen", None): 5}


def test_save_drops_noops_and_deletes_empty_set(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 130)])
    assert changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 100)]) == 0
    assert changes.get_saved_items(conn, fy["id"]) == []


# validation --------------------------------------------------------------------------------------

def test_validation_errors_block_save(conn, fy, person, cost_code, project):
    cancelled = add_project(conn, cost_code, "dead", status="cancelled")
    cases = [
        (WorkItem(project, "allocated", -1), "negative"),
        (WorkItem(project, "reserved", 10), "more than the allocation"),
        (WorkItem(project, "week_hours", 8, date(2025, 10, 7), person), "not a Monday"),
        (WorkItem(project, "week_hours", 8, date(2027, 1, 4), person), "inside FY26"),
        (WorkItem(project, "week_hours", 8, WEEK, None), "person"),
        (WorkItem(cancelled, "week_hours", 8, WEEK, person), "cancelled"),
        (WorkItem(9999, "allocated", 5), "not in this fiscal year"),
    ]
    for item, message in cases:
        with pytest.raises(ValidationError, match=message):
            changes.save_items(conn, fy["id"], [item])
    assert changes.get_saved_items(conn, fy["id"]) == []


def test_hours_on_cancelled_project_can_be_reduced(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 40), WorkItem(project, "week_hours", 8, WEEK, person))
    allocation.update_project(conn, project, "alpha_main", "cancelled")
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 3, WEEK, person))
    assert allocation.get_balance(conn, project).spent == 3


def test_overdraft_and_held_breach_warn_but_do_not_block(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 40), WorkItem(project, "frozen", 35))
    dips = changes.validate(conn, fy["id"], [WorkItem(project, "week_hours", 10, WEEK, person)])
    assert dips.errors == [] and "dips 5 h into reserved/frozen" in dips.warnings[0]
    over = changes.validate(conn, fy["id"], [WorkItem(project, "week_hours", 50, WEEK, person)])
    assert over.errors == []
    assert any("alpha_main will be overdrawn by 10 h" in w for w in over.warnings)
    assert any(w.startswith("Cost code") for w in over.warnings)
    result = approve_items(conn, fy["id"], WorkItem(project, "week_hours", 50, WEEK, person))
    assert result.rows_written == 1 and result.warnings


# approve -----------------------------------------------------------------------------------------

def test_approve_appends_signed_deltas_and_never_mutates(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100, reason="initial"))
    snapshot = ledger(conn)
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 120))
    assert ledger(conn)[: len(snapshot)] == snapshot
    snapshot = ledger(conn)
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 90))
    assert ledger(conn)[: len(snapshot)] == snapshot
    assert signed(conn, project, "fund") == [100, 20, -30]
    assert allocation.get_balance(conn, project).allocated == 90


def test_reserve_and_freeze_are_amendments(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    approve_items(conn, fy["id"], WorkItem(project, "reserved", 40, reason="conference"), WorkItem(project, "frozen", 25))
    assert allocation.get_balance(conn, project).available == 35
    approve_items(conn, fy["id"], WorkItem(project, "reserved", 0), WorkItem(project, "frozen", 10))
    assert signed(conn, project, "reserve") == [40, -40]
    assert signed(conn, project, "freeze") == [25, -15]
    assert allocation.get_balance(conn, project).available == 90


def test_reason_is_optional(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    assert conn.execute("SELECT reason FROM allocation_ledger").fetchone()[0] is None


def test_week_hours_edit_and_delete_append_corrections(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 8, WEEK, person, reason="first"))
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 5, WEEK, person))
    entry = spending.list_week_entries(conn, fy["id"], week_start=WEEK)[0]
    assert (entry["hours"], entry["revisions"], entry["notes"]) == (5, 2, "first")
    assert spending.week_total(conn, fy["id"], WEEK) == 5

    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 0, WEEK, person))
    assert spending.list_week_entries(conn, fy["id"]) == []                       # net zero is hidden
    history = spending.list_entry_history(conn, person, project, WEEK)
    assert [h["hours"] for h in history] == [8, -3, -5]                          # but nothing was erased
    assert allocation.get_balance(conn, project).spent == 0


def test_note_only_change_is_recorded_as_zero_hour_row(conn, fy, person, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), WorkItem(project, "week_hours", 8, WEEK, person))
    approve_items(conn, fy["id"], WorkItem(project, "week_hours", 8, WEEK, person, reason="Analysis review"))
    entry = spending.list_week_entries(conn, fy["id"])[0]
    assert (entry["hours"], entry["notes"], entry["revisions"]) == (8, "Analysis review", 2)
    assert changes.save_items(conn, fy["id"], [WorkItem(project, "week_hours", 8, WEEK, person, reason="Analysis review")]) == 0


def test_move_between_projects_is_one_change_set(conn, fy, cost_code, project):
    other = add_project(conn, cost_code, "alpha_travel")
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), WorkItem(other, "allocated", 50))
    result = approve_items(conn, fy["id"], WorkItem(project, "allocated", 90), WorkItem(other, "allocated", 60),
                           note="cover travel")
    rows = changes.list_amendments(conn, fy["id"], change_set_id=result.change_set_id)
    assert sorted((r["project_name"], r["hours"]) for r in rows) == [("alpha_main", -10), ("alpha_travel", 10)]
    assert sum(b.allocated for b in allocation.list_balances(conn, fy["id"])) == 150


def test_approve_empties_the_intentions_and_records_the_approval(conn, fy, project):
    first = approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), note="kickoff")
    assert changes.get_saved_items(conn, fy["id"]) == [] and changes.get_saved_note(conn, fy["id"]) is None
    changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 110)])      # a new intention, not in history
    history = changes.list_change_sets(conn, fy["id"])
    assert [(h["id"], h["note"], h["amendments"]) for h in history] == [(first.change_set_id, "kickoff", 1)]


def test_approve_with_nothing_saved_raises(conn, fy):
    with pytest.raises(ValidationError, match="nothing saved"):
        changes.approve(conn, fy["id"])


def test_approve_is_atomic(conn, fy, person, project, monkeypatch):
    changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 100),
                                        WorkItem(project, "week_hours", 8, WEEK, person)])

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(spending_repo, "insert_spending_row", boom)
    with pytest.raises(RuntimeError):
        changes.approve(conn, fy["id"])
    assert ledger(conn) == [] and ledger(conn, "spending_ledger") == []
    assert changes.pending_count(conn, fy["id"]) == 2          # still saved, still an intention


def test_stale_saved_items_that_became_true_write_nothing(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 120)])
    # the same number gets into the system another way before approval
    cs = conn.execute("INSERT INTO change_sets(fy_id) VALUES (?)", (fy["id"],)).lastrowid
    conn.execute("INSERT INTO allocation_ledger(change_set_id, project_id, entry_type, hours) VALUES (?, ?, 'fund', 20)",
                 (cs, project))
    conn.commit()
    result = changes.approve(conn, fy["id"])
    assert result.rows_written == 0 and result.change_set_id is None
    assert changes.get_saved_items(conn, fy["id"]) == []
    assert len(changes.list_change_sets(conn, fy["id"])) == 2                     # no empty approval recorded
    assert signed(conn, project, "fund") == [100, 20]


def test_discard_leaves_ledgers_untouched(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    before = ledger(conn)
    changes.save_items(conn, fy["id"], [WorkItem(project, "allocated", 10)])
    changes.discard(conn, fy["id"])
    changes.discard(conn, fy["id"])   # harmless when nothing is open
    assert ledger(conn) == before and changes.get_saved_items(conn, fy["id"]) == []


def test_week_nets_dataframe_sums_per_week_and_project(conn, fy, person, cost_code, project):
    other = add_project(conn, cost_code, "alpha_travel")
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100), WorkItem(other, "allocated", 100),
                  WorkItem(project, "week_hours", 8, WEEK, person), WorkItem(other, "week_hours", 4, WEEK, person))
    df = spending.week_nets(conn, fy["id"])
    assert list(df.columns) == ["week_start", "project_id", "hours"]
    assert df["hours"].sum() == 12 and len(df) == 2
    assert spending.week_nets(conn, 999).empty


def test_intentions_file_disappears_when_nothing_is_pending(tmp_path):
    path = str(tmp_path / "t.db")
    conn = make_conn(path)
    fy_id = conn.execute(
        "INSERT INTO fiscal_years(label, start_date, end_date) VALUES ('FY26', '2025-10-01', '2026-09-30')"
    ).lastrowid
    project = add_project(conn, add_cost_code(conn, fy_id))
    json_file = tmp_path / "t.intentions.json"
    changes.save_items(conn, fy_id, [WorkItem(project, "allocated", 100)])
    assert json_file.exists()
    changes.approve(conn, fy_id)
    assert not json_file.exists() and allocation.get_balance(conn, project).allocated == 100
    changes.save_items(conn, fy_id, [WorkItem(project, "allocated", 50)])
    changes.discard(conn, fy_id)
    assert not json_file.exists() and allocation.get_balance(conn, project).allocated == 100
    conn.close()
