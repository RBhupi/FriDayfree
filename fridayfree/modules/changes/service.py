"""The only write path to the ledgers. Two ways in, both append-only:

  record_fund_action  -> a project action (allocate / deallocate / reserve / unreserve / freeze / unfreeze)
                         recorded straight away as one signed row.
  save_items/approve  -> the week's hours: intentions kept in <database>.intentions.json, then approved
                         together as signed corrections.

Existing ledger rows are never updated or deleted.
"""
from dataclasses import dataclass, field, replace
from datetime import date

import pandas as pd

from fridayfree.db import intentions
from fridayfree.modules.allocation import repository as allocation_repo
from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.changes import repository as repo
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.settings import service as settings
from fridayfree.modules.spending import repository as spending_repo
from fridayfree.modules.spending.service import WEEKLY_COLUMNS
from fridayfree.utils.dates import fy_weeks

ENTRY_TYPE = {"allocated": "fund", "reserved": "reserve", "frozen": "freeze"}
FIELDS = (*ENTRY_TYPE, "week_hours")
EPSILON = 0.005   # hours are kept to 2 decimals


@dataclass(frozen=True)
class WorkItem:
    project_id: int
    field: str
    target_value: float
    week_start: date = None
    person_id: int = None
    dollars: float = None
    reason: str = None

    @property
    def key(self):
        return (self.project_id, self.field, self.week_start)


@dataclass(frozen=True)
class State:
    balances: list
    weekly: pd.DataFrame                      # week_start, project_id, hours
    pending_keys: frozenset = frozenset()     # item keys that differ from what is approved


@dataclass(frozen=True)
class Validation:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass(frozen=True)
class ApproveResult:
    change_set_id: int
    rows_written: int
    warnings: list


# pure helpers ------------------------------------------------------------------------------------

def merge_items(saved, working) -> list[WorkItem]:
    """Working (unsaved) edits override saved intentions on the same cell."""
    merged = {i.key: i for i in saved}
    merged.update({i.key: i for i in working})
    return list(merged.values())


def _clean(text):
    return (text or "").strip() or None


# approved snapshot -------------------------------------------------------------------------------

class _Approved:
    """What is in the system right now, looked up per item."""

    def __init__(self, conn, fy_id):
        self.balances = {b.project_id: b for b in allocation.list_balances(conn, fy_id)}
        self.week = {
            (e["person_id"], e["project_id"], e["week_start"]): e
            for e in spending_repo.net_entries(conn, fy_id, include_zero=True)
        }

    def week_entry(self, item: WorkItem) -> dict:
        return self.week.get((item.person_id, item.project_id, item.week_start), {"hours": 0.0, "dollars": None, "notes": None})

    def value(self, item: WorkItem) -> float:
        if item.field == "week_hours":
            return self.week_entry(item)["hours"]
        return getattr(self.balances[item.project_id], item.field)

    def is_noop(self, item: WorkItem) -> bool:
        if abs(item.target_value - self.value(item)) >= EPSILON:
            return False
        if item.field == "week_hours":   # a changed note on its own is still worth recording
            return _clean(item.reason) in (None, self.week_entry(item)["notes"])
        return True


def _apply(approved: _Approved, items) -> State:
    balances = dict(approved.balances)
    weekly = {}
    for (_, project_id, week), entry in approved.week.items():
        weekly[(week, project_id)] = weekly.get((week, project_id), 0.0) + entry["hours"]
    pending = set()
    for item in items:
        if item.project_id not in balances or approved.is_noop(item):
            continue
        pending.add(item.key)
        delta = item.target_value - approved.value(item)
        current = balances[item.project_id]
        if item.field == "week_hours":
            balances[item.project_id] = replace(current, spent=round(current.spent + delta, 2))
            slot = (item.week_start, item.project_id)
            weekly[slot] = weekly.get(slot, 0.0) + delta
        else:
            balances[item.project_id] = replace(current, **{item.field: round(item.target_value, 2)})
    rows = [(w, p, round(h, 2)) for (w, p), h in weekly.items() if abs(h) >= EPSILON]
    return State(list(balances.values()), pd.DataFrame(rows, columns=WEEKLY_COLUMNS), frozenset(pending))


def load_state(conn, fy_id: int, items=()) -> State:
    """Approved state with the given targets applied. items=() gives the approved state itself."""
    return _apply(_Approved(conn, fy_id), items)


def week_values(conn, fy_id: int, items, week_start: date, person_id) -> dict:
    """{project_id: {'hours': float, 'note': str}} for one week, with the planned items applied."""
    approved = _Approved(conn, fy_id)
    planned = {i.key: i for i in items}
    out = {}
    for project_id in approved.balances:
        entry = approved.week.get((person_id, project_id, week_start), {"hours": 0.0, "notes": None})
        row = {"hours": entry["hours"], "note": entry["notes"] or "", "planned": False}
        item = planned.get((project_id, "week_hours", week_start))
        if item is not None:
            row.update(hours=item.target_value, planned=True)
            if item.reason:
                row["note"] = item.reason
        out[project_id] = row
    return out


# fund actions ------------------------------------------------------------------------------------
# Six actions on a project, each recorded immediately as one signed row. A mistake is undone with the
# opposite action, never by editing what is already written.

FUND_ACTIONS = {                      # action: (entry_type, sign, verb, preposition, what it is limited by)
    "allocate":   ("fund", +1, "Allocate", "to", None),
    "deallocate": ("fund", -1, "Deallocate", "from", "free_hours"),
    "reserve":    ("reserve", +1, "Reserve", "on", "free_hours"),
    "unreserve":  ("reserve", -1, "Unreserve", "on", "reserved"),
    "freeze":     ("freeze", +1, "Freeze", "on", "free_hours"),
    "unfreeze":   ("freeze", -1, "Unfreeze", "on", "frozen"),
}
LIMIT_WORD = {"free_hours": "available", "reserved": "currently reserved", "frozen": "currently frozen"}


@dataclass(frozen=True)
class FundResult:
    change_set_id: int
    action: str
    hours: float
    before: object          # ProjectBalance
    after: object           # ProjectBalance
    sentence: str
    warnings: list


def action_sentence(action: str, hours: float, project_name: str) -> str:
    """The button label and the message afterwards: 'Allocate 40 h to alpha_main'."""
    _, _, verb, preposition, _ = FUND_ACTIONS[action]
    return f"{verb} {hours:g} h {preposition} {project_name}"


def opposite_action(action: str) -> str:
    entry_type, sign, *_ = FUND_ACTIONS[action]
    return next(a for a, (t, s, *_) in FUND_ACTIONS.items() if t == entry_type and s == -sign)


def max_hours(balance, action: str) -> float:
    """How much this action may move, given where the project stands. None-limited actions return inf."""
    limit = FUND_ACTIONS[action][4]
    if limit is None:
        return float("inf")
    return max(round(getattr(balance, limit), 2), 0.0)


def _fund_checks(balance, action: str, hours: float) -> list[str]:
    errors = []
    if action not in FUND_ACTIONS:
        return [f"Unknown action {action!r}."]
    if hours is None or hours <= 0:
        errors.append("Enter how many hours, as a positive number.")
        return errors
    name, limit = balance.project_name, FUND_ACTIONS[action][4]
    if action == "allocate" and balance.status == "cancelled":
        errors.append(f"{name} is cancelled. Set it back to active before allocating hours to it.")
    if limit is not None:
        ceiling = max_hours(balance, action)
        if hours > ceiling + EPSILON:
            errors.append(
                f"{name} has {ceiling:g} h {LIMIT_WORD[limit]}; you cannot {action} {hours:g} h."
            )
    return errors


def preview_fund_action(conn, project_id: int, action: str, hours: float):
    """(balance as it would be, errors, warnings) — writes nothing."""
    before = allocation.get_balance(conn, project_id)
    errors = _fund_checks(before, action, hours)
    if errors:
        return before, errors, []
    entry_type, sign, *_ = FUND_ACTIONS[action]
    field = {"fund": "allocated", "reserve": "reserved", "freeze": "frozen"}[entry_type]
    after = replace(before, **{field: round(getattr(before, field) + sign * hours, 2)})
    warnings = []
    if after.held > after.allocated + EPSILON:
        warnings.append(f"{after.project_name}: reserved + frozen ({after.held:g} h) now exceeds its "
                        f"allocation ({after.allocated:g} h).")
    if after.status != "active":
        warnings.append(f"{after.project_name} is {after.status}, so its available hours stay at 0.")
    return after, errors, warnings


def record_fund_action(conn, fy_id: int, project_id: int, action: str, hours: float, note=None) -> FundResult:
    """Record the action at once: one approval + one signed ledger row, in a single transaction."""
    before = allocation.get_balance(conn, project_id)
    after, errors, warnings = preview_fund_action(conn, project_id, action, hours)
    if errors:
        raise ValidationError("\n".join(errors))
    entry_type, sign, *_ = FUND_ACTIONS[action]
    sentence = action_sentence(action, hours, before.project_name)
    with conn:
        change_set_id = repo.insert_approval(conn, fy_id, _clean(note) or sentence)
        allocation_repo.insert_ledger_row(
            conn, change_set_id, project_id, entry_type, round(sign * hours, 2), None, _clean(note)
        )
    return FundResult(change_set_id, action, hours, before, allocation.get_balance(conn, project_id),
                      sentence, warnings)


def recent_fund_actions(conn, fy_id: int, limit: int = 10) -> list[dict]:
    """The latest allocation-ledger rows, newest first, each with the action that would undo it."""
    rows = allocation.list_ledger(conn, fy_id)[:limit]
    for row in rows:
        entry_type, hours = row["entry_type"], row["hours"]
        row["action"] = next(a for a, (t, s, *_) in FUND_ACTIONS.items()
                             if t == entry_type and s == (1 if hours > 0 else -1))
        row["undo_action"] = opposite_action(row["action"])
        row["sentence"] = action_sentence(row["action"], abs(hours), row["project_name"])
    return rows


# validation --------------------------------------------------------------------------------------

def _validate(conn, fy_id, items, approved: _Approved) -> Validation:
    fy = settings.get_fiscal_year(conn, fy_id)
    weeks = set(fy_weeks(fy["start_date"], fy["end_date"]))
    errors, warnings = [], []
    for item in items:
        balance = approved.balances.get(item.project_id)
        if balance is None:
            errors.append("A change points at a project that is not in this fiscal year.")
            continue
        name = balance.project_name
        if item.field not in FIELDS:
            errors.append(f"{name}: unknown field {item.field!r}.")
            continue
        if item.target_value < 0:
            errors.append(f"{name}: {item.field.replace('_', ' ')} cannot be negative.")
        if item.field != "week_hours":
            continue
        if item.person_id is None or item.week_start is None:
            errors.append(f"{name}: weekly hours need a person and a week. Set up the person in Settings first.")
            continue
        if item.week_start.weekday() != 0 or item.week_start not in weeks:
            errors.append(f"{name}: {item.week_start} is not a Monday inside {fy['label']}.")
        if balance.status == "cancelled" and item.target_value > approved.value(item) + EPSILON:
            errors.append(f"{name} is cancelled; hours on it can only be reduced.")
    if errors:
        return Validation(errors, warnings)

    after = {b.project_id: b for b in _apply(approved, items).balances}
    touched = {i.project_id for i in items if not approved.is_noop(i)}
    for project_id in sorted(touched):
        b = after[project_id]
        if b.held > b.allocated + EPSILON:
            errors.append(
                f"{b.project_name}: reserved + frozen ({b.held:g} h) is more than the allocation ({b.allocated:g} h)."
            )
        elif b.overdrawn:
            warnings.append(f"{b.project_name} will be overdrawn by {-b.balance:g} h.")
        elif b.held_breach:
            warnings.append(f"{b.project_name}: charging dips {-b.available:g} h into reserved/frozen hours.")
    for cost_code_id in sorted({after[p].cost_code_id for p in touched}):
        members = [b for b in after.values() if b.cost_code_id == cost_code_id]
        total = round(sum(b.balance for b in members), 2)
        if total < 0:
            warnings.append(f"Cost code {members[0].cost_code_name} will be overdrawn by {-total:g} h.")
    return Validation(errors, warnings)


def validate(conn, fy_id: int, items) -> Validation:
    return _validate(conn, fy_id, list(items), _Approved(conn, fy_id))


# save / approve / discard ------------------------------------------------------------------------

def get_saved_items(conn, fy_id: int) -> list[WorkItem]:
    return [
        WorkItem(r["project_id"], r["field"], r["target_value"], r["week_start"], r["person_id"], r["dollars"], r["reason"])
        for r in intentions.load(conn, fy_id)["items"]
    ]


def get_saved_note(conn, fy_id: int):
    return intentions.load(conn, fy_id)["note"]


def pending_count(conn, fy_id: int) -> int:
    return len(intentions.load(conn, fy_id)["items"])


def save_items(conn, fy_id: int, items, note=None) -> int:
    """Persist intentions (JSON file, not the database). Replaces what was saved; returns how many are kept."""
    approved = _Approved(conn, fy_id)
    items = merge_items([], items)   # last edit per cell wins
    result = _validate(conn, fy_id, items, approved)
    if result.errors:
        raise ValidationError("\n".join(result.errors))
    keep = [i for i in items if not approved.is_noop(i)]
    if not keep:
        intentions.clear(conn, fy_id)
        return 0
    intentions.save(
        conn, fy_id,
        [{"project_id": i.project_id, "field": i.field, "person_id": i.person_id, "week_start": i.week_start,
          "target_value": round(i.target_value, 2), "dollars": i.dollars, "reason": _clean(i.reason)} for i in keep],
        note=_clean(note),
        labels={b.project_id: b.project_name for b in approved.balances.values()},
    )
    return len(keep)


def approve(conn, fy_id: int) -> ApproveResult:
    """Put the saved intentions in the system: append one signed ledger row per changed number."""
    items = get_saved_items(conn, fy_id)
    if not items:
        raise ValidationError("There is nothing saved to approve.")
    approved = _Approved(conn, fy_id)
    result = _validate(conn, fy_id, items, approved)
    if result.errors:
        raise ValidationError("\n".join(result.errors))

    live = [i for i in items if not approved.is_noop(i)]
    change_set_id = None
    if live:
        with conn:   # all rows or none
            change_set_id = repo.insert_approval(conn, fy_id, get_saved_note(conn, fy_id))
            for item in live:
                delta = round(item.target_value - approved.value(item), 2)
                if item.field == "week_hours":
                    current_dollars = approved.week_entry(item)["dollars"]
                    dollars = None if item.dollars is None else round(item.dollars - (current_dollars or 0), 2)
                    spending_repo.insert_spending_row(
                        conn, change_set_id, item.person_id, item.project_id, item.week_start, delta, dollars, item.reason
                    )
                else:
                    allocation_repo.insert_ledger_row(
                        conn, change_set_id, item.project_id, ENTRY_TYPE[item.field], delta, item.dollars, item.reason
                    )
    intentions.clear(conn, fy_id)   # only after the database has committed
    return ApproveResult(change_set_id, len(live), result.warnings)


def discard(conn, fy_id: int) -> None:
    """Drop the saved intentions. The database is not touched."""
    intentions.clear(conn, fy_id)


# history -----------------------------------------------------------------------------------------

def list_change_sets(conn, fy_id: int) -> list[dict]:
    return repo.list_approved_change_sets(conn, fy_id)


def list_amendments(conn, fy_id: int, change_set_id=None, project_id=None, cost_code_id=None) -> list[dict]:
    return repo.list_amendments(conn, fy_id, change_set_id, project_id, cost_code_id)
