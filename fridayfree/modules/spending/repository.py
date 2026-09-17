"""SQL only: spending_ledger. Rows are signed deltas; queries here fold them into nets."""
from datetime import date


def _with_date(row) -> dict:
    out = dict(row)
    out["week_start"] = date.fromisoformat(out["week_start"])
    return out


def insert_spending_row(conn, change_set_id, person_id, project_id, week_start: date, hours,
                        dollars=None, notes=None) -> int:
    cur = conn.execute(
        "INSERT INTO spending_ledger(change_set_id, person_id, project_id, week_start, hours, dollars, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (change_set_id, person_id, project_id, week_start.isoformat(), hours, dollars, notes),
    )
    return cur.lastrowid


def net_entries(conn, fy_id, week_start: date = None, project_id=None, include_zero=False) -> list[dict]:
    """One row per (person, project, week): net hours/dollars, latest non-empty note, revision count."""
    sql = (
        "SELECT s.person_id, s.project_id, s.week_start, p.name AS project_name, c.name AS cost_code_name, "
        "       ROUND(SUM(s.hours), 2) AS hours, SUM(s.dollars) AS dollars, COUNT(*) AS revisions, "
        "       MAX(s.created_at) AS updated_at, "
        "       (SELECT n.notes FROM spending_ledger n "
        "         WHERE n.person_id = s.person_id AND n.project_id = s.project_id AND n.week_start = s.week_start "
        "           AND n.notes IS NOT NULL ORDER BY n.id DESC LIMIT 1) AS notes "
        "FROM spending_ledger s "
        "JOIN projects p ON p.id = s.project_id JOIN cost_codes c ON c.id = p.cost_code_id "
        "WHERE c.fy_id = ?"
    )
    params = [fy_id]
    if week_start is not None:
        sql += " AND s.week_start = ?"
        params.append(week_start.isoformat())
    if project_id is not None:
        sql += " AND s.project_id = ?"
        params.append(project_id)
    sql += " GROUP BY s.person_id, s.project_id, s.week_start"
    if not include_zero:
        sql += " HAVING ABS(SUM(s.hours)) > 0.004"
    sql += " ORDER BY s.week_start DESC, c.name, p.name"
    return [_with_date(r) for r in conn.execute(sql, params)]


def entry_history(conn, person_id, project_id, week_start: date) -> list[dict]:
    rows = conn.execute(
        "SELECT id, change_set_id, week_start, hours, dollars, notes, created_at FROM spending_ledger "
        "WHERE person_id = ? AND project_id = ? AND week_start = ? ORDER BY id",
        (person_id, project_id, week_start.isoformat()),
    )
    return [_with_date(r) for r in rows]
