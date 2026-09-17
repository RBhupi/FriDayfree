"""Settings pages: fiscal years and the person charging time."""
import streamlit as st

from fridayfree.modules.settings import service as settings
from fridayfree.modules.shared_ui import AppContext, run_action, show_flashes
from fridayfree.utils.dates import fy_default_dates


def render_fiscal_years(conn, today) -> None:
    """Works without an AppContext because it is also the first-run screen."""
    st.title("Fiscal years")
    show_flashes()
    years = settings.list_fiscal_years(conn)
    if years:
        st.dataframe(
            [{"Label": y["label"], "Starts": y["start_date"], "Ends": y["end_date"]} for y in years],
            hide_index=True, width="stretch",
        )
    else:
        st.info("Welcome! Create your first fiscal year to get started.")

    st.subheader("Add a fiscal year")
    suggested = f"FY{(today.year + (1 if today.month >= 10 else 0)) % 100:02d}"
    label = st.text_input("Label", value=suggested, key="fy_label")
    try:
        start_default, end_default = fy_default_dates(label)
    except ValueError:
        start_default, end_default = fy_default_dates(suggested)
    start_col, end_col = st.columns(2)
    start = start_col.date_input("Start date", value=start_default, key=f"fy_start_{label}")
    end = end_col.date_input("End date", value=end_default, key=f"fy_end_{label}")
    if st.button("Create fiscal year", type="primary"):
        if run_action(lambda: settings.create_fiscal_year(conn, label, start, end), f"{label.strip()} created."):
            st.rerun()


def render_person(ctx: AppContext) -> None:
    st.title(f"Person · {ctx.fy['label']}")
    show_flashes()
    st.caption("Rate and FTE are optional. With a rate, the dashboard also shows dollars.")
    person = ctx.person or {}
    with st.form("person_form"):
        name = st.text_input("Name", value=person.get("name", ""))
        badge = st.text_input("Badge number", value=person.get("badge") or "")
        rate = st.number_input("Hourly rate ($)", min_value=0.0, value=person.get("rate_dollar"), step=1.0,
                               placeholder="optional")
        fte = st.number_input("FTE", min_value=0.0, max_value=1.0, value=person.get("fte"), step=0.05,
                              placeholder="optional")
        submitted = st.form_submit_button("Save", type="primary")
    if submitted:
        if run_action(lambda: settings.save_person(ctx.conn, ctx.fy["id"], name, badge, rate, fte or None), "Person saved."):
            st.rerun()
