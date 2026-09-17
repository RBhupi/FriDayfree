"""Dev-only demo data, built through the same services the UI uses.

    fridayfree demo        # fills the database (see `fridayfree where`); refuses if data exists
"""
import random
from datetime import date, timedelta

from fridayfree.db.connection import get_connection, init_db
from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.changes import service as changes
from fridayfree.modules.changes.service import WorkItem
from fridayfree.modules.settings import service as settings
from fridayfree.modules.tasks import service as tasks
from fridayfree.utils.dates import current_week, fy_default_dates, fy_weeks

COST_CODES = [   # name, charge string (all invented), PRJ, PT, notes
    ("Alpha study", "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis",
     "PRJ0001234", "PT00567", "Main analysis funding"),
    ("Beta programme", "205>PRJ0004321 - DEMO PROGRAM – BETA>General>PT00890: Field Work",
     "PRJ0004321", "PT00890", None),
    ("Gamma campaign", "310>PRJ0007788 - EXAMPLE CAMPAIGN – GAMMA>General>PT00321: Modelling",
     "PRJ0007788", "PT00321", None),
    ("Pilot effort", "412>PRJ0009900 - PILOT EFFORT – DELTA>General>PT00111: Research",
     "PRJ0009900", "PT00111", "Sponsor review pending"),
    ("Group overhead", "500>PRJ0000001 - Group Overhead>General>PT00001: Administration",
     "PRJ0000001", "PT00001", None),
]

PROJECTS = [   # tag, cost code name, hours allocated, typical hours per week
    ("alpha_main", "Alpha study", 640, 13),
    ("alpha_travel", "Alpha study", 80, 0),
    ("beta_ops", "Beta programme", 900, 15),
    ("beta_workshop", "Beta programme", 120, 1),
    ("gamma_tools", "Gamma campaign", 420, 7),
    ("gamma_docs", "Gamma campaign", 170, 2),
    ("delta_pilot", "Pilot effort", 300, 4),
    ("admin", "Group overhead", 110, 1),
]


def seed(conn, today: date = None) -> dict:
    today = today or date.today()
    fy_label = f"FY{(today.year + (1 if today.month >= 10 else 0)) % 100:02d}"
    start, end = fy_default_dates(fy_label)
    fy_id = settings.create_fiscal_year(conn, fy_label, start, end)
    person_id = settings.save_person(conn, fy_id, "Demo Researcher", badge="B00000", rate_dollar=100.0, fte=1.0)

    codes = {name: allocation.create_cost_code(conn, fy_id, string, name, prj, pt, notes)
             for name, string, prj, pt, notes in COST_CODES}
    ids = {tag: allocation.create_project(conn, codes[code_name], tag)
           for tag, code_name, _, _ in PROJECTS}

    def do(tag, action, hours, note=None):
        changes.record_fund_action(conn, fy_id, ids[tag], action, hours, note)

    for tag, _, hours, _ in PROJECTS:
        do(tag, "allocate", hours, "Allocation for the year")
    do("alpha_travel", "reserve", 40, "Conference travel")
    do("delta_pilot", "freeze", 60, "Pending sponsor review")
    do("gamma_docs", "deallocate", 20, "Moved to gamma_tools")
    do("gamma_tools", "allocate", 20, "Moved from gamma_docs")
    do("beta_ops", "allocate", 60, "Extra funds received")

    rng = random.Random(7)
    past_weeks = [w for w in fy_weeks(start, end) if w < current_week(today)]
    for week in past_weeks:
        items = []
        for tag, _, _, pace in PROJECTS:
            hours = max(0.0, round((pace + rng.uniform(-3, 3)) * 4) / 4) if pace else 0.0
            if hours:
                items.append(WorkItem(ids[tag], "week_hours", hours, week, person_id))
        if items:
            changes.save_items(conn, fy_id, items)
            changes.approve(conn, fy_id)
    if past_weeks:
        week = past_weeks[len(past_weeks) // 2]
        changes.save_items(conn, fy_id, [WorkItem(ids["beta_ops"], "week_hours", 10, week, person_id,
                                                  reason="Corrected after timesheet review")])
        changes.approve(conn, fy_id)

    # this week's hours planned but not approved yet
    changes.save_items(conn, fy_id, [
        WorkItem(ids["alpha_main"], "week_hours", 12, current_week(today), person_id),
        WorkItem(ids["beta_ops"], "week_hours", 16, current_week(today), person_id),
    ], note="This week, to approve on Friday")

    tasks.add_task(conn, "Submit conference travel request", project_id=ids["alpha_travel"],
                   due_date=today + timedelta(days=10))
    tasks.add_task(conn, "Ask about the pilot freeze", project_id=ids["delta_pilot"], status="in_progress")
    tasks.add_task(conn, "Back up fridayfree.db")
    return {"fy_id": fy_id, "person_id": person_id, "projects": ids, "cost_codes": codes}


def main() -> None:
    conn = get_connection()
    init_db(conn)
    if settings.list_fiscal_years(conn):
        raise SystemExit("The database already has data. Seed only an empty database.")
    seed(conn)
    conn.close()
    print("Demo data added. Start the app with: fridayfree")


if __name__ == "__main__":
    main()
