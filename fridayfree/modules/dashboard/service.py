"""Dashboard aggregations. Pure functions over a changes.State, so the same code renders the approved
state or the final state including saved intentions."""
from dataclasses import dataclass
from datetime import date

import pandas as pd

from fridayfree.utils.dates import current_week, fy_weeks

PACE_WEEKS = 4


@dataclass(frozen=True)
class CostCodeSummary:
    cost_code_id: int
    cost_code_name: str
    charge_string: str
    allocated: float
    spent: float
    reserved: float
    frozen: float
    available: float
    balance: float

    @property
    def overdrawn(self) -> bool:
        return self.balance < 0

    @property
    def pct_remaining(self):
        return self.available / self.allocated if self.allocated > 0 else None


@dataclass(frozen=True)
class Projection:
    avg_weekly: float          # pace over the last few completed weeks
    weeks_left: int            # including the current week
    spent: float
    projected_total: float
    total_allocated: float
    series: pd.DataFrame       # week_start, projected (cumulative), from the last completed week to FY end


def chargeable_now(state) -> dict:
    """What can I charge this week? Held = has reserved/frozen hours (do not charge those)."""
    active = [b for b in state.balances if b.status == "active"]
    return {
        "chargeable": sorted((b for b in active if b.available > 0), key=lambda b: -b.available),
        "held": sorted((b for b in active if b.held > 0), key=lambda b: -b.held),
        "overdrawn": sorted((b for b in state.balances if b.overdrawn), key=lambda b: b.balance),
    }


def cost_code_summary(state) -> list[CostCodeSummary]:
    groups = {}
    for b in state.balances:
        groups.setdefault(b.cost_code_id, []).append(b)
    return [
        CostCodeSummary(
            cost_code_id=cost_code_id,
            cost_code_name=members[0].cost_code_name,
            charge_string=members[0].charge_string,
            **{f: round(sum(getattr(b, f) for b in members), 2)
               for f in ("allocated", "spent", "reserved", "frozen", "available", "balance")},
        )
        for cost_code_id, members in groups.items()
    ]


def totals(state) -> CostCodeSummary:
    """Everything in the fiscal year added up (same columns as a cost code)."""
    return CostCodeSummary(
        cost_code_id=0, cost_code_name="All cost codes", charge_string="",
        **{f: round(sum(getattr(b, f) for b in state.balances), 2)
           for f in ("allocated", "spent", "reserved", "frozen", "available", "balance")},
    )


def overdraft_alerts(state) -> list[str]:
    alerts = [f"Cost code {c.cost_code_name} is overdrawn by {-c.balance:g} h."
              for c in cost_code_summary(state) if c.overdrawn]
    alerts += [f"{b.project_name} is overdrawn by {-b.balance:g} h." for b in state.balances if b.overdrawn]
    return alerts


def _hours_by_week(state) -> dict:
    if state.weekly.empty:
        return {}
    return state.weekly.groupby("week_start")["hours"].sum().to_dict()


def weekly_burn(state, fy: dict, today: date) -> pd.DataFrame:
    """Hours per week from FY start to the current week (or the last week with hours), zero-filled."""
    by_week = _hours_by_week(state)
    last = max([current_week(today), *by_week]) if by_week else current_week(today)
    weeks = [w for w in fy_weeks(fy["start_date"], fy["end_date"]) if w <= last]
    return pd.DataFrame({"week_start": weeks, "hours": [round(by_week.get(w, 0.0), 2) for w in weeks]})


def total_allocated(state) -> float:
    return round(sum(b.allocated for b in state.balances), 2)


def cumulative_vs_allocation(state, fy: dict, today: date) -> pd.DataFrame:
    burn = weekly_burn(state, fy, today)
    burn["cumulative_hours"] = burn["hours"].cumsum().round(2)
    burn["allocation"] = total_allocated(state)
    return burn[["week_start", "cumulative_hours", "allocation"]]


def project_end_of_fy(state, fy: dict, today: date) -> Projection:
    """Straight-line projection at the average pace of the last few completed weeks (zeros count)."""
    by_week = _hours_by_week(state)
    this_week = current_week(today)
    weeks = fy_weeks(fy["start_date"], fy["end_date"])
    completed = [w for w in weeks if w < this_week]
    remaining = [w for w in weeks if w >= this_week]
    recent = completed[-PACE_WEEKS:]
    avg = round(sum(by_week.get(w, 0.0) for w in recent) / len(recent), 2) if recent else 0.0

    spent = round(sum(by_week.values()), 2)
    running = sum(by_week.get(w, 0.0) for w in completed)
    points = [(completed[-1], round(running, 2))] if completed else []
    for w in remaining:
        running += max(by_week.get(w, 0.0), avg)    # a week already logged above pace keeps its real hours
        points.append((w, round(running, 2)))
    return Projection(
        avg_weekly=avg,
        weeks_left=len(remaining),
        spent=spent,
        projected_total=round(running, 2),
        total_allocated=total_allocated(state),
        series=pd.DataFrame(points, columns=["week_start", "projected"]),
    )
