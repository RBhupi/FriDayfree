from datetime import date, timedelta

import pandas as pd

from fridayfree.modules.allocation.service import ProjectBalance
from fridayfree.modules.changes.service import State
from fridayfree.modules.dashboard import charts
from fridayfree.modules.dashboard import service as dash
from fridayfree.utils.formatting import RISK_HEX

FY = {"id": 1, "label": "FY26", "start_date": date(2025, 10, 1), "end_date": date(2026, 9, 30)}
W0 = date(2025, 9, 29)


def pb(pid, name, allocated, spent, status="active"):
    return ProjectBalance(pid, name, status, 1, "code", "9>PRJ1 - X>PT1: Y", allocated, spent, 0, 0)


def make_state():
    rows = [(W0 + timedelta(weeks=i), 1, 10.0) for i in range(6)]
    balances = [pb(1, "healthy", 100, 20), pb(2, "low", 100, 85), pb(3, "over", 10, 40), pb(4, "closed", 50, 0, "completed")]
    return State(balances, pd.DataFrame(rows, columns=["week_start", "project_id", "hours"]))


def test_burn_chart_has_one_bar_series():
    fig = charts.burn_chart(dash.weekly_burn(make_state(), FY, W0 + timedelta(weeks=6)))
    assert len(fig.data) == 1 and fig.data[0].type == "bar" and len(fig.data[0].x) == 7


def test_remaining_chart_colours_and_labels_follow_risk():
    bar = charts.remaining_chart(make_state().balances).data[0]
    assert list(bar.y) == ["over", "low", "healthy"]                       # active only, worst at the bottom
    assert list(bar.marker.color) == [RISK_HEX["red"], RISK_HEX["amber"], RISK_HEX["green"]]
    assert bar.text[0].endswith("critical") and bar.text[2].endswith("healthy")   # never colour alone


def test_cumulative_chart_has_spent_projection_and_allocation():
    state, today = make_state(), W0 + timedelta(weeks=6)
    fig = charts.cumulative_chart(dash.cumulative_vs_allocation(state, FY, today), dash.project_end_of_fy(state, FY, today))
    assert [t.name for t in fig.data] == ["Spent (cumulative)", "Projected at current pace", "Total allocation"]
    assert fig.data[1].line.dash == "dash"
    assert fig.data[1].x[-1] == date(2026, 9, 28)


def test_cumulative_chart_without_projection():
    state = make_state()
    fig = charts.cumulative_chart(dash.cumulative_vs_allocation(state, FY, W0 + timedelta(weeks=6)))
    assert [t.name for t in fig.data] == ["Spent (cumulative)", "Total allocation"]
