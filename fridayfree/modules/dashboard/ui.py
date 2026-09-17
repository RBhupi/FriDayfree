"""Dashboard page: final numbers only — never a list of amendments."""
import pandas as pd
import streamlit as st

from fridayfree.modules.changes import ui as plan_ui
from fridayfree.modules.spending import ui as spending_ui
from fridayfree.modules.dashboard import charts
from fridayfree.modules.dashboard import service as dash
from fridayfree.modules.shared_ui import AppContext, copy_button, export_controls, show_flashes
from fridayfree.utils.formatting import RISK_DOT, RISK_LABEL, format_dollar, format_hours, risk_color, to_dollars


def _charge_row(b, key: str, note: str) -> None:
    color = risk_color(b.pct_remaining, b.overdrawn)
    name_col, hours_col, copy_col = st.columns([5, 3, 2], vertical_alignment="center")
    name_col.markdown(f"{RISK_DOT[color]} **{b.project_name}**  \n:gray[{b.cost_code_name}]")
    hours_col.markdown(note)
    with copy_col:
        copy_button(b.charge_string, key=key)


VIEWS = ("All panels", "Total", "Cost codes", "Projects")


def _total_panel(ctx: AppContext, state) -> None:
    total = dash.totals(state)
    st.subheader("Total")
    cols = st.columns(5)
    for col, label, hours, priced in zip(
        cols, ("Available", "Allocated", "Spent", "Reserved", "Frozen"),
        (total.available, total.allocated, total.spent, total.reserved, total.frozen), (True, True, True, False, False),
    ):
        col.metric(label, format_hours(hours))
        if priced and ctx.rate is not None:
            col.caption(format_dollar(to_dollars(hours, ctx.rate)))


def _cost_code_panel(state, key: str) -> None:
    st.subheader("By cost code")
    codes = dash.cost_code_summary(state)
    if not codes:
        st.info("No cost codes yet. Add one under Allocations → Cost codes.")
    for code in codes:
        color = risk_color(code.pct_remaining, code.overdrawn)
        with st.container(border=True):
            name_col, copy_col = st.columns([7, 3], vertical_alignment="center")
            name_col.markdown(
                f"{RISK_DOT[color]} **{code.cost_code_name}**  \n"
                f"**{format_hours(code.available)}** available of {format_hours(code.allocated)} · {RISK_LABEL[color]}")
            with copy_col:
                copy_button(code.charge_string, key=f"{key}_copy_code_{code.cost_code_id}")
            used = min(max(code.spent / code.allocated, 0.0), 1.0) if code.allocated > 0 else 0.0
            held = [f"{format_hours(v)} {word}" for v, word in ((code.reserved, "reserved"), (code.frozen, "frozen")) if v]
            st.progress(used, text=f"{format_hours(code.spent)} spent" + (" · " + " · ".join(held) if held else ""))


def _project_panel(state, key: str) -> None:
    st.subheader("By project — what can I charge this week")
    buckets = dash.chargeable_now(state)
    if not buckets["chargeable"]:
        st.info("Nothing is available to charge right now.")
    for b in buckets["chargeable"]:
        color = risk_color(b.pct_remaining, b.overdrawn)
        _charge_row(b, f"{key}_copy_charge_{b.project_id}", f"**{format_hours(b.available)}** available · {RISK_LABEL[color]}")
    if buckets["held"]:
        st.markdown("**Held — do not charge these hours**")
        for b in buckets["held"]:
            held = [f"{format_hours(v)} {word}" for v, word in ((b.reserved, "reserved"), (b.frozen, "frozen")) if v]
            _charge_row(b, f"{key}_copy_held_{b.project_id}", " · ".join(held))
    for b in buckets["overdrawn"]:
        st.markdown(f"🔴 **{b.project_name}** is overdrawn by **{format_hours(-b.balance)}** — do not charge.")


def _panels(ctx: AppContext, state) -> None:
    view = st.segmented_control("Show", VIEWS, default=VIEWS[0], key="dash_view") or VIEWS[0]
    if view in ("All panels", "Total"):
        _total_panel(ctx, state)
    if view == "All panels":
        left, right = st.columns(2, gap="large")
        with left:
            _cost_code_panel(state, "all")
        with right:
            _project_panel(state, "all")
    elif view == "Cost codes":
        _cost_code_panel(state, "only")
    elif view == "Projects":
        _project_panel(state, "only")


def _summary_frame(rows, rate, label: str) -> pd.DataFrame:
    records = []
    for r in rows:
        color = risk_color(r.pct_remaining, r.overdrawn)
        record = {
            label: getattr(r, "project_name", None) or r.cost_code_name,
            "Allocated": r.allocated, "Spent": r.spent, "Reserved": r.reserved, "Frozen": r.frozen,
            "Available": r.available, "Status": f"{RISK_DOT[color]} {RISK_LABEL[color]}",
        }
        if rate is not None:
            record["Spent $"] = to_dollars(r.spent, rate)
            record["Available $"] = to_dollars(r.available, rate)
        records.append(record)
    return pd.DataFrame(records)


def _money_config(frame: pd.DataFrame) -> dict:
    config = {c: st.column_config.NumberColumn(c, format="dollar") for c in frame.columns if c.endswith("$")}
    for c in ("Allocated", "Spent", "Reserved", "Frozen", "Available"):
        config[c] = st.column_config.NumberColumn(c, format="%.2f")
    return config


def _summaries(ctx: AppContext, state) -> None:
    st.subheader("Tables")
    codes = dash.cost_code_summary(state)
    if not codes:
        st.info("No cost codes yet. Add a project under Allocations → Projects.")
        return
    frame = _summary_frame(codes, ctx.rate, "Cost code")
    st.dataframe(frame, hide_index=True, width="stretch", column_config=_money_config(frame))
    export_controls(frame, "cost code summary", ctx.today)

    all_projects = []
    for code in codes:
        members = [b for b in state.balances if b.cost_code_id == code.cost_code_id]
        all_projects += members
        with st.expander(f"{code.cost_code_name} — {len(members)} project(s) · {format_hours(code.available)} available"):
            st.code(code.charge_string, language=None)
            project_frame = _summary_frame(members, ctx.rate, "Project")
            st.dataframe(project_frame, hide_index=True, width="stretch", column_config=_money_config(project_frame))
    breakdown = _summary_frame(all_projects, ctx.rate, "Project")
    breakdown.insert(1, "Cost code", [b.cost_code_name for b in all_projects])
    export_controls(breakdown, "project breakdown", ctx.today)


def _charts(ctx: AppContext, state) -> None:
    st.subheader("Trends")
    if state.weekly.empty:
        st.info("Charts appear once hours are logged.")
        return
    projection = dash.project_end_of_fy(state, ctx.fy, ctx.today)
    left, right = st.columns(2)
    with left:
        st.markdown("**Weekly burn**")
        st.plotly_chart(charts.burn_chart(dash.weekly_burn(state, ctx.fy, ctx.today)), key="chart_burn")
    with right:
        st.markdown("**Available by project**")
        st.plotly_chart(charts.remaining_chart(state.balances), key="chart_remaining")

    st.markdown("**Cumulative spend vs allocation**")
    verdict = (
        f"At the recent pace of {format_hours(projection.avg_weekly)}/week you are on track to use "
        f"**{format_hours(projection.projected_total)}** of **{format_hours(projection.total_allocated)}** "
        f"by the end of {ctx.fy['label']}"
    )
    gap = round(projection.total_allocated - projection.projected_total, 2)
    verdict += f" — {format_hours(gap)} would be left." if gap >= 0 else f" — **{format_hours(-gap)} over**."
    st.markdown(verdict)
    st.plotly_chart(
        charts.cumulative_chart(dash.cumulative_vs_allocation(state, ctx.fy, ctx.today), projection), key="chart_cumulative"
    )


def render(ctx: AppContext) -> None:
    st.title(f"Dashboard · {ctx.fy['label']}")
    show_flashes()

    planned = plan_ui.planned_items(ctx)
    approved_only = False
    if planned:
        info_col, toggle_col = st.columns([3, 1], vertical_alignment="center")
        info_col.info(f"These numbers include **{len(planned)} planned hour entr"
                      f"{'y' if len(planned) == 1 else 'ies'}** that are not approved yet.", icon=":material/edit:")
        approved_only = toggle_col.toggle("Show approved only", key="approved_only")
    state = plan_ui.current_state(ctx, approved_only=approved_only)

    for alert in dash.overdraft_alerts(state):
        st.error(alert, icon="🚨")

    if state.balances and dash.totals(state).allocated == 0:
        st.info("Your projects have no hours yet. Go to **Funds**, pick a project, press **Allocate**.", icon="👉")

    _panels(ctx, state)

    st.subheader("This week")
    week = plan_ui.week_picker(ctx, key="dash_week")
    spending_ui.week_form(ctx, week, key="dash_week")

    _summaries(ctx, state)
    _charts(ctx, state)
