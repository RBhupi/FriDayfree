"""Weekly spending pages: a focused hours grid and the net history."""
import pandas as pd
import streamlit as st

from fridayfree.modules.changes import ui as workspace
from fridayfree.modules.shared_ui import AppContext, export_controls, show_flashes
from fridayfree.modules.spending import service as spending
from fridayfree.utils.dates import week_label
from fridayfree.utils.formatting import format_hours


def render_log_hours(ctx: AppContext) -> None:
    st.title(f"Log hours · {ctx.fy['label']}")
    show_flashes()
    st.caption("One number per project per week. Type the total you charged; to remove an entry set it to 0. "
               "**Save** keeps it as an intention; **Approve** puts it in the system.")
    week = workspace.week_picker(ctx, key="log_week")
    state = workspace.current_state(ctx)
    this_week = state.weekly[state.weekly["week_start"] == week]["hours"].sum() if not state.weekly.empty else 0.0
    st.metric(f"Total for {week_label(week)}", format_hours(round(float(this_week), 2)))
    workspace.workspace_grid(ctx, week, fields=("week_hours",), key="log_grid")
    workspace.action_bar(ctx, key="log_bar")


def render_history(ctx: AppContext) -> None:
    st.title(f"Spending history · {ctx.fy['label']}")
    st.caption("Approved hours, one line per project per week.")
    entries = spending.list_week_entries(ctx.conn, ctx.fy["id"])
    if not entries:
        st.info("No hours have been approved yet.")
        return
    projects = sorted({e["project_name"] for e in entries})
    chosen = st.multiselect("Projects", projects, key="spend_hist_projects")
    entries = [e for e in entries if not chosen or e["project_name"] in chosen]

    frame = pd.DataFrame([{
        "Week": week_label(e["week_start"]), "Project": e["project_name"], "Cost code": e["cost_code_name"],
        "Hours": e["hours"], "Note": e["notes"] or "", "Revisions": e["revisions"],
    } for e in entries])
    st.dataframe(frame, hide_index=True, width="stretch")
    st.caption(f"Total: **{format_hours(round(frame['Hours'].sum(), 2))}**")
    export_controls(frame, "weekly spending log", ctx.today)

    revised = [e for e in entries if e["revisions"] > 1]
    if revised:
        with st.expander("Corrections behind an entry"):
            entry = st.selectbox(
                "Entry", revised, key="spend_hist_entry",
                format_func=lambda e: f"{week_label(e['week_start'])} · {e['project_name']} · {format_hours(e['hours'])}",
            )
            history = spending.list_entry_history(ctx.conn, entry["person_id"], entry["project_id"], entry["week_start"])
            st.dataframe(
                [{"Recorded (UTC)": h["created_at"], "Hours": h["hours"], "Note": h["notes"] or ""} for h in history],
                hide_index=True, width="stretch",
                column_config={"Hours": st.column_config.NumberColumn("Hours", format="%+.2f")},
            )
