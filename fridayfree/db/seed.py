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

PROJECTS = [   # tag, charge string (all invented), allocated hours, typical hours per week
    ("alpha_main", "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis", 640, 13),
    ("alpha_travel", "101>PRJ0001234 - SAMPLE STUDY – ALPHA>General>PT00567: Analysis", 80, 0),
    ("beta_ops", "205>PRJ0004321 - DEMO PROGRAM – BETA>General>PT00890: Field Work", 900, 15),
    ("beta_workshop", "205>PRJ0004321 - DEMO PROGRAM – BETA>General>PT00890: Field Work", 120, 1),
    ("gamma_tools", "310>PRJ0007788 - EXAMPLE CAMPAIGN – GAMMA>General>PT00321: Modelling", 420, 7),
    ("gamma_docs", "310>PRJ0007788 - EXAMPLE CAMPAIGN – GAMMA>General>PT00321: Modelling", 170, 2),
    ("delta_pilot", "412>PRJ0009900 - PILOT EFFORT – DELTA>General>PT00111: Research", 300, 4),
    ("admin", "500>PRJ0000001 - Group Overhead>General>PT00001: Administration", 110, 1),
]


def seed(conn, today: date = None) -> dict:
    today = today or date.today()
    fy_label = f"FY{(today.year + (1 if today.month >= 10 else 0)) % 100:02d}"
    start, end = fy_default_dates(fy_label)
    fy_id = settings.create_fiscal_year(conn, fy_label, start, end)
    person_id = settings.save_person(conn, fy_id, "Demo Researcher", badge="B00000", rate_dollar=100.0, fte=1.0)

    ids = {tag: allocation.add_project_from_string(conn, fy_id, tag, string) for tag, string, _, _ in PROJECTS}

    def approve(items, note=None):
        changes.save_items(conn, fy_id, items, note=note)
        changes.approve(conn, fy_id)

    approve([WorkItem(ids[tag], "allocated", hours) for tag, _, hours, _ in PROJECTS], note="Initial FY allocations")
    approve([WorkItem(ids["alpha_travel"], "reserved", 40, reason="Conference travel")], note="Hold conference hours")
    approve([WorkItem(ids["delta_pilot"], "frozen", 60, reason="Pending sponsor review")], note="Pilot partially frozen")

    rng = random.Random(7)
    past_weeks = [w for w in fy_weeks(start, end) if w < current_week(today)]
    for week in past_weeks:
        items = []
        for tag, _, _, pace in PROJECTS:
            hours = max(0.0, round((pace + rng.uniform(-3, 3)) * 4) / 4) if pace else 0.0
            if hours:
                items.append(WorkItem(ids[tag], "week_hours", hours, week, person_id))
        approve(items)
    if past_weeks:
        week = past_weeks[len(past_weeks) // 2]
        approve([WorkItem(ids["beta_ops"], "week_hours", 10, week, person_id, reason="Corrected after timesheet review")])

    approve([WorkItem(ids["gamma_docs"], "allocated", 150), WorkItem(ids["gamma_tools"], "allocated", 440)],
            note="Move 20 h from docs to tools")

    # one set of intentions left saved, not approved
    changes.save_items(conn, fy_id, [
        WorkItem(ids["admin"], "allocated", 130, reason="Asked division for 20 more hours"),
        WorkItem(ids["alpha_travel"], "reserved", 0, reason="Conference is next week"),
    ], note="To confirm with budget office")

    tasks.add_task(conn, "Submit conference travel request", project_id=ids["alpha_travel"],
                   due_date=today + timedelta(days=10))
    tasks.add_task(conn, "Ask about the pilot freeze", project_id=ids["delta_pilot"], status="in_progress")
    tasks.add_task(conn, "Back up fridayfree.db")
    return {"fy_id": fy_id, "person_id": person_id, "projects": ids}


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
