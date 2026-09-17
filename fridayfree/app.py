"""FriDayfree — Streamlit entry point: navigation, fiscal-year selector, error guard."""
import traceback
from datetime import date, datetime

import streamlit as st

from fridayfree.db.connection import error_log_path, get_connection, init_db
from fridayfree.modules.allocation import ui as allocation_ui
from fridayfree.modules.carryforward import ui as carryforward_ui
from fridayfree.modules.changes import ui as plan_ui
from fridayfree.modules.dashboard import ui as dashboard_ui
from fridayfree.modules.settings import service as settings
from fridayfree.modules.settings import ui as settings_ui
from fridayfree.modules.shared_ui import AppContext
from fridayfree.modules.spending import ui as spending_ui
from fridayfree.modules.tasks import ui as tasks_ui


def _select_fiscal_year(conn, today: date):
    years = settings.list_fiscal_years(conn)
    if not years:
        return None
    labels = [y["label"] for y in years]
    switch_to = st.session_state.pop("switch_to_fy", None)      # queued by another page, applied before the widget
    if switch_to in labels:
        st.session_state["fy_label"] = switch_to
    if st.session_state.get("fy_label") not in labels:
        current = [y for y in years if y["start_date"] <= today <= y["end_date"]]
        st.session_state["fy_label"] = (current or years)[0]["label"]
    label = st.sidebar.selectbox("Fiscal year", labels, key="fy_label")
    return years[labels.index(label)]


def _page(render, ctx, title, icon, url_path, default=False):
    def run():
        render(ctx)
    return st.Page(run, title=title, icon=icon, url_path=url_path, default=default)


def main() -> None:
    st.set_page_config(page_title="FriDayfree", page_icon="⏱️", layout="wide")
    today = date.today()
    conn = get_connection()
    try:
        init_db(conn)
        fy = _select_fiscal_year(conn, today)
        if fy is None:
            settings_ui.render_fiscal_years(conn, today)
            return
        ctx = AppContext(conn=conn, fy=fy, person=settings.get_person(conn, fy["id"]), today=today)
        plan_ui.pending_badge(ctx)
        navigation = st.navigation({
            "": [
                _page(dashboard_ui.render, ctx, "Dashboard", "📊", "dashboard", default=True),
                _page(spending_ui.render_week, ctx, "This week", "⏱️", "this-week"),
            ],
            "Funds": [
                _page(allocation_ui.render_funds, ctx, "Adjust funds", "🧮", "funds"),
                _page(allocation_ui.render_cost_codes, ctx, "Cost codes", "💰", "cost-codes"),
                _page(allocation_ui.render_projects, ctx, "Projects", "🏷️", "projects"),
            ],
            "History": [
                _page(allocation_ui.render_history, ctx, "Everything recorded", "🧾", "history"),
                _page(spending_ui.render_history, ctx, "Weekly hours", "🗓️", "weekly-hours"),
            ],
            "Tasks": [_page(tasks_ui.render, ctx, "Tasks", "✅", "tasks")],
            "Settings": [
                st.Page(lambda: settings_ui.render_fiscal_years(conn, today), title="Fiscal year", icon="📅",
                        url_path="fiscal-year"),
                _page(settings_ui.render_person, ctx, "Person / rate", "👤", "person"),
                _page(carryforward_ui.render_carry_forward, ctx, "Carry forward", "📦", "carry-forward"),
            ],
        })
        navigation.run()
    except Exception:   # noqa: BLE001 — never show a raw traceback to the user (NFR-3)
        with error_log_path().open("a", encoding="utf-8") as log:
            log.write(f"\n--- {datetime.now().isoformat()} ---\n{traceback.format_exc()}")
        st.error("Something went wrong. Your data is safe; details were written to app_errors.log in your data folder.")
    finally:
        conn.close()


main()
