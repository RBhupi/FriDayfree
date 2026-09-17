"""Business rules for cost codes and projects, and the single definition of a project's balance.

Hours are never written here: allocation changes go through modules.changes (save -> approve).
"""
import sqlite3
from dataclasses import dataclass

from fridayfree.db import intentions
from fridayfree.modules.allocation import repository as repo
from fridayfree.modules.errors import ValidationError
from fridayfree.utils.charge_string import parse_charge_string

PROJECT_STATUSES = ("active", "completed", "cancelled")


@dataclass(frozen=True)
class ProjectBalance:
    project_id: int
    project_name: str
    status: str
    cost_code_id: int
    cost_code_name: str
    charge_string: str
    allocated: float
    spent: float
    reserved: float
    frozen: float

    @property
    def balance(self) -> float:
        return round(self.allocated - self.spent, 2)

    @property
    def available(self) -> float:
        """Hours that can be charged right now. Reserved and frozen hours are held back."""
        if self.status != "active":
            return 0.0
        return round(self.balance - self.reserved - self.frozen, 2)

    @property
    def held(self) -> float:
        return round(self.reserved + self.frozen, 2)

    @property
    def overdrawn(self) -> bool:
        return self.balance < 0

    @property
    def held_breach(self) -> bool:
        """Not overdrawn, but spending has eaten into reserved/frozen hours."""
        return self.status == "active" and self.balance >= 0 and self.available < 0

    @property
    def pct_remaining(self):
        if self.allocated <= 0:
            return None
        return self.available / self.allocated


def make_balance(row: dict) -> ProjectBalance:
    return ProjectBalance(
        project_id=row["project_id"],
        project_name=row["project_name"],
        status=row["status"],
        cost_code_id=row["cost_code_id"],
        cost_code_name=row["cost_code_name"],
        charge_string=row["charge_string"],
        allocated=round(row["allocated"], 2),
        spent=round(row["spent"], 2),
        reserved=round(row["reserved"], 2),
        frozen=round(row["frozen"], 2),
    )


# balances ----------------------------------------------------------------------------------------

def list_balances(conn, fy_id: int) -> list[ProjectBalance]:
    return [make_balance(r) for r in repo.project_balances(conn, fy_id)]


def get_balance(conn, project_id: int) -> ProjectBalance:
    row = repo.project_balance(conn, project_id)
    if row is None:
        raise ValidationError("That project does not exist.")
    return make_balance(row)


def available_hours(conn, project_id: int) -> float:
    return get_balance(conn, project_id).available


# cost codes --------------------------------------------------------------------------------------

def create_cost_code(conn, fy_id: int, charge_string: str, name=None, notes=None) -> int:
    """Decipher the pasted Dayforce string and store it verbatim."""
    try:
        parsed = parse_charge_string(charge_string)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if repo.get_cost_code_by_string(conn, fy_id, parsed.raw):
        raise ValidationError("That charge string is already set up for this fiscal year.")
    name = (name or "").strip() or parsed.suggested_name
    with conn:
        return repo.insert_cost_code(
            conn, fy_id, parsed.raw, parsed.prj_code, parsed.pt_code, name, (notes or "").strip() or None
        )


def update_cost_code(conn, cost_code_id: int, name: str, notes=None) -> None:
    name = (name or "").strip()
    if not name:
        raise ValidationError("A cost code needs a name.")
    with conn:
        repo.update_cost_code(conn, cost_code_id, name, (notes or "").strip() or None)


def list_cost_codes(conn, fy_id: int) -> list[dict]:
    return repo.list_cost_codes(conn, fy_id)


def delete_cost_code(conn, cost_code_id: int) -> None:
    code = repo.get_cost_code(conn, cost_code_id)
    if code is None:
        raise ValidationError("That cost code does not exist.")
    projects = repo.list_projects(conn, code["fy_id"], include_cancelled=True, cost_code_id=cost_code_id)
    blocked = [p["name"] for p in projects if _is_referenced(conn, p["id"])]
    if blocked:
        raise ValidationError(
            "Cannot delete: hours are recorded or planned on " + ", ".join(blocked) + ". Cancel those projects instead."
        )
    with conn:
        for p in projects:
            repo.delete_project(conn, p["id"])
        repo.delete_cost_code(conn, cost_code_id)


# projects ----------------------------------------------------------------------------------------

def create_project(conn, cost_code_id: int, name: str) -> int:
    """A project starts with 0 hours; hours are set on the dashboard and approved."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Give the project a tag, e.g. alpha_main.")
    if repo.get_cost_code(conn, cost_code_id) is None:
        raise ValidationError("That cost code does not exist.")
    try:
        with conn:
            return repo.insert_project(conn, cost_code_id, name)
    except sqlite3.IntegrityError as exc:
        raise ValidationError(f"{name} already exists under that cost code.") from exc


def add_project_from_string(conn, fy_id: int, name: str, charge_string: str) -> int:
    """The main way to add a project: a tag plus the pasted charge string.

    The string's cost code is reused when it already exists for the FY, otherwise it is created.
    """
    try:
        parsed = parse_charge_string(charge_string)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if not (name or "").strip():
        raise ValidationError("Give the project a tag, e.g. alpha_main.")
    existing = repo.get_cost_code_by_string(conn, fy_id, parsed.raw)
    cost_code_id = existing["id"] if existing else create_cost_code(conn, fy_id, parsed.raw)
    return create_project(conn, cost_code_id, name)


def update_project(conn, project_id: int, name: str, status: str) -> None:
    name = (name or "").strip()
    if not name:
        raise ValidationError("A project needs a tag.")
    if status not in PROJECT_STATUSES:
        raise ValidationError(f"Status must be one of {', '.join(PROJECT_STATUSES)}.")
    try:
        with conn:
            repo.update_project(conn, project_id, name, status)
    except sqlite3.IntegrityError as exc:
        raise ValidationError(f"{name} already exists under that cost code.") from exc


def _is_referenced(conn, project_id: int) -> bool:
    """Hours recorded in the ledgers, or planned in the saved intentions."""
    return bool(repo.count_project_references(conn, project_id) or intentions.count_for_project(conn, project_id))


def can_delete_project(conn, project_id: int) -> bool:
    return not _is_referenced(conn, project_id)


def delete_project(conn, project_id: int) -> None:
    if not can_delete_project(conn, project_id):
        raise ValidationError("Hours are recorded or planned on this project. Set it to cancelled instead.")
    with conn:
        repo.delete_project(conn, project_id)


def get_project(conn, project_id: int) -> dict:
    project = repo.get_project(conn, project_id)
    if project is None:
        raise ValidationError("That project does not exist.")
    return project


def list_projects(conn, fy_id: int, include_cancelled=False) -> list[dict]:
    return repo.list_projects(conn, fy_id, include_cancelled=include_cancelled)


def list_ledger(conn, fy_id: int, project_id=None, cost_code_id=None) -> list[dict]:
    return repo.list_ledger_rows(conn, fy_id, project_id=project_id, cost_code_id=cost_code_id)
