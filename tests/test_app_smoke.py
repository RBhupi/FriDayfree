"""Every page renders on a seeded database without raising. Interaction is covered by the manual checklist."""
import pytest
from streamlit.testing.v1 import AppTest

from fridayfree.db.seed import seed
from tests.conftest import make_conn

APP = __import__("pathlib").Path(__file__).resolve().parent.parent / "fridayfree" / "app.py"

PAGES = [
    "dashboard.render", "allocation.render_funds", "allocation.render_cost_codes", "allocation.render_projects",
    "allocation.render_history", "spending.render_week", "spending.render_history", "tasks.render",
    "settings.render_person", "carryforward.render_carry_forward",
]


def _page_script(page: str, db_path: str):
    import importlib
    from datetime import date

    from fridayfree.db.connection import get_connection
    from fridayfree.modules.settings import service as settings
    from fridayfree.modules.shared_ui import AppContext

    module_name, function_name = page.split(".")
    render = getattr(importlib.import_module(f"fridayfree.modules.{module_name}.ui"), function_name)
    conn = get_connection(db_path)
    fy = settings.list_fiscal_years(conn)[0]
    render(AppContext(conn=conn, fy=fy, person=settings.get_person(conn, fy["id"]), today=date(2026, 9, 17)))
    conn.close()


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "seeded.db")
    conn = make_conn(path)
    seed(conn, today=__import__("datetime").date(2026, 9, 17))
    conn.close()
    return path


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(seeded_db, page):
    at = AppTest.from_function(_page_script, args=(page, seeded_db), default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.title) == 1


def test_whole_app_boots(seeded_db, monkeypatch):
    monkeypatch.setenv("FRIDAYFREE_DB", seeded_db)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not any("Something went wrong" in e.value for e in at.error)
    assert at.title[0].value.startswith("Dashboard")


def test_first_run_shows_fiscal_year_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAYFREE_DB", str(tmp_path / "empty.db"))
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert at.title[0].value == "Fiscal years"
