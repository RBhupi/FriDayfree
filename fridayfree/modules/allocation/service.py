"""Business rules for cost codes and projects, and the single definition of a project's balance.

Hours are never written here: allocation changes go through modules.changes (save -> approve).
"""
import sqlite3
from dataclasses import dataclass

from fridayfree.db import intentions
from fridayfree.modules.allocation import repository as repo
from fridayfree.modules.errors import ValidationError
from fridayfree.utils.charge_string import normalize as normalize_charge_string
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
    def free_hours(self) -> float:
        """Hours not spent and not held — what may be taken back, reserved or frozen.

        Unlike `available` this ignores the status: funds can always be pulled back off a project that was
        completed or cancelled.
        """
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

def _cost_code_fields(charge_string, name, prj_code, pt_code, notes, expires_on):
    charge_string = normalize_charge_string(charge_string)
    if not charge_string:
        raise ValidationError("Paste the cost code string — it is what the Copy button gives you.")
    name = (name or "").strip()
    if not name:
        raise ValidationError("Give the cost code a name you will recognise.")
    return {
        "charge_string": charge_string, "name": name,
        "prj_code": (prj_code or "").strip(), "pt_code": (pt_code or "").strip(),
        "notes": (notes or "").strip() or None, "expires_on": expires_on,
    }


def create_cost_code(conn, fy_id: int, charge_string: str, name: str, prj_code="", pt_code="",
                     notes=None, expires_on=None) -> int:
    """A cost code is a bucket of funds. Every field is given by the user; the string is stored verbatim."""
    fields = _cost_code_fields(charge_string, name, prj_code, pt_code, notes, expires_on)
    if repo.get_cost_code_by_string(conn, fy_id, fields["charge_string"]):
        raise ValidationError("That cost code string is already set up for this fiscal year.")
    with conn:
        return repo.insert_cost_code(
            conn, fy_id, fields["charge_string"], fields["prj_code"], fields["pt_code"],
            fields["name"], fields["notes"], fields["expires_on"],
        )


def update_cost_code(conn, cost_code_id: int, charge_string: str, name: str, prj_code="", pt_code="",
                     notes=None, expires_on=None) -> None:
    code = repo.get_cost_code(conn, cost_code_id)
    if code is None:
        raise ValidationError("That cost code does not exist.")
    fields = _cost_code_fields(charge_string, name, prj_code, pt_code, notes, expires_on)
    clash = repo.get_cost_code_by_string(conn, code["fy_id"], fields["charge_string"])
    if clash and clash["id"] != cost_code_id:
        raise ValidationError("Another cost code in this fiscal year already has that string.")
    with conn:
        repo.update_cost_code(
            conn, cost_code_id, fields["charge_string"], fields["prj_code"], fields["pt_code"],
            fields["name"], fields["notes"], fields["expires_on"],
        )


def suggest_codes(charge_string: str) -> dict:
    """Pre-fill help for the form only: what PRJ/PT codes the pasted string seems to contain."""
    try:
        parsed = parse_charge_string(charge_string)
    except ValueError:
        return {"prj_code": "", "pt_code": "", "name": ""}
    return {"prj_code": parsed.prj_code, "pt_code": parsed.pt_code, "name": parsed.suggested_name}


def list_cost_codes(conn, fy_id: int) -> list[dict]:
    return repo.list_cost_codes(conn, fy_id)


def get_cost_code(conn, cost_code_id: int) -> dict:
    code = repo.get_cost_code(conn, cost_code_id)
    if code is None:
        raise ValidationError("That cost code does not exist.")
    return code


def delete_cost_code(conn, cost_code_id: int) -> None:
    code = get_cost_code(conn, cost_code_id)
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
    """A project draws from exactly one cost code and starts with 0 hours; use Allocate to give it some."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Give the project a tag, e.g. alpha_main.")
    if repo.get_cost_code(conn, cost_code_id) is None:
        raise ValidationError("Pick the cost code this project draws from.")
    try:
        with conn:
            return repo.insert_project(conn, cost_code_id, name)
    except sqlite3.IntegrityError as exc:
        raise ValidationError(f"{name} already exists under that cost code.") from exc


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
