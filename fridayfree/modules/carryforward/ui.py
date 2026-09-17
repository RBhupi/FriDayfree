"""Carry forward: rebuild this year's cost codes and projects in the next year with what is left."""
import pandas as pd
import streamlit as st

from fridayfree.modules.carryforward import service as carry
from fridayfree.modules.shared_ui import AppContext, export_controls, flash, run_action, show_flashes
from fridayfree.utils.formatting import format_hours


def _preview_frame(plan) -> pd.DataFrame:
    return pd.DataFrame([{
        "Cost code": line.cost_code_name, "Project": line.project_name, "Left": line.left,
        "Carries": line.carries, "Reserved": line.reserved, "Frozen": line.frozen,
        "Already in the new year": line.already_there or None,
        "Note": line.left_behind or "",
    } for line in plan.lines])


def render_carry_forward(ctx: AppContext) -> None:
    st.title(f"Carry forward · {ctx.fy['label']}")
    show_flashes()
    st.caption("At the end of the year this rebuilds every cost code and project in the new year and gives each "
               "project the hours it had left. Nothing in the old year is changed. Tasks stay where they are.")

    plan = carry.plan(ctx.conn, ctx.fy["id"], ctx.today)
    carried = carry.already_carried(ctx.conn, ctx.fy["id"], plan.target_fy_id)
    if carried:
        st.success(f"{ctx.fy['label']} was already carried forward into **{carried['label']}**.", icon="✅")
        return
    for blocker in plan.blockers:
        st.info(blocker, icon="⏳")
    if not plan.lines:
        st.info("There are no projects in this year to carry.")
        return

    st.subheader(f"{ctx.fy['label']} → {plan.target_label or 'the new year'}")
    frame = _preview_frame(plan)
    st.dataframe(frame, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(c, format="%.2f")
                                for c in ("Left", "Carries", "Reserved", "Frozen", "Already in the new year")})
    st.markdown(f"**Total carried: {format_hours(plan.total_carried)}**")
    for warning in plan.warnings:
        st.warning(warning, icon="⚠️")
    export_controls(frame, "carry forward", ctx.today)

    if plan.target_fy_id is not None:
        st.caption(f"{plan.target_label} already exists, so everything is added to it.")
        label, start, end = plan.target_label, plan.target_start, plan.target_end
    else:
        st.markdown("**The new fiscal year**")
        label_col, start_col, end_col = st.columns(3)
        label = label_col.text_input("Label", value=plan.target_label, key="carry_label")
        start = start_col.date_input("Starts", value=plan.target_start, key="carry_start")
        end = end_col.date_input("Ends", value=plan.target_end, key="carry_end")

    if st.button(f"Carry forward to {label or 'the new year'}", type="primary", disabled=bool(plan.blockers)):
        def run():
            result = carry.carry_forward(ctx.conn, ctx.fy["id"], ctx.today, plan.target_fy_id, label, start, end)
            flash(f"Carried {format_hours(result.hours_carried)} into {result.target_label}: "
                  f"{result.cost_codes} cost code(s) and {result.projects} project(s) created.")
            st.session_state["switch_to_fy"] = result.target_label   # applied on the next run
        if run_action(run):
            st.rerun()
