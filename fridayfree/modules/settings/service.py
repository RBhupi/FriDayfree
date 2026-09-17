"""Business rules for fiscal years and the person charging time."""
from datetime import date

from fridayfree.modules.errors import ValidationError
from fridayfree.modules.settings import repository as repo


def create_fiscal_year(conn, label: str, start_date: date, end_date: date) -> int:
    label = (label or "").strip()
    if not label:
        raise ValidationError("Give the fiscal year a label, e.g. FY26.")
    if start_date >= end_date:
        raise ValidationError("The fiscal year must start before it ends.")
    if repo.get_fiscal_year_by_label(conn, label):
        raise ValidationError(f"{label} already exists.")
    with conn:
        return repo.insert_fiscal_year(conn, label, start_date, end_date)


def list_fiscal_years(conn) -> list[dict]:
    return repo.list_fiscal_years(conn)


def get_fiscal_year(conn, fy_id: int) -> dict:
    fy = repo.get_fiscal_year(conn, fy_id)
    if fy is None:
        raise ValidationError("That fiscal year does not exist.")
    return fy


def get_person(conn, fy_id: int):
    return repo.get_person_for_fy(conn, fy_id)


def save_person(conn, fy_id: int, name: str, badge=None, rate_dollar=None, fte=None) -> int:
    """Create or update the single v1 person for a fiscal year."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("A name is required.")
    if rate_dollar is not None and rate_dollar < 0:
        raise ValidationError("The hourly rate cannot be negative.")
    if fte is not None and not 0 < fte <= 1:
        raise ValidationError("FTE must be greater than 0 and at most 1.")
    badge = (badge or "").strip() or None
    existing = repo.get_person_for_fy(conn, fy_id)
    with conn:
        if existing:
            repo.update_person(conn, existing["id"], name, badge, rate_dollar, fte)
            return existing["id"]
        return repo.insert_person(conn, fy_id, name, badge, rate_dollar, fte)
