"""This week: one hours box per project, saved as a plan and approved when the week is settled."""
import pandas as pd
import streamlit as st

from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes import ui as plan_ui
from fridayfree.modules.changes.service import WorkItem
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.shared_ui import AppContext, copy_button, export_controls, flash, show_flashes
from fridayfree.modules.spending import service as spending
from fridayfree.utils.dates import week_label
from fridayfree.utils.formatting import RISK_DOT, format_hours, risk_color


def week_form(ctx: AppContext, week, key: str = "week") -> None:
    """The heart of the weekly routine: type the hours you charged, save the plan, approve the week."""
    fy_id = ctx.fy["id"]
    if ctx.person is None:
        st.info("Add yourself under Settings → Person before logging hours.")
        return
    person_id = ctx.person["id"]

    saved = plan_ui.planned_items(ctx)
    values = changes.week_values(ctx.conn, fy_id, saved, week, person_id)
    state = changes.load_state(ctx.conn, fy_id, saved)
    balances = [b for b in state.balances if b.status == "active"]
    if not balances:
        st.info("No active projects yet. Add one under Funds → Cost codes.")
        return

    chargeable = [b for b in balances if b.available > 0 or values[b.project_id]["hours"]]
    held = [b for b in balances if b not in chargeable]
    nonce = st.session_state.get(f"{key}_nonce", 0)

    with st.form(f"{key}_form_{fy_id}_{week.isoformat()}_{nonce}"):
        st.markdown(f"**{week_label(week)}**")
        for b in chargeable:
            row = values[b.project_id]
            name_col, avail_col, copy_col, hours_col = st.columns([3, 2.4, 1.6, 1.6], vertical_alignment="center")
            colour = risk_color(b.pct_remaining, b.overdrawn)
            name_col.markdown(f"{RISK_DOT[colour]} **{b.project_name}**  \n:gray[{b.cost_code_name}]")
            avail_col.markdown(f"{format_hours(b.available)} available" + ("  \n:orange[planned]" if row["planned"] else ""))
            with copy_col:
                copy_button(b.charge_string, key=f"{key}_copy_{b.project_id}_{week}", label="Copy code")
            hours_col.number_input(
                f"Hours · {b.project_name}", min_value=0.0, step=0.25, value=float(row["hours"]),
                key=f"{key}_hours_{b.project_id}_{week}_{nonce}", label_visibility="collapsed",
            )
        note = st.text_input("Note for this week (optional)", value=changes.get_saved_note(ctx.conn, fy_id) or "",
                             key=f"{key}_note_{nonce}")
        save_col, approve_col, _ = st.columns([1, 1, 3])
        save = save_col.form_submit_button("Save plan", width="stretch")
        approve = approve_col.form_submit_button("Approve week", type="primary", width="stretch")

    if held:
        st.caption("Held or empty — not chargeable this week: " + " · ".join(
            f"{b.project_name} ({format_hours(b.held)} held)" if b.held else f"{b.project_name} (0 h)" for b in held))

    if save or approve:
        items = []
        for b in chargeable:
            hours = float(st.session_state[f"{key}_hours_{b.project_id}_{week}_{nonce}"])
            if not hours and not values[b.project_id]["hours"]:
                continue        # a project you never touched this week: leave it out entirely
            items.append(WorkItem(b.project_id, "week_hours", hours, week, person_id,
                                  reason=note or None if hours else None))
        try:
            kept = changes.save_items(ctx.conn, fy_id, items, note=note)
            if approve:
                result = changes.approve(ctx.conn, fy_id)
                flash(f"Week approved — {result.rows_written} entr{'y' if result.rows_written == 1 else 'ies'} recorded.")
                for warning in result.warnings:
                    flash("⚠️ " + warning)
            else:
                flash(f"Plan saved — {kept} entr{'y' if kept == 1 else 'ies'} waiting to be approved."
                      if kept else "Nothing left to approve.")
        except ValidationError as exc:
            st.error(str(exc))
        else:
            st.session_state[f"{key}_nonce"] = nonce + 1
            st.rerun()

    planned_total = sum(values[b.project_id]["hours"] for b in chargeable)
    total_col, discard_col = st.columns([3, 1], vertical_alignment="center")
    total_col.markdown(f"**Week total: {format_hours(round(planned_total, 2))}**")
    if changes.pending_count(ctx.conn, fy_id):
        with discard_col.popover("Discard plan", width="stretch"):
            st.write("Forget the hours you have planned? Approved weeks are not affected.")
            if st.button("Yes, discard", key=f"{key}_discard"):
                changes.discard(ctx.conn, fy_id)
                st.session_state[f"{key}_nonce"] = nonce + 1
                flash("Plan discarded.")
                st.rerun()


def render_week(ctx: AppContext) -> None:
    st.title(f"This week · {ctx.fy['label']}")
    show_flashes()
    st.caption("Type the hours you charged, press **Save plan** during the week, and **Approve week** when it is "
               "settled. Use **Copy code** to paste the cost code into your timesheet.")
    week = plan_ui.week_picker(ctx, key="week_page")
    week_form(ctx, week, key="week_page")


def render_history(ctx: AppContext) -> None:
    st.title(f"Weekly hours · {ctx.fy['label']}")
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
    export_controls(frame, "weekly hours", ctx.today)

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
