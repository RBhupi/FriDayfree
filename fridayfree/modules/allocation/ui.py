"""Allocation pages: projects (tag + pasted charge string), cost codes, and the amendment history."""
import pandas as pd
import streamlit as st

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.allocation.service import PROJECT_STATUSES
from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes import ui as workspace
from fridayfree.modules.shared_ui import AppContext, copy_button, export_controls, run_action, show_flashes
from fridayfree.utils.charge_string import parse_charge_string
from fridayfree.utils.dates import default_week, week_label
from fridayfree.utils.formatting import format_hours

EXAMPLE_STRING = "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis"


def _show_deciphered(charge_string: str) -> None:
    parsed = parse_charge_string(charge_string)
    if parsed.prj_code or parsed.pt_code:
        st.success(f"Deciphered: **{parsed.prj_code or '—'}** {parsed.prj_name} · "
                   f"**{parsed.pt_code or '—'}** {parsed.pt_name}", icon="🔎")
    else:
        st.warning("No PRJ/PT code found in that string. It will still be stored and copyable as-is.")


KIND_LABEL = {"fund": "allocation", "reserve": "reserved", "freeze": "frozen", "hours": "hours charged"}


# projects ----------------------------------------------------------------------------------------

def _add_project_form(ctx: AppContext) -> None:
    st.subheader("Add a project")
    st.caption("Give it your own tag and paste the cost code string from Dayforce. "
               "Several projects can share one string; each project has exactly one.")
    existing = {c["charge_string"]: c for c in allocation.list_cost_codes(ctx.conn, ctx.fy["id"])}
    tag = st.text_input("Project tag", placeholder="alpha_main", key="new_project_tag")
    choice = st.selectbox(
        "Cost code string", ["Paste a new string…", *existing], key="new_project_choice",
        format_func=lambda s: s if s not in existing else f"{existing[s]['name']}  ·  {s}",
    )
    charge_string = choice
    if choice not in existing:
        charge_string = st.text_input(
            "Paste the string", placeholder=EXAMPLE_STRING, key="new_project_string")
        if charge_string.strip():
            _show_deciphered(charge_string)
    if st.button("Add project", type="primary"):
        if run_action(lambda: allocation.add_project_from_string(ctx.conn, ctx.fy["id"], tag, charge_string),
                      f"{tag.strip()} added. Give it hours under Allocations → Funds (or in the Dashboard grid)."):
            for key in ("new_project_tag", "new_project_string"):
                st.session_state.pop(key, None)
            st.rerun()


def _project_row(ctx: AppContext, balance, project: dict) -> None:
    with st.container(border=True):
        name_col, numbers_col, copy_col = st.columns([4, 4, 2], vertical_alignment="center")
        name_col.markdown(f"**{balance.project_name}**  \n:gray[{balance.status}]")
        numbers_col.markdown(
            f"{format_hours(balance.allocated)} allocated · {format_hours(balance.spent)} spent · "
            f"**{format_hours(balance.available)} available**")
        with copy_col:
            copy_button(balance.charge_string, key=f"copy_project_{balance.project_id}")
        with st.expander("Rename, change status or delete"):
            name = st.text_input("Tag", value=project["name"], key=f"p_name_{project['id']}")
            status = st.selectbox("Status", PROJECT_STATUSES, index=PROJECT_STATUSES.index(project["status"]),
                                  key=f"p_status_{project['id']}")
            save_col, delete_col = st.columns(2)
            if save_col.button("Save", key=f"p_save_{project['id']}"):
                if run_action(lambda: allocation.update_project(ctx.conn, project["id"], name, status), "Project updated."):
                    st.rerun()
            deletable = allocation.can_delete_project(ctx.conn, project["id"])
            if delete_col.button("Delete", key=f"p_del_{project['id']}", disabled=not deletable,
                                 help=None if deletable else "Hours are recorded or planned here — set the status to cancelled instead."):
                if run_action(lambda: allocation.delete_project(ctx.conn, project["id"]), "Project deleted."):
                    st.rerun()


def render_projects(ctx: AppContext) -> None:
    st.title(f"Projects · {ctx.fy['label']}")
    show_flashes()
    _add_project_form(ctx)

    st.subheader("Your projects")
    show_cancelled = st.toggle("Show cancelled", key="show_cancelled")
    projects = {p["id"]: p for p in allocation.list_projects(ctx.conn, ctx.fy["id"], include_cancelled=show_cancelled)}
    balances = [b for b in allocation.list_balances(ctx.conn, ctx.fy["id"]) if b.project_id in projects]
    if not balances:
        st.info("No projects yet.")
        return
    st.caption("Hours shown here are approved figures. Change them under Allocations → Funds or in the Dashboard grid.")
    current_code = None
    for b in balances:
        if b.cost_code_id != current_code:
            current_code = b.cost_code_id
            st.markdown(f"#### {b.cost_code_name}")
            st.code(b.charge_string, language=None)
        _project_row(ctx, b, projects[b.project_id])


# funds -------------------------------------------------------------------------------------------

def render_funds(ctx: AppContext) -> None:
    st.title(f"Funds · {ctx.fy['label']}")
    show_flashes()
    st.markdown(
        "Type the **final number** you want and press **Approve**.\n"
        "- **Allocated** — hours the project has. New funds: raise it. Funds removed: lower it. "
        "To move hours, lower one project and raise another, then approve together.\n"
        "- **Reserved** — hours you hold back for something planned. Set back to 0 to use them.\n"
        "- **Frozen** — hours you may not use until unfrozen. Set back to 0 when lifted.")
    week = default_week(ctx.fy["start_date"], ctx.fy["end_date"], ctx.today)
    workspace.workspace_grid(ctx, week, fields=workspace.ALLOCATION_FIELDS, key="funds_grid")
    workspace.action_bar(ctx, key="funds_bar")


# cost codes --------------------------------------------------------------------------------------

def render_cost_codes(ctx: AppContext) -> None:
    st.title(f"Cost codes · {ctx.fy['label']}")
    show_flashes()
    with st.expander("Add a cost code", expanded=not allocation.list_cost_codes(ctx.conn, ctx.fy["id"])):
        st.caption("Paste the cost code string exactly as your timesheet system shows it.")
        new_string = st.text_input("Cost code string", placeholder=EXAMPLE_STRING, key="new_code_string")
        new_name = st.text_input("Display name (optional — deciphered from the string if left empty)", key="new_code_name")
        if new_string.strip():
            _show_deciphered(new_string)
        if st.button("Add cost code", type="primary"):
            if run_action(lambda: allocation.create_cost_code(ctx.conn, ctx.fy["id"], new_string, new_name), "Cost code added."):
                for key in ("new_code_string", "new_code_name"):
                    st.session_state.pop(key, None)
                st.rerun()

    codes = allocation.list_cost_codes(ctx.conn, ctx.fy["id"])
    for code in codes:
        with st.container(border=True):
            title_col, copy_col = st.columns([8, 2], vertical_alignment="center")
            title_col.markdown(f"**{code['name']}**  \n:gray[{code['prj_code'] or '—'} · {code['pt_code'] or '—'} · "
                               f"{code['project_count']} project(s)]")
            with copy_col:
                copy_button(code["charge_string"], key=f"copy_code_{code['id']}")
            st.code(code["charge_string"], language=None)
            if code["notes"]:
                st.caption(code["notes"])
            tag_col, add_col = st.columns([7, 3], vertical_alignment="bottom")
            tag = tag_col.text_input("Add a project to this cost code", placeholder="project tag", key=f"c_tag_{code['id']}")
            if add_col.button("Add project", key=f"c_add_{code['id']}", width="stretch"):
                if run_action(lambda: allocation.create_project(ctx.conn, code["id"], tag),
                              f"{tag.strip()} added. Give it hours under Allocations → Funds."):
                    st.session_state.pop(f"c_tag_{code['id']}", None)
                    st.rerun()
            with st.expander("Edit name / notes or delete"):
                name = st.text_input("Name", value=code["name"], key=f"c_name_{code['id']}")
                notes = st.text_area("Notes", value=code["notes"] or "", key=f"c_notes_{code['id']}")
                save_col, delete_col = st.columns(2)
                if save_col.button("Save", key=f"c_save_{code['id']}"):
                    if run_action(lambda: allocation.update_cost_code(ctx.conn, code["id"], name, notes), "Cost code updated."):
                        st.rerun()
                if delete_col.button("Delete", key=f"c_del_{code['id']}"):
                    if run_action(lambda: allocation.delete_cost_code(ctx.conn, code["id"]), "Cost code deleted."):
                        st.rerun()
    if codes:
        frame = pd.DataFrame([{"Name": c["name"], "PRJ": c["prj_code"], "PT": c["pt_code"],
                               "String": c["charge_string"], "Notes": c["notes"]} for c in codes])
        export_controls(frame, "cost codes", ctx.today)


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
    st.caption("Every approved change, exactly as recorded. Rows are only ever added: "
               "+ adds hours, − removes them. The Dashboard shows the resulting totals.")
    balances = allocation.list_balances(ctx.conn, ctx.fy["id"])
    codes = {b.cost_code_id: b.cost_code_name for b in balances}
    projects = {b.project_id: b.project_name for b in balances}
    code_col, project_col = st.columns(2)
    cost_code_id = code_col.selectbox("Cost code", [None, *codes], format_func=lambda c: codes.get(c, "All"), key="hist_code")
    project_id = project_col.selectbox("Project", [None, *projects], format_func=lambda p: projects.get(p, "All"), key="hist_project")

    rows = changes.list_amendments(ctx.conn, ctx.fy["id"], project_id=project_id, cost_code_id=cost_code_id)
    if not rows:
        st.info("Nothing has been approved yet.")
        return
    sets = {s["id"]: s for s in changes.list_change_sets(ctx.conn, ctx.fy["id"])}
    by_set = {}
    for r in rows:
        by_set.setdefault(r["change_set_id"], []).append(r)
    for change_set_id, members in by_set.items():
        info = sets.get(change_set_id, {})
        title = f"#{change_set_id} · {info.get('approved_at', '')} · {len(members)} amendment(s)"
        if info.get("note"):
            title += f" · {info['note']}"
        with st.expander(title):
            frame = _amendment_frame(members).drop(columns=["Change #"])
            st.dataframe(frame, hide_index=True, width="stretch",
                         column_config={"Hours": st.column_config.NumberColumn("Hours", format="%+.2f")})
    export_controls(_amendment_frame(rows), "audit log", ctx.today)
