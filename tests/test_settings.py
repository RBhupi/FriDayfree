from datetime import date

import pytest

from fridayfree.modules.errors import ValidationError
from fridayfree.modules.settings import service as settings


def test_create_and_list_fiscal_years(conn):
    fy_id = settings.create_fiscal_year(conn, " FY26 ", date(2025, 10, 1), date(2026, 9, 30))
    settings.create_fiscal_year(conn, "FY27", date(2026, 10, 1), date(2027, 9, 30))
    assert [f["label"] for f in settings.list_fiscal_years(conn)] == ["FY27", "FY26"]   # newest first
    assert settings.get_fiscal_year(conn, fy_id)["start_date"] == date(2025, 10, 1)


def test_fiscal_year_validation(conn, fy):
    with pytest.raises(ValidationError, match="already exists"):
        settings.create_fiscal_year(conn, "FY26", date(2025, 10, 1), date(2026, 9, 30))
    with pytest.raises(ValidationError, match="start before"):
        settings.create_fiscal_year(conn, "FY99", date(2026, 9, 30), date(2025, 10, 1))
    with pytest.raises(ValidationError, match="label"):
        settings.create_fiscal_year(conn, "  ", date(2025, 10, 1), date(2026, 9, 30))
    with pytest.raises(ValidationError):
        settings.get_fiscal_year(conn, 999)


def test_save_person_inserts_then_updates_same_row(conn, fy):
    assert settings.get_person(conn, fy["id"]) is None
    first = settings.save_person(conn, fy["id"], "Example", badge="B1")
    second = settings.save_person(conn, fy["id"], "S. Example", badge="B1", rate_dollar=125.5, fte=0.8)
    assert first == second
    person = settings.get_person(conn, fy["id"])
    assert (person["name"], person["rate_dollar"], person["fte"]) == ("S. Example", 125.5, 0.8)


def test_rate_and_fte_are_optional(conn, fy):
    settings.save_person(conn, fy["id"], "Example")
    person = settings.get_person(conn, fy["id"])
    assert person["rate_dollar"] is None and person["fte"] is None and person["badge"] is None


@pytest.mark.parametrize("kwargs", [{"fte": 0}, {"fte": 1.2}, {"rate_dollar": -1}])
def test_person_validation(conn, fy, kwargs):
    with pytest.raises(ValidationError):
        settings.save_person(conn, fy["id"], "Example", **kwargs)
    with pytest.raises(ValidationError, match="name"):
        settings.save_person(conn, fy["id"], " ")
