"""The workspace: an editable grid of FINAL numbers plus the Save / Approve / Discard bar.

Three layers of state:
  approved  - in the ledgers
  saved     - intentions persisted in <database>.intentions.json (survive restarts, never in the database)
  working   - unsaved edits, kept in st.session_state so they survive page switches
The grid always shows approved + saved + working.
"""
from datetime import date

import pandas as pd
import streamlit as st

from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes.service import EPSILON, WorkItem
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.shared_ui import AppContext, flash
from fridayfree.utils.dates import default_week, pickable_weeks, week_label
from fridayfree.utils.formatting import RISK_DOT, RISK_LABEL, risk_color

ALLOCATION_FIELDS = ("allocated", "reserved", "frozen")
COLUMN_LABEL = {"allocated": "Allocated", "reserved": "Reserved", "frozen": "Frozen"}
FIELD_WORD = {"allocated": "allocated", "reserved": "reserved", "frozen": "frozen", "week_hours": "hours"}


# working-state store -----------------------------------------------------------------------------

def _store(fy_id: int) -> dict:
    return st.session_state.setdefault("working_items", {}).setdefault(fy_id, {})


def working_items(fy_id: int) -> list[WorkItem]:
    return list(_store(fy_id).values())


def _reset_editors(fy_id: int) -> None:
    st.session_state["working_items"][fy_id] = {}
    st.session_state["grid_nonce"] = st.session_state.get("grid_nonce", 0) + 1


def current_items(ctx: AppContext) -> list[WorkItem]:
    """Saved intentions with the unsaved edits on top."""
    return changes.merge_items(changes.get_saved_items(ctx.conn, ctx.fy["id"]), working_items(ctx.fy["id"]))


def current_state(ctx: AppContext, approved_only: bool = False):
    return changes.load_state(ctx.conn, ctx.fy["id"], () if approved_only else current_items(ctx))


# grid --------------------------------------------------------------------------------------------

def _hours_label(week: date) -> str:
    return f"Hours · wk of {week:%b} {week.day}"


def _pending_text(project_id: int, week: date, pending_keys) -> str:
    words = [FIELD_WORD[f] for (p, f, w) in sorted(pending_keys, key=str) if p == project_id and w in (None, week)]
    other_weeks = any(p == project_id and w not in (None, week) for (p, _, w) in pending_keys)
    if other_weeks:
        words.append("hours (other weeks)")
    return "✎ " + ", ".join(words) if words else ""


def _derive_working(edited: pd.DataFrame, project_ids, fields, saved_values, week, person_id, hours_col) -> dict:
    """Cells that differ from approved + saved become WorkItems."""
    derived = {}
    for row, project_id in zip(edited.to_dict("records"), project_ids):
        base = saved_values[project_id]
        note = (row.get("Note") or "").strip()
        new_note = note if note != base["note"] else None
        for name in fields:
            column = hours_col if name == "week_hours" else COLUMN_LABEL[name]
            value = row[column]
            value = 0.0 if value is None or pd.isna(value) else round(float(value), 2)
            changed = abs(value - base[name]) >= EPSILON
            if name == "week_hours":
                if changed or (new_note and value > 0):
                    item = WorkItem(project_id, name, value, week, person_id, reason=note or None)
                    derived[item.key] = item
            elif changed:
                item = WorkItem(project_id, name, value, reason=new_note)
                derived[item.key] = item
    return derived


def workspace_grid(ctx: AppContext, week: date, fields=(*ALLOCATION_FIELDS, "week_hours"), key: str = "grid") -> None:
    """Editable grid. Type the final number you want; nothing is written until Save / Approve."""
    fy_id = ctx.fy["id"]
    person_id = ctx.person["id"] if ctx.person else None
    if "week_hours" in fields and person_id is None:
        st.info("Add yourself under Settings → Person to log weekly hours.")
        fields = tuple(f for f in fields if f != "week_hours")
    if not fields:
        return

    saved = changes.get_saved_items(ctx.conn, fy_id)
    merged = changes.merge_items(saved, working_items(fy_id))
    state = changes.load_state(ctx.conn, fy_id, merged)
    rows_to_show = [b for b in state.balances if b.status != "cancelled" or b.allocated or b.spent]
    if not rows_to_show:
        st.info("No projects yet. Add one under Allocations → Projects.")
        return

    shown_values = changes.grid_values(ctx.conn, fy_id, merged, week, person_id)
    saved_values = changes.grid_values(ctx.conn, fy_id, saved, week, person_id)
    hours_col = _hours_label(week)

    records = []
    for b in rows_to_show:
        values = shown_values[b.project_id]
        color = risk_color(b.pct_remaining, b.overdrawn)
        record = {"Project": b.project_name, "Pending": _pending_text(b.project_id, week, state.pending_keys)}
        if "week_hours" in fields:
            record[hours_col] = values["week_hours"]
        for name in ALLOCATION_FIELDS:
            if name in fields:
                record[COLUMN_LABEL[name]] = values[name]
        record["Spent"] = b.spent
        record["Available"] = b.available
        record["Status"] = f"{RISK_DOT[color]} {RISK_LABEL[color] if b.status == 'active' else b.status}"
        record["Note"] = values["note"]
        record["Cost code"] = b.cost_code_name
        records.append(record)
    frame = pd.DataFrame(records)

    editable = [hours_col if f == "week_hours" else COLUMN_LABEL[f] for f in fields] + ["Note"]
    number = {"min_value": 0.0, "step": 0.25, "format": "%.2f", "required": True}
    column_config = {c: st.column_config.NumberColumn(c, **number) for c in editable if c != "Note"}
    column_config["Spent"] = st.column_config.NumberColumn("Spent", format="%.2f")
    column_config["Available"] = st.column_config.NumberColumn(
        "Available", format="%.2f", help="Allocated − spent − reserved − frozen")
    column_config["Note"] = st.column_config.TextColumn("Note", help="Optional. Saved with whatever you change on this row.")
    column_config["Pending"] = st.column_config.TextColumn("Pending", width="medium", help="Changed but not yet approved")

    nonce = st.session_state.get("grid_nonce", 0)
    edited = st.data_editor(
        frame, key=f"{key}_{fy_id}_{week.isoformat()}_{nonce}", hide_index=True, num_rows="fixed",
        width="stretch", disabled=[c for c in frame.columns if c not in editable], column_config=column_config,
    )

    project_ids = [b.project_id for b in rows_to_show]
    derived = _derive_working(edited, project_ids, fields, saved_values, week, person_id, hours_col)
    scope = {(p, f, week if f == "week_hours" else None) for p in project_ids for f in fields}
    store = _store(fy_id)
    updated = {k: v for k, v in store.items() if k not in scope} | derived
    if updated != store:
        st.session_state["working_items"][fy_id] = updated
        st.rerun()   # so every number on the page reflects the edit


# action bar --------------------------------------------------------------------------------------

def _save(ctx: AppContext, items, note) -> None:
    changes.save_items(ctx.conn, ctx.fy["id"], items, note=note)
    _reset_editors(ctx.fy["id"])


def action_bar(ctx: AppContext, key: str = "bar") -> None:
    """Save = keep as intentions. Approve = put in the system. Discard = forget saved and unsaved edits."""
    fy_id = ctx.fy["id"]
    working = working_items(fy_id)
    saved_count = changes.pending_count(ctx.conn, fy_id)
    merged = current_items(ctx)

    if not merged:
        st.caption("Type the final numbers you want in the grid. Nothing changes until you Save or Approve.")
        return

    result = changes.validate(ctx.conn, fy_id, merged)
    for error in result.errors:
        st.error(error)
    for warning in result.warnings:
        st.warning(warning, icon="⚠️")

    parts = []
    if working:
        parts.append(f"**{len(working)} unsaved**")
    if saved_count:
        parts.append(f"**{saved_count} saved, not approved**")
    st.markdown(" · ".join(parts))

    note = st.text_input(
        "Note for this set of changes (optional)", value=changes.get_saved_note(ctx.conn, fy_id) or "",
        key=f"{key}_note_{st.session_state.get('grid_nonce', 0)}",
    )
    save_col, approve_col, discard_col, _ = st.columns([1, 1, 1, 3])
    blocked = bool(result.errors)

    if save_col.button("Save", key=f"{key}_save", disabled=blocked or not working, width="stretch",
                       help="Keep these as intentions (stored in a JSON file next to your database). Not in the system until approved."):
        try:
            _save(ctx, merged, note)
            flash("Saved as intentions. Approve when you want them in the system.")
        except ValidationError as exc:
            st.error(str(exc))
        else:
            st.rerun()

    if approve_col.button("Approve", key=f"{key}_approve", type="primary", disabled=blocked, width="stretch",
                          help="Put every saved and unsaved change in the system."):
        try:
            _save(ctx, merged, note)
            outcome = changes.approve(ctx.conn, fy_id)
            flash(f"Approved — {outcome.rows_written} amendment(s) recorded.")
        except ValidationError as exc:
            st.error(str(exc))
        else:
            st.rerun()

    with discard_col.popover("Discard", width="stretch"):
        st.write("Forget all saved and unsaved changes? Approved data is not affected.")
        if st.button("Yes, discard", key=f"{key}_discard"):
            changes.discard(ctx.conn, fy_id)
            _reset_editors(fy_id)
            flash("Changes discarded.")
            st.rerun()


def pending_badge(ctx: AppContext) -> None:
    """Sidebar reminder shown on every page."""
    saved = changes.pending_count(ctx.conn, ctx.fy["id"])
    unsaved = len(working_items(ctx.fy["id"]))
    if saved or unsaved:
        bits = ([f"{unsaved} unsaved"] if unsaved else []) + ([f"{saved} saved, not approved"] if saved else [])
        st.sidebar.warning(" · ".join(bits) + "\n\nReview on the Dashboard.", icon=":material/edit:")


def week_picker(ctx: AppContext, key: str) -> date:
    weeks = pickable_weeks(ctx.fy["start_date"], ctx.fy["end_date"], ctx.today)
    default = default_week(ctx.fy["start_date"], ctx.fy["end_date"], ctx.today)
    index = weeks.index(default) if default in weeks else 0
    return st.selectbox("Week", weeks, index=index, format_func=week_label, key=f"{key}_{ctx.fy['id']}")
