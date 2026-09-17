from datetime import date, timedelta

import pandas as pd
import pytest

from fridayfree.modules.allocation.service import ProjectBalance
from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes.service import State, WorkItem
from fridayfree.modules.dashboard import service as dash
from tests.conftest import approve_items

FY = {"id": 1, "label": "FY26", "start_date": date(2025, 10, 1), "end_date": date(2026, 9, 30)}
W0 = date(2025, 9, 29)


def pb(pid, name, code, allocated, spent, reserved=0, frozen=0, status="active"):
    return ProjectBalance(pid, name, status, code, f"code{code}", f"9>PRJ{code} - X>PT{code}: Y",
                          allocated, spent, reserved, frozen)


def weekly(rows):
    return pd.DataFrame(rows, columns=["week_start", "project_id", "hours"])


@pytest.fixture
def state():
    balances = [
        pb(1, "healthy", 1, 100, 20),                 # 80 available, green
        pb(2, "amber", 1, 100, 80),                   # 20 available
        pb(3, "overdrawn", 2, 50, 60),                # -10
        pb(4, "iced", 2, 40, 0, reserved=10, frozen=30),   # fully held
        pb(5, "done", 2, 30, 10, status="completed"),
    ]
    return State(balances, weekly([(W0, 1, 20.0), (W0 + timedelta(weeks=2), 2, 80.0)]))


def test_chargeable_now_buckets_and_order(state):
    out = dash.chargeable_now(state)
    assert [b.project_name for b in out["chargeable"]] == ["healthy", "amber"]
    assert [b.project_name for b in out["held"]] == ["iced"]
    assert [b.project_name for b in out["overdrawn"]] == ["overdrawn"]


def test_cost_code_summary_sums_every_column(state):
    one, two = dash.cost_code_summary(state)
    assert (one.allocated, one.spent, one.available, one.balance) == (200, 100, 100, 100)
    assert (two.allocated, two.spent, two.reserved, two.frozen) == (120, 70, 10, 30)
    assert two.available == -10          # overdrawn -10 + iced 0 + completed 0
    assert not two.overdrawn and two.balance == 50
    assert one.pct_remaining == 0.5
    assert two.charge_string == "9>PRJ2 - X>PT2: Y"


def test_totals_add_up_every_project(state):
    total = dash.totals(state)
    assert (total.allocated, total.spent, total.reserved, total.frozen) == (320, 170, 10, 30)
    assert total.available == 90 and total.balance == 150 and not total.overdrawn


def test_overdraft_alerts_name_project_and_cost_code():
    state = State([pb(1, "a", 1, 10, 30), pb(2, "b", 1, 10, 0)], weekly([]))
    assert dash.overdraft_alerts(state) == ["Cost code code1 is overdrawn by 10 h.", "a is overdrawn by 20 h."]
    assert dash.overdraft_alerts(State([pb(1, "a", 1, 10, 3)], weekly([]))) == []


def test_weekly_burn_zero_fills_up_to_current_week(state):
    burn = dash.weekly_burn(state, FY, today=date(2025, 10, 22))
    assert list(burn["week_start"]) == [W0 + timedelta(weeks=i) for i in range(4)]
    assert list(burn["hours"]) == [20, 0, 80, 0]


def test_weekly_burn_extends_to_future_weeks_that_have_hours():
    state = State([pb(1, "a", 1, 100, 8)], weekly([(W0 + timedelta(weeks=5), 1, 8.0)]))
    assert len(dash.weekly_burn(state, FY, today=date(2025, 10, 1))) == 6


def test_cumulative_ends_at_total_spent(state):
    cum = dash.cumulative_vs_allocation(state, FY, today=date(2025, 10, 22))
    assert list(cum["cumulative_hours"]) == [20, 20, 100, 100]
    assert set(cum["allocation"]) == {320}


def test_projection_uses_last_four_completed_weeks():
    rows = [(W0 + timedelta(weeks=i), 1, h) for i, h in enumerate([40, 10, 20, 30, 20])]   # 5 completed weeks
    state = State([pb(1, "a", 1, 2000, 120)], weekly(rows))
    today = W0 + timedelta(weeks=5, days=2)                                                 # week 6, nothing logged yet
    p = dash.project_end_of_fy(state, FY, today)
    assert p.avg_weekly == 20                           # (10 + 20 + 30 + 20) / 4 — the 40 h week is too old
    assert p.weeks_left == 53 - 5
    assert p.projected_total == 120 + 20 * 48
    assert p.series.iloc[0].tolist() == [W0 + timedelta(weeks=4), 120]
    assert p.series.iloc[-1].tolist() == [date(2026, 9, 28), p.projected_total]


def test_projection_with_short_or_no_history():
    state = State([pb(1, "a", 1, 100, 30)], weekly([(W0, 1, 30.0)]))
    assert dash.project_end_of_fy(state, FY, W0 + timedelta(weeks=1)).avg_weekly == 30
    empty = dash.project_end_of_fy(State([pb(1, "a", 1, 100, 0)], weekly([])), FY, W0 + timedelta(weeks=9))
    assert (empty.avg_weekly, empty.projected_total, empty.total_allocated) == (0, 0, 100)


def test_projection_after_fy_end_is_just_what_was_spent(state):
    p = dash.project_end_of_fy(state, FY, date(2027, 1, 1))
    assert p.weeks_left == 0 and p.projected_total == p.spent == 100


def test_same_functions_show_approved_or_intended_state(conn, fy, project):
    approve_items(conn, fy["id"], WorkItem(project, "allocated", 100))
    intentions = [WorkItem(project, "frozen", 60)]
    approved = dash.chargeable_now(changes.load_state(conn, fy["id"]))
    intended = dash.chargeable_now(changes.load_state(conn, fy["id"], intentions))
    assert approved["chargeable"][0].available == 100 and approved["held"] == []
    assert intended["chargeable"][0].available == 40 and intended["held"][0].frozen == 60
