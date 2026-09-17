"""Funds, cost codes, projects and history.

A cost code is a bucket of funds; projects draw from it. Every fund action happens on a project and is
recorded the moment you press the button.
"""
import pandas as pd
import streamlit as st

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.allocation.service import PROJECT_STATUSES
from fridayfree.modules.changes import service as changes
from fridayfree.modules.shared_ui import (AppContext, apply_queued_values, copy_button, export_controls,
                                          flash, queue_widget_values, run_action, show_flashes)
from fridayfree.utils.dates import week_label
from fridayfree.utils.formatting import RISK_DOT, format_hours, risk_color

EXAMPLE_STRING = "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis"
KIND_LABEL = {"fund": "allocation", "reserve": "reserved", "freeze": "frozen", "hours": "hours charged"}
ACTION_HELP = {
    "allocate": "Give the project hours from this cost code.",
    "deallocate": "Take hours back off the project.",
    "reserve": "Hold hours back for something planned. They stop being available until you unreserve them.",
    "unreserve": "Release hours you were holding, so they can be charged again.",
    "freeze": "Hours you may not use, e.g. pending a sponsor decision.",
    "unfreeze": "Lift the freeze so the hours can be used again.",
}


# funds -------------------------------------------------------------------------------------------

def _project_choice(balances) -> dict:
    return {b.project_id: f"{b.project_name}  ·  {b.cost_code_name}" for b in balances}


def _numbers_line(b) -> str:
    return (f"**{format_hours(b.available)} available**  ·  {b.allocated:g} allocated · {b.spent:g} spent · "
            f"{b.reserved:g} reserved · {b.frozen:g} frozen")


def _queue(**fields) -> None:
    """Ask the form to show these values (applied on the next run — see queue_widget_values)."""
    queue_widget_values("fund_queue", **fields)


def _apply_queue() -> None:
    nonce = st.session_state.get("fund_nonce", 0)
    apply_queued_values("fund_queue",
                        key_for=lambda name: f"fund_hours_{nonce}" if name == "hours" else f"fund_{name}")


def _action_form(ctx: AppContext, balances) -> None:
    choices = _project_choice(balances)
    project_id = st.selectbox("Project", list(choices), format_func=choices.get, key="fund_project")
    balance = next(b for b in balances if b.project_id == project_id)
    st.markdown(_numbers_line(balance))
    if balance.status != "active":
        st.caption(f"This project is {balance.status}. You can still take hours back off it.")

    action = st.radio("Action", list(changes.FUND_ACTIONS), horizontal=True, key="fund_action",
                      format_func=lambda a: changes.FUND_ACTIONS[a][2])
    st.caption(ACTION_HELP[action])

    ceiling = changes.max_hours(balance, action)
    hours_col, all_col = st.columns([3, 1], vertical_alignment="bottom")
    hours = hours_col.number_input(
        "Hours", min_value=0.0, step=0.25, key=f"fund_hours_{st.session_state.get('fund_nonce', 0)}",
        help=None if ceiling == float("inf") else f"At most {ceiling:g} h.",
    )
    if ceiling != float("inf") and ceiling > 0:
        if all_col.button(f"All {ceiling:g} h", width="stretch"):
            _queue(hours=ceiling)
    note = st.text_input("Note (optional)", key=f"fund_note_{st.session_state.get('fund_nonce', 0)}",
                         placeholder="why the funds changed")

    if hours > 0:
        after, errors, warnings = changes.preview_fund_action(ctx.conn, project_id, action, hours)
        for error in errors:
            st.error(error)
        for warning in warnings:
            st.warning(warning, icon="⚠️")
        sentence = changes.action_sentence(action, hours, balance.project_name)
        if st.button(sentence, type="primary", disabled=bool(errors)):
            def apply():
                result = changes.record_fund_action(ctx.conn, ctx.fy["id"], project_id, action, hours, note)
                flash(f"{result.sentence} — done. {balance.project_name} now has "
                      f"{format_hours(result.after.available)} available.")
            if run_action(apply):
                st.session_state["fund_nonce"] = st.session_state.get("fund_nonce", 0) + 1
                st.rerun()
        if not errors:
            st.caption(f"After this: **{format_hours(after.available)} available** "
                       f"({after.allocated:g} allocated · {after.reserved:g} reserved · {after.frozen:g} frozen)")
    else:
        st.button(changes.FUND_ACTIONS[action][2], disabled=True, help="Enter the hours first")


def _recent_actions(ctx: AppContext) -> None:
    recent = changes.recent_fund_actions(ctx.conn, ctx.fy["id"])
    if not recent:
        return
    st.subheader("Last few fund changes")
    for row in recent:
        with st.container(border=True):
            text_col, undo_col = st.columns([8, 2], vertical_alignment="center")
            note = f" · {row['reason']}" if row["reason"] else ""
            text_col.markdown(f"{row['sentence']}  \n:gray[{row['created_at']}{note}]")
            if undo_col.button("Undo", key=f"undo_{row['id']}", width="stretch",
                               help="Fills in the opposite action above. The original entry is kept."):
                _queue(project=row["project_id"], action=row["undo_action"], hours=abs(row["hours"]))


def render_funds(ctx: AppContext) -> None:
    st.title(f"Funds · {ctx.fy['label']}")
    show_flashes()
    balances = allocation.list_balances(ctx.conn, ctx.fy["id"])
    if not balances:
        st.info("Add a cost code and a project first — Funds → Cost codes.")
        return

    _apply_queue()          # before any widget on this page is created

    st.caption("Pick a project, pick what you want to do, press the button. It is recorded straight away; "
               "to undo something, do the opposite action.")
    _action_form(ctx, balances)

    st.subheader("Your projects")
    current_code = None
    for b in balances:
        if b.cost_code_id != current_code:
            current_code = b.cost_code_id
            st.markdown(f"**{b.cost_code_name}**")
        with st.container(border=True):
            name_col, numbers_col, adjust_col, copy_col = st.columns([3, 5, 1.2, 1.8], vertical_alignment="center")
            colour = risk_color(b.pct_remaining, b.overdrawn)
            name_col.markdown(f"{RISK_DOT[colour]} **{b.project_name}**"
                              + (f"  \n:gray[{b.status}]" if b.status != "active" else ""))
            numbers_col.markdown(_numbers_line(b))
            if adjust_col.button("Adjust", key=f"adjust_{b.project_id}", width="stretch"):
                _queue(project=b.project_id)
            with copy_col:
                copy_button(b.charge_string, key=f"copy_fund_{b.project_id}")

    _recent_actions(ctx)


# cost codes --------------------------------------------------------------------------------------

def _expiry_note(expires_on, today) -> str:
    if not expires_on:
        return ""
    days = (expires_on - today).days
    if days < 0:
        return f"  \n:red[expired {-days} day(s) ago]"
    if days <= 30:
        return f"  \n:orange[expires in {days} day(s)]"
    return f"  \n:gray[expires {expires_on:%b %d %Y}]"


def _cost_code_fields(ctx: AppContext, prefix: str, code=None) -> dict:
    """The one form, used for both adding and editing. Every field is asked for."""
    code = code or {}
    name = st.text_input("Name", value=code.get("name", ""), key=f"{prefix}_name",
                         placeholder="what you call this pot of money")
    charge_string = st.text_area(
        "Cost code string (copied into your timesheet)", value=code.get("charge_string", ""),
        key=f"{prefix}_string", placeholder=EXAMPLE_STRING, height=68)
    suggestion = allocation.suggest_codes(charge_string)
    prj_col, pt_col = st.columns(2)
    prj_code = prj_col.text_input("PRJ code", value=code.get("prj_code") or suggestion["prj_code"],
                                  key=f"{prefix}_prj", placeholder="PRJ…")
    pt_code = pt_col.text_input("PT code", value=code.get("pt_code") or suggestion["pt_code"],
                                key=f"{prefix}_pt", placeholder="PT…")
    if suggestion["prj_code"] and not code:
        st.caption("PRJ and PT were read from the string — correct them if they are wrong.")
    expires_col, _ = st.columns(2)
    expires_on = expires_col.date_input("Expires on (optional)", value=code.get("expires_on"),
                                        key=f"{prefix}_expires", format="YYYY-MM-DD")
    notes = st.text_area("Notes (optional)", value=code.get("notes") or "", key=f"{prefix}_notes", height=68)
    return {"name": name, "charge_string": charge_string, "prj_code": prj_code, "pt_code": pt_code,
            "expires_on": expires_on, "notes": notes}


def render_cost_codes(ctx: AppContext) -> None:
    st.title(f"Cost codes · {ctx.fy['label']}")
    show_flashes()
    st.caption("A cost code is a pot of funds. Add it here, then add the projects that draw from it; "
               "hours are given to projects on the Funds page.")
    codes = allocation.list_cost_codes(ctx.conn, ctx.fy["id"])

    with st.expander("Add a cost code", expanded=not codes):
        fields = _cost_code_fields(ctx, "new_code")
        if st.button("Add cost code", type="primary"):
            if run_action(lambda: allocation.create_cost_code(ctx.conn, ctx.fy["id"], **fields),
                          f"{fields['name'].strip()} added. Now add the projects that use it."):
                for key in list(st.session_state):
                    if key.startswith("new_code_"):
                        del st.session_state[key]
                st.rerun()

    for code in codes:
        with st.container(border=True):
            title_col, copy_col = st.columns([8, 2], vertical_alignment="center")
            title_col.markdown(f"**{code['name']}**  \n:gray[{code['prj_code'] or '—'} · {code['pt_code'] or '—'} · "
                               f"{code['project_count']} project(s)]" + _expiry_note(code["expires_on"], ctx.today))
            with copy_col:
                copy_button(code["charge_string"], key=f"copy_code_{code['id']}")
            st.code(code["charge_string"], language=None)
            if code["notes"]:
                st.caption(code["notes"])

            tag_col, add_col = st.columns([7, 3], vertical_alignment="bottom")
            tag = tag_col.text_input("Add a project that uses this cost code", placeholder="project tag",
                                     key=f"c_tag_{code['id']}")
            if add_col.button("Add project", key=f"c_add_{code['id']}", width="stretch"):
                if run_action(lambda: allocation.create_project(ctx.conn, code["id"], tag),
                              f"{tag.strip()} added. Give it hours on the Funds page."):
                    st.session_state.pop(f"c_tag_{code['id']}", None)
                    st.rerun()

            with st.expander("Edit or delete this cost code"):
                fields = _cost_code_fields(ctx, f"edit_{code['id']}", code)
                save_col, delete_col = st.columns(2)
                if save_col.button("Save", key=f"c_save_{code['id']}"):
                    if run_action(lambda: allocation.update_cost_code(ctx.conn, code["id"], **fields),
                                  "Cost code updated."):
                        st.rerun()
                if delete_col.button("Delete", key=f"c_del_{code['id']}"):
                    if run_action(lambda: allocation.delete_cost_code(ctx.conn, code["id"]), "Cost code deleted."):
                        st.rerun()

    if codes:
        frame = pd.DataFrame([{"Name": c["name"], "PRJ": c["prj_code"], "PT": c["pt_code"],
                               "Projects": c["project_count"], "Expires": c["expires_on"],
                               "String": c["charge_string"], "Notes": c["notes"]} for c in codes])
        export_controls(frame, "cost codes", ctx.today)


# projects ----------------------------------------------------------------------------------------

def render_projects(ctx: AppContext) -> None:
    st.title(f"Projects · {ctx.fy['label']}")
    show_flashes()
    codes = {c["id"]: c["name"] for c in allocation.list_cost_codes(ctx.conn, ctx.fy["id"])}
    if not codes:
        st.info("Add a cost code first — a project always draws from one. Funds → Cost codes.")
        return

    with st.expander("Add a project", expanded=not allocation.list_projects(ctx.conn, ctx.fy["id"])):
        tag = st.text_input("Project tag", placeholder="alpha_main", key="new_project_tag")
        cost_code_id = st.selectbox("Draws from", list(codes), format_func=codes.get, key="new_project_code")
        if st.button("Add project", type="primary"):
            if run_action(lambda: allocation.create_project(ctx.conn, cost_code_id, tag),
                          f"{tag.strip()} added. Give it hours on the Funds page."):
                st.session_state.pop("new_project_tag", None)
                st.rerun()

    show_cancelled = st.toggle("Show cancelled", key="show_cancelled")
    projects = {p["id"]: p for p in allocation.list_projects(ctx.conn, ctx.fy["id"], include_cancelled=show_cancelled)}
    balances = [b for b in allocation.list_balances(ctx.conn, ctx.fy["id"]) if b.project_id in projects]
    if not balances:
        st.info("No projects yet.")
        return
    st.caption("Hours are changed on the Funds page — this page is for names, status and clean-up.")

    current_code = None
    for b in balances:
        if b.cost_code_id != current_code:
            current_code = b.cost_code_id
            st.markdown(f"#### {b.cost_code_name}")
        project = projects[b.project_id]
        with st.container(border=True):
            name_col, numbers_col, copy_col = st.columns([4, 4, 2], vertical_alignment="center")
            name_col.markdown(f"**{b.project_name}**  \n:gray[{b.status}]")
            numbers_col.markdown(_numbers_line(b))
            with copy_col:
                copy_button(b.charge_string, key=f"copy_project_{b.project_id}")
            with st.expander("Rename, change status or delete"):
                name = st.text_input("Tag", value=project["name"], key=f"p_name_{project['id']}")
                status = st.selectbox("Status", PROJECT_STATUSES, index=PROJECT_STATUSES.index(project["status"]),
                                      key=f"p_status_{project['id']}")
                save_col, delete_col = st.columns(2)
                if save_col.button("Save", key=f"p_save_{project['id']}"):
                    if run_action(lambda: allocation.update_project(ctx.conn, project["id"], name, status),
                                  "Project updated."):
                        st.rerun()
                deletable = allocation.can_delete_project(ctx.conn, project["id"])
                if delete_col.button("Delete", key=f"p_del_{project['id']}", disabled=not deletable,
                                     help=None if deletable else "Hours are recorded here — set it to cancelled instead."):
                    if run_action(lambda: allocation.delete_project(ctx.conn, project["id"]), "Project deleted."):
                        st.rerun()


# history -----------------------------------------------------------------------------------------

def _amendment_frame(rows) -> pd.DataFrame:
    return pd.DataFrame([{
        "Change #": r["change_set_id"], "Recorded (UTC)": r["created_at"], "Project": r["project_name"],
        "Cost code": r["cost_code_name"], "What": KIND_LABEL[r["kind"]],
        "Week": week_label(r["week_start"]) if r["week_start"] else "",
        "Hours": r["hours"], "Note": r["note"] or "",
    } for r in rows])


def render_history(ctx: AppContext) -> None:
    st.title(f"History · {ctx.fy['label']}")
    st.caption("Everything that was recorded, exactly as it happened. Entries are only ever added: "
               "+ puts hours in, − takes them out. The other pages show the resulting totals.")
    balances = allocation.list_balances(ctx.conn, ctx.fy["id"])
    codes = {b.cost_code_id: b.cost_code_name for b in balances}
    projects = {b.project_id: b.project_name for b in balances}
    code_col, project_col = st.columns(2)
    cost_code_id = code_col.selectbox("Cost code", [None, *codes], format_func=lambda c: codes.get(c, "All"), key="hist_code")
    project_id = project_col.selectbox("Project", [None, *projects], format_func=lambda p: projects.get(p, "All"), key="hist_project")

    rows = changes.list_amendments(ctx.conn, ctx.fy["id"], project_id=project_id, cost_code_id=cost_code_id)
    if not rows:
        st.info("Nothing has been recorded yet.")
        return
    sets = {s["id"]: s for s in changes.list_change_sets(ctx.conn, ctx.fy["id"])}
    by_set = {}
    for r in rows:
        by_set.setdefault(r["change_set_id"], []).append(r)
    for change_set_id, members in by_set.items():
        info = sets.get(change_set_id, {})
        title = f"#{change_set_id} · {info.get('approved_at', '')} · {len(members)} entr(y/ies)"
        if info.get("note"):
            title += f" · {info['note']}"
        with st.expander(title):
            frame = _amendment_frame(members).drop(columns=["Change #"])
            st.dataframe(frame, hide_index=True, width="stretch",
                         column_config={"Hours": st.column_config.NumberColumn("Hours", format="%+.2f")})
    export_controls(_amendment_frame(rows), "history", ctx.today)
