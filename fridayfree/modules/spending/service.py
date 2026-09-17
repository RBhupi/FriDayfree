"""Read side of weekly spending. Hours are written only by modules.changes (save -> approve)."""
from datetime import date

import pandas as pd

from fridayfree.modules.spending import repository as repo

WEEKLY_COLUMNS = ["week_start", "project_id", "hours"]


def list_week_entries(conn, fy_id: int, week_start: date = None, project_id=None) -> list[dict]:
    """Net entries the user sees: one per project per week, zero-net entries hidden."""
    return repo.net_entries(conn, fy_id, week_start=week_start, project_id=project_id)


def list_entry_history(conn, person_id: int, project_id: int, week_start: date) -> list[dict]:
    """Every signed revision behind one net entry, oldest first."""
    return repo.entry_history(conn, person_id, project_id, week_start)


def week_total(conn, fy_id: int, week_start: date) -> float:
    return round(sum(e["hours"] for e in list_week_entries(conn, fy_id, week_start=week_start)), 2)


def week_net(conn, fy_id: int, person_id: int, project_id: int, week_start: date) -> dict:
    """Approved net for one person/project/week (zeros when nothing is logged)."""
    for e in repo.net_entries(conn, fy_id, week_start=week_start, project_id=project_id, include_zero=True):
        if e["person_id"] == person_id:
            return e
    return {"hours": 0.0, "dollars": None, "notes": None, "revisions": 0}


def week_nets(conn, fy_id: int) -> pd.DataFrame:
    """Net hours per (week_start, project_id) across people, as a DataFrame."""
    entries = list_week_entries(conn, fy_id)
    if not entries:
        return pd.DataFrame(columns=WEEKLY_COLUMNS)
    df = pd.DataFrame(entries)[WEEKLY_COLUMNS]
    return df.groupby(["week_start", "project_id"], as_index=False)["hours"].sum()
