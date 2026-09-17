"""SQL only: approvals (change_sets) and the combined amendment history."""
from datetime import date


def insert_approval(conn, fy_id, note=None) -> int:
    """Record that a set of changes was approved; the ledger rows written with it point here."""
    return conn.execute("INSERT INTO change_sets(fy_id, note) VALUES (?, ?)", (fy_id, note)).lastrowid


def list_approved_change_sets(conn, fy_id) -> list[dict]:
    rows = conn.execute(
        "SELECT cs.id, cs.note, cs.approved_at, "
        "  (SELECT COUNT(*) FROM allocation_ledger l WHERE l.change_set_id = cs.id) "
        "+ (SELECT COUNT(*) FROM spending_ledger s WHERE s.change_set_id = cs.id) AS amendments "
        "FROM change_sets cs WHERE cs.fy_id = ? ORDER BY cs.id DESC",
        (fy_id,),
    )
    return [dict(r) for r in rows]


def list_amendments(conn, fy_id, change_set_id=None, project_id=None, cost_code_id=None) -> list[dict]:
    """Every ledger row (allocation and spending) in one shape, newest first."""
    sql = (
        "SELECT a.*, p.name AS project_name, c.id AS cost_code_id, c.name AS cost_code_name FROM ("
        "  SELECT l.change_set_id, l.created_at, l.entry_type AS kind, l.project_id, NULL AS week_start, "
        "         l.hours, l.dollars, l.reason AS note, l.id AS row_id "
        "  FROM allocation_ledger l "
        "  UNION ALL "
        "  SELECT s.change_set_id, s.created_at, 'hours' AS kind, s.project_id, s.week_start, "
        "         s.hours, s.dollars, s.notes AS note, s.id AS row_id "
        "  FROM spending_ledger s"
        ") a JOIN projects p ON p.id = a.project_id JOIN cost_codes c ON c.id = p.cost_code_id "
        "WHERE c.fy_id = ?"
    )
    params = [fy_id]
    for column, value in (("a.change_set_id", change_set_id), ("a.project_id", project_id), ("c.id", cost_code_id)):
        if value is not None:
            sql += f" AND {column} = ?"
            params.append(value)
    out = []
    for r in conn.execute(sql + " ORDER BY a.change_set_id DESC, a.kind, a.row_id", params):
        row = dict(r)
        row["week_start"] = date.fromisoformat(row["week_start"]) if row["week_start"] else None
        out.append(row)
    return out
