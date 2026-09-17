from datetime import date

import pandas as pd
import pytest

from fridayfree.utils import dates, export, formatting
from fridayfree.utils.charge_string import parse_charge_string

FY_START, FY_END = date(2025, 10, 1), date(2026, 9, 30)


# dates -------------------------------------------------------------------------------------------

def test_week_start_returns_monday():
    assert dates.week_start(date(2025, 10, 1)) == date(2025, 9, 29)   # Wednesday
    assert dates.week_start(date(2025, 9, 29)) == date(2025, 9, 29)   # Monday stays
    assert dates.week_start(date(2025, 10, 5)) == date(2025, 9, 29)   # Sunday


def test_fy_weeks_cover_every_overlapping_week():
    weeks = dates.fy_weeks(FY_START, FY_END)
    assert weeks[0] == date(2025, 9, 29)
    assert weeks[-1] == date(2026, 9, 28)
    assert len(weeks) == 53
    assert all(w.weekday() == 0 for w in weeks)


def test_pickable_weeks_capped_four_weeks_ahead_newest_first():
    weeks = dates.pickable_weeks(FY_START, FY_END, today=date(2026, 1, 14))
    assert weeks[0] == date(2026, 2, 9)
    assert weeks[-1] == date(2025, 9, 29)


def test_pickable_weeks_never_exceed_fy():
    weeks = dates.pickable_weeks(FY_START, FY_END, today=date(2027, 1, 1))
    assert weeks[0] == date(2026, 9, 28)
    assert len(weeks) == 53


def test_pickable_weeks_before_fy_starts_offers_first_week():
    assert dates.pickable_weeks(FY_START, FY_END, today=date(2025, 1, 1)) == [date(2025, 9, 29)]


def test_default_week():
    assert dates.default_week(FY_START, FY_END, date(2026, 1, 14)) == date(2026, 1, 12)
    assert dates.default_week(FY_START, FY_END, date(2027, 1, 1)) == date(2026, 9, 28)
    assert dates.default_week(FY_START, FY_END, date(2025, 1, 1)) == date(2025, 9, 29)


def test_week_label():
    assert dates.week_label(date(2026, 9, 14)) == "Sep 14 – Sep 20, 2026"


def test_fy_default_dates():
    assert dates.fy_default_dates("FY26") == (FY_START, FY_END)
    assert dates.fy_default_dates("FY2027") == (date(2026, 10, 1), date(2027, 9, 30))
    with pytest.raises(ValueError):
        dates.fy_default_dates("next year")


# formatting --------------------------------------------------------------------------------------

@pytest.mark.parametrize("pct, overdrawn, expected", [
    (0.31, False, "green"), (0.30, False, "amber"), (0.10, False, "amber"),
    (0.09, False, "red"), (0.0, False, "red"), (0.5, True, "red"), (None, False, "grey"),
])
def test_risk_color_thresholds(pct, overdrawn, expected):
    assert formatting.risk_color(pct, overdrawn) == expected


def test_format_helpers():
    assert formatting.format_hours(1234.5) == "1,234.5 h"
    assert formatting.format_hours(40) == "40 h"
    assert formatting.format_hours(None) == ""
    assert formatting.format_dollar(-1234.5) == "-$1,234.50"
    assert formatting.to_dollars(10, 125.5) == 1255.0
    assert formatting.to_dollars(10, None) is None


# charge string -----------------------------------------------------------------------------------

def test_parse_full_charge_string():
    cs = parse_charge_string("101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis")
    assert cs.raw == "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis"
    assert (cs.prj_code, cs.prj_name) == ("PRJ0001234", "SAMPLE STUDY – ALPHA")
    assert (cs.pt_code, cs.pt_name) == ("PT00567", "Analysis")
    assert cs.other_segments == ("101", "General")
    assert cs.suggested_name == "SAMPLE STUDY – ALPHA / Analysis"


def test_parse_trims_but_keeps_inner_text_verbatim():
    cs = parse_charge_string("  101>PRJ1 - A  B>PT2: C\n")
    assert cs.raw == "101>PRJ1 - A B>PT2: C"


def test_parse_is_forgiving_about_unknown_shapes():
    cs = parse_charge_string("Overhead>Admin")
    assert (cs.prj_code, cs.pt_code) == ("", "")
    assert cs.suggested_name == "Overhead>Admin"
    bare = parse_charge_string("PRJ55>PT66")
    assert (bare.prj_code, bare.pt_code, bare.suggested_name) == ("PRJ55", "PT66", "PRJ55 / PT66")


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_charge_string("   ")


# export ------------------------------------------------------------------------------------------

def test_df_to_markdown_shape_and_escaping():
    df = pd.DataFrame({"Project": ["a|b", None], "Hours": [1.5, float("nan")]})
    assert export.df_to_markdown(df) == (
        "| Project | Hours |\n| --- | --- |\n| a\\|b | 1.5 |\n|  |  |\n"
    )


def test_df_to_markdown_empty_frame_has_header_only():
    assert export.df_to_markdown(pd.DataFrame(columns=["A", "B"])) == "| A | B |\n| --- | --- |\n"


def test_markdown_filename():
    assert export.markdown_filename("Cost Code Summary", date(2026, 9, 17)) == "cost-code-summary-2026-09-17.md"
