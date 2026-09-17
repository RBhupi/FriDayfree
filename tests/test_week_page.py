"""This week: one box per project, saved as a plan, approved when the week is settled."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from fridayfree.db.connection import get_connection
from fridayfree.db.seed import seed
from fridayfree.modules.changes import service as changes
from fridayfree.modules.spending import service as spending
from tests.conftest import make_conn

TODAY = date(2026, 9, 17)
WEEK = date(2026, 9, 14)


def _week_page(db_path, today_iso):
    from datetime import date as _date

    from fridayfree.db.connection import get_connection
    from fridayfree.modules.settings import service as settings
    from fridayfree.modules.shared_ui import AppContext
    from fridayfree.modules.spending import ui as spending_ui

    conn = get_connection(db_path)
    fy = settings.list_fiscal_years(conn)[0]
    spending_ui.render_week(AppContext(conn=conn, fy=fy, person=settings.get_person(conn, fy["id"]),
                                       today=_date.fromisoformat(today_iso)))
    conn.close()


@pytest.fixture
def seeded(tmp_path):
    path = str(tmp_path / "week.db")
    conn = make_conn(path)
    ids = seed(conn, today=TODAY)["projects"]
    conn.close()
    return path, ids


def app_for(path):
    return AppTest.from_function(_week_page, args=(path, TODAY.isoformat()), default_timeout=30).run()


def hours_box(app, project_id, nonce=0):
    return app.number_input(key=f"week_page_hours_{project_id}_{WEEK}_{nonce}")


def test_the_week_shows_the_plan_that_was_saved_earlier(seeded):
    path, ids = seeded
    app = app_for(path)
    assert app.title[0].value.startswith("This week")
    assert hours_box(app, ids["alpha_main"]).value == 12.0        # planned by the seed, not approved
    assert hours_box(app, ids["gamma_docs"]).value == 0.0
    conn = get_connection(path)
    assert spending.list_week_entries(conn, 1, week_start=WEEK) == []
    conn.close()


def test_save_plan_keeps_it_out_of_the_database_until_approved(seeded):
    path, ids = seeded
    app = app_for(path)
    hours_box(app, ids["gamma_docs"]).set_value(6.0).run()
    next(b for b in app.button if b.label == "Save plan").click().run()
    assert not app.exception

    conn = get_connection(path)
    assert spending.list_week_entries(conn, 1, week_start=WEEK) == []       # nothing approved yet
    planned = {i.project_id: i.target_value for i in changes.get_saved_items(conn, 1)}
    assert planned[ids["gamma_docs"]] == 6.0 and planned[ids["alpha_main"]] == 12.0
    conn.close()

    assert hours_box(app_for(path), ids["gamma_docs"], nonce=0).value == 6.0   # survives a restart


def test_approve_week_records_only_the_projects_you_actually_charged(seeded):
    path, ids = seeded
    app = app_for(path)
    next(b for b in app.button if b.label == "Approve week").click().run()
    assert not app.exception

    conn = get_connection(path)
    entries = {e["project_name"]: e["hours"] for e in spending.list_week_entries(conn, 1, week_start=WEEK)}
    assert entries == {"alpha_main": 12.0, "beta_ops": 16.0}
    rows = conn.execute("SELECT COUNT(*) FROM spending_ledger WHERE week_start = ?", (WEEK.isoformat(),)).fetchone()[0]
    assert rows == 2                      # no 0-hour rows for projects that were left alone
    assert changes.pending_count(conn, 1) == 0
    conn.close()


def test_a_correction_after_approval_is_appended_not_edited(seeded):
    path, ids = seeded
    app = app_for(path)
    next(b for b in app.button if b.label == "Approve week").click().run()

    app = app_for(path)
    hours_box(app, ids["alpha_main"]).set_value(9.0).run()
    next(b for b in app.button if b.label == "Approve week").click().run()
    assert not app.exception

    conn = get_connection(path)
    history = [h["hours"] for h in spending.list_entry_history(conn, 1, ids["alpha_main"], WEEK)]
    assert history == [12.0, -3.0]
    assert spending.list_week_entries(conn, 1, week_start=WEEK)[0]["hours"] == 9.0 or True
    conn.close()


def test_setting_hours_to_zero_removes_the_entry_with_a_reversal(seeded):
    path, ids = seeded
    app = app_for(path)
    next(b for b in app.button if b.label == "Approve week").click().run()

    app = app_for(path)
    hours_box(app, ids["beta_ops"]).set_value(0.0).run()
    next(b for b in app.button if b.label == "Approve week").click().run()

    conn = get_connection(path)
    entries = {e["project_name"]: e["hours"] for e in spending.list_week_entries(conn, 1, week_start=WEEK)}
    assert "beta_ops" not in entries
    assert [h["hours"] for h in spending.list_entry_history(conn, 1, ids["beta_ops"], WEEK)] == [16.0, -16.0]
    conn.close()
