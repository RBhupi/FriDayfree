"""Shared pieces for the week's plan.

Two layers of state, no more:
  approved — in the database
  planned  — saved in <database>.intentions.json, waiting to be approved
"""
from datetime import date

import streamlit as st

from fridayfree.modules.changes import service as changes
from fridayfree.modules.shared_ui import AppContext
from fridayfree.utils.dates import default_week, pickable_weeks, week_label


def planned_items(ctx: AppContext) -> list:
    return changes.get_saved_items(ctx.conn, ctx.fy["id"])


def current_state(ctx: AppContext, approved_only: bool = False):
    """The numbers to show: approved, optionally with this week's plan applied on top."""
    return changes.load_state(ctx.conn, ctx.fy["id"], () if approved_only else planned_items(ctx))


def pending_badge(ctx: AppContext) -> None:
    """Sidebar reminder shown on every page while hours are planned but not approved."""
    planned = changes.pending_count(ctx.conn, ctx.fy["id"])
    if planned:
        st.sidebar.warning(f"{planned} planned hour entr{'y' if planned == 1 else 'ies'} not approved yet.\n\n"
                           "Approve them on This week.", icon=":material/edit:")


def week_picker(ctx: AppContext, key: str) -> date:
    weeks = pickable_weeks(ctx.fy["start_date"], ctx.fy["end_date"], ctx.today)
    default = default_week(ctx.fy["start_date"], ctx.fy["end_date"], ctx.today)
    index = weeks.index(default) if default in weeks else 0
    return st.selectbox("Week", weeks, index=index, format_func=week_label, key=f"{key}_{ctx.fy['id']}")
