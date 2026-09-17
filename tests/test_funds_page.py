"""The Funds page drives the real service: pressing a button records the change immediately."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import make_conn

TODAY = date(2026, 9, 17)


def _funds_page(db_path, today_iso):
    from datetime import date

    from fridayfree.db.connection import get_connection
    from fridayfree.modules.allocation import ui as allocation_ui
    from fridayfree.modules.settings import service as settings
    from fridayfree.modules.shared_ui import AppContext

    conn = get_connection(db_path)
    fy = settings.list_fiscal_years(conn)[0]
    allocation_ui.render_funds(AppContext(conn=conn, fy=fy, person=settings.get_person(conn, fy["id"]),
                                          today=date.fromisoformat(today_iso)))
    conn.close()


@pytest.fixture
def funds_app(tmp_path):
    from fridayfree.db.seed import seed

    path = str(tmp_path / "funds.db")
    conn = make_conn(path)
    seed(conn, today=TODAY)
    conn.close()
    return AppTest.from_function(_funds_page, args=(path, TODAY.isoformat()), default_timeout=30).run()


def test_the_page_offers_every_action_and_starts_clean(funds_app):
    assert funds_app.title[0].value.startswith("Funds")
    assert funds_app.radio(key="fund_action").options == [
        "Allocate", "Deallocate", "Reserve", "Unreserve", "Freeze", "Unfreeze"]
    assert not funds_app.exception


def test_pressing_the_button_records_the_action_at_once(tmp_path):
    from fridayfree.db.connection import get_connection
    from fridayfree.db.seed import seed
    from fridayfree.modules.allocation import service as allocation

    path = str(tmp_path / "funds.db")
    conn = make_conn(path)
    ids = seed(conn, today=TODAY)["projects"]
    before = allocation.get_balance(conn, ids["alpha_main"]).allocated
    conn.close()

    app = AppTest.from_function(_funds_page, args=(path, TODAY.isoformat()), default_timeout=30).run()
    app.number_input(key="fund_hours_0").set_value(40.0).run()
    assert app.button[0].label == "Allocate 40 h to alpha_main"      # the button says what it will do
    app.button[0].click().run()
    assert not app.exception

    conn = get_connection(path)
    assert allocation.get_balance(conn, ids["alpha_main"]).allocated == before + 40
    assert conn.execute("SELECT COUNT(*) FROM allocation_ledger WHERE hours = 40").fetchone()[0] >= 1
    conn.close()


def test_undo_fills_in_the_opposite_action_without_erasing_anything(tmp_path):
    from fridayfree.db.connection import get_connection
    from fridayfree.db.seed import seed

    path = str(tmp_path / "funds.db")
    conn = make_conn(path)
    seed(conn, today=TODAY)
    rows_before = conn.execute("SELECT COUNT(*) FROM allocation_ledger").fetchone()[0]
    conn.close()

    app = AppTest.from_function(_funds_page, args=(path, TODAY.isoformat()), default_timeout=30).run()
    undo = next(b for b in app.button if b.label == "Undo")
    undo.click().run()
    assert not app.exception                                   # widget keys must not be written too late
    assert app.session_state["fund_action"] == "deallocate"     # the latest seeded action was an allocate
    assert app.number_input(key="fund_hours_0").value == 60.0
    assert app.selectbox(key="fund_project").value is not None

    conn = get_connection(path)
    assert conn.execute("SELECT COUNT(*) FROM allocation_ledger").fetchone()[0] == rows_before
    conn.close()


def test_adjust_switches_the_form_to_that_project(funds_app):
    adjust = [b for b in funds_app.button if b.label == "Adjust"]
    first = funds_app.selectbox(key="fund_project").value
    adjust[-1].click().run()
    assert not funds_app.exception
    assert funds_app.selectbox(key="fund_project").value != first
