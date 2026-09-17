"""Carry the leftovers of a finished fiscal year into the next one.

Everything is rebuilt in the new year — the same cost codes and projects — and each project's leftover
balance is allocated to it again, with reserved and frozen hours re-applied as such. The old year is never
written to: its ledgers stay exactly as they are.

Writes go through repositories only. The create_* services each open their own `with conn:`, which would
commit a half-finished carry, so this module reads through services and writes through repositories inside
one transaction.
"""
from dataclasses import dataclass
from datetime import date

from fridayfree.db import intentions
from fridayfree.modules.allocation import repository as allocation_repo
from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.carryforward import repository as repo
from fridayfree.modules.changes import repository as changes_repo
from fridayfree.modules.changes.service import EPSILON
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.settings import repository as settings_repo
from fridayfree.modules.settings import service as settings
from fridayfree.utils.dates import next_fy_dates, next_fy_label

CARRY_NOTE = "Carried forward from {label}"
ROW_REASON = "carried forward from {label}"


@dataclass(frozen=True)
class CarryLine:
    cost_code_id: int
    cost_code_name: str
    charge_string: str
    project_id: int
    project_name: str
    status: str
    left: float
    carries: float
    reserved: float
    frozen: float
    already_there: float          # what a project of that name already has in the target year
    left_behind: str = None       # why it carries nothing


@dataclass(frozen=True)
class CarryPlan:
    source_fy: dict
    target_fy_id: int
    target_label: str
    target_start: date
    target_end: date
    lines: list
    blockers: list
    warnings: list

    @property
    def total_carried(self) -> float:
        return round(sum(line.carries for line in self.lines), 2)

    @property
    def ready(self) -> bool:
        return not self.blockers and bool(self.lines)


@dataclass(frozen=True)
class CarryResult:
    target_fy_id: int
    target_label: str
    change_set_id: int
    cost_codes: int
    projects: int
    rows_written: int
    hours_carried: float
    warnings: list


# eligibility -------------------------------------------------------------------------------------

def already_carried(conn, fy_id: int, target_fy_id=None):
    """The year it was carried into, or None. Two independent signals, either is enough."""
    target = repo.carried_into(conn, fy_id)
    if target:
        return target
    if target_fy_id is None:
        return None
    label = settings.get_fiscal_year(conn, fy_id)["label"]
    if repo.carry_note_exists(conn, target_fy_id, CARRY_NOTE.format(label=label)):
        return settings.get_fiscal_year(conn, target_fy_id)
    return None


def eligibility(conn, fy_id: int, today: date, target_fy_id=None) -> list[str]:
    """Everything standing in the way, in plain words. Empty means go ahead."""
    fy = settings.get_fiscal_year(conn, fy_id)
    blockers = []
    if today <= fy["end_date"]:
        blockers.append(f"{fy['label']} is not over yet — it ends on {fy['end_date']:%b %d %Y}.")
    if intentions.load(conn, fy_id)["items"]:
        blockers.append(f"{fy['label']} still has planned hours that are not approved. Approve or discard them first.")
    if target_fy_id is not None and intentions.load(conn, target_fy_id)["items"]:
        target = settings.get_fiscal_year(conn, target_fy_id)
        blockers.append(f"{target['label']} has planned hours that are not approved. Approve or discard them first.")
    carried = already_carried(conn, fy_id, target_fy_id)
    if carried:
        blockers.append(f"{fy['label']} was already carried forward into {carried['label']}.")
    return blockers


def target_year(conn, fy_id: int, target_fy_id=None):
    """(id or None, label, start, end) for the year to carry into."""
    fy = settings.get_fiscal_year(conn, fy_id)
    years = settings.list_fiscal_years(conn)
    if target_fy_id is not None:
        target = settings.get_fiscal_year(conn, target_fy_id)
        return target["id"], target["label"], target["start_date"], target["end_date"]
    try:
        label = next_fy_label(fy["label"])
    except ValueError:
        label = ""
    start, end = next_fy_dates(fy["start_date"], fy["end_date"], fy["label"])
    for match in (lambda c: c["label"] == label, lambda c: c["start_date"] == start):
        for candidate in years:                  # by label first, then a year starting the day after this one
            if candidate["id"] != fy_id and match(candidate):
                return candidate["id"], candidate["label"], candidate["start_date"], candidate["end_date"]
    return None, label, start, end


# preview -----------------------------------------------------------------------------------------

def plan(conn, fy_id: int, today: date, target_fy_id=None) -> CarryPlan:
    """What would be carried. Writes nothing."""
    fy = settings.get_fiscal_year(conn, fy_id)
    target_id, label, start, end = target_year(conn, fy_id, target_fy_id)
    blockers = eligibility(conn, fy_id, today, target_id)
    existing = {}
    if target_id is not None:
        for balance in allocation.list_balances(conn, target_id):
            existing[(balance.charge_string, balance.project_name)] = balance.allocated

    lines, warnings = [], []
    for b in allocation.list_balances(conn, fy_id):
        left = b.balance
        carries = reserved = frozen = 0.0
        left_behind = None
        if b.status == "cancelled":
            left_behind = "cancelled — left behind"
        elif left < -EPSILON:
            left_behind = f"overdrawn by {-left:g} h — the overdraft stays in {fy['label']}"
            warnings.append(f"{b.project_name} was overdrawn by {-left:g} h; it carries 0 h.")
        elif left > EPSILON:
            carries = round(left, 2)
            frozen = round(min(b.frozen, carries), 2)
            reserved = round(min(b.reserved, carries - frozen), 2)
            if frozen < b.frozen - EPSILON or reserved < b.reserved - EPSILON:
                warnings.append(
                    f"{b.project_name}: only {carries:g} h are left, so it carries {reserved:g} h reserved and "
                    f"{frozen:g} h frozen instead of {b.reserved:g} / {b.frozen:g}.")
            if b.status != "active":
                warnings.append(f"{b.project_name} is {b.status}; its available hours in {label} read 0 until you "
                                f"set it back to active.")
        lines.append(CarryLine(
            cost_code_id=b.cost_code_id, cost_code_name=b.cost_code_name, charge_string=b.charge_string,
            project_id=b.project_id, project_name=b.project_name, status=b.status,
            left=left, carries=carries, reserved=reserved, frozen=frozen,
            already_there=existing.get((b.charge_string, b.project_name), 0.0), left_behind=left_behind,
        ))
    for line in lines:
        if line.already_there:
            warnings.append(f"{line.project_name} already exists in {label} with {line.already_there:g} h; "
                            f"the carried hours are added to it.")
    return CarryPlan(fy, target_id, label, start, end, lines, blockers, warnings)


# the move ----------------------------------------------------------------------------------------

def carry_forward(conn, fy_id: int, today: date, target_fy_id=None, target_label=None,
                  target_start=None, target_end=None, copy_person=True) -> CarryResult:
    """Rebuild this year's cost codes and projects in the next year and allocate the leftovers."""
    proposal = plan(conn, fy_id, today, target_fy_id)
    if proposal.blockers:
        raise ValidationError("\n".join(proposal.blockers))
    if not proposal.lines:
        raise ValidationError("There is nothing to carry forward.")
    source = proposal.source_fy
    label = (target_label or proposal.target_label or "").strip()
    start = target_start or proposal.target_start
    end = target_end or proposal.target_end
    target_id = proposal.target_fy_id
    if target_id is None:
        if not label:
            raise ValidationError("Give the new fiscal year a label, e.g. FY27.")
        if settings_repo.get_fiscal_year_by_label(conn, label):
            raise ValidationError(f"{label} already exists — pick it as the target year instead.")
        if start >= end:
            raise ValidationError("The new fiscal year must start before it ends.")

    note = CARRY_NOTE.format(label=source["label"])
    reason = ROW_REASON.format(label=source["label"])
    codes_made = projects_made = rows = 0
    change_set_id = None
    hours = 0.0

    with conn:                                        # everything, or nothing
        if target_id is None:
            target_id = settings_repo.insert_fiscal_year(conn, label, start, end)
        code_ids, project_ids = {}, {}
        for line in proposal.lines:
            if line.cost_code_id not in code_ids:
                source_code = allocation_repo.get_cost_code(conn, line.cost_code_id)
                existing = allocation_repo.get_cost_code_by_string(conn, target_id, line.charge_string)
                if existing:
                    code_ids[line.cost_code_id] = existing["id"]
                else:
                    code_ids[line.cost_code_id] = allocation_repo.insert_cost_code(
                        conn, target_id, source_code["charge_string"], source_code["prj_code"],
                        source_code["pt_code"], source_code["name"], source_code["notes"], None,
                    )
                    codes_made += 1
            if line.left_behind == "cancelled — left behind":
                continue
            target_code_id = code_ids[line.cost_code_id]
            twin = next((p for p in allocation_repo.list_projects(conn, target_id, include_cancelled=True,
                                                                  cost_code_id=target_code_id)
                         if p["name"] == line.project_name), None)
            if twin:
                project_ids[line.project_id] = twin["id"]
            else:
                new_id = allocation_repo.insert_project(conn, target_code_id, line.project_name)
                if line.status == "completed":
                    allocation_repo.update_project(conn, new_id, line.project_name, line.status)
                project_ids[line.project_id] = new_id
                projects_made += 1

        if copy_person and settings_repo.get_person_for_fy(conn, target_id) is None:
            person = settings_repo.get_person_for_fy(conn, fy_id)
            if person:
                settings_repo.insert_person(conn, target_id, person["name"], person["badge"],
                                            person["rate_dollar"], person["fte"])

        movements = [
            (project_ids[line.project_id], entry_type, value)
            for line in proposal.lines if line.project_id in project_ids
            for entry_type, value in (("fund", line.carries), ("reserve", line.reserved), ("freeze", line.frozen))
            if abs(value) >= EPSILON
        ]
        if movements:
            change_set_id = changes_repo.insert_approval(conn, target_id, note)
            for project_id, entry_type, value in movements:
                allocation_repo.insert_ledger_row(conn, change_set_id, project_id, entry_type, value, None, reason)
                rows += 1
                if entry_type == "fund":
                    hours += value
        repo.set_carried_from(conn, target_id, fy_id)

    return CarryResult(target_id, label or settings.get_fiscal_year(conn, target_id)["label"], change_set_id,
                       codes_made, projects_made, rows, round(hours, 2), proposal.warnings)
