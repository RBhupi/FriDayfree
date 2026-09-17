"""SQL only: cost_codes, projects, allocation_ledger and the per-project balance query."""
from datetime import date


def _iso(value):
    return value.isoformat() if isinstance(value, date) else value


def _code(row) -> dict:
    out = dict(row)
    out["expires_on"] = date.fromisoformat(out["expires_on"]) if out.get("expires_on") else None
    return out


# Correlated subqueries (not joins) so ledger rows never multiply each other.
_BALANCE_SQL = """
SELECT p.id AS project_id, p.name AS project_name, p.status,
       c.id AS cost_code_id, c.name AS cost_code_name, c.charge_string, c.prj_code, c.pt_code, c.fy_id,
       COALESCE((SELECT SUM(l.hours) FROM allocation_ledger l
                 WHERE l.project_id = p.id AND l.entry_type = 'fund'), 0)    AS allocated,
       COALESCE((SELECT SUM(l.hours) FROM allocation_ledger l
                 WHERE l.project_id = p.id AND l.entry_type = 'reserve'), 0) AS reserved,
       COALESCE((SELECT SUM(l.hours) FROM allocation_ledger l
                 WHERE l.project_id = p.id AND l.entry_type = 'freeze'), 0)  AS frozen,
       COALESCE((SELECT SUM(s.hours) FROM spending_ledger s WHERE s.project_id = p.id), 0) AS spent
FROM projects p
JOIN cost_codes c ON c.id = p.cost_code_id
"""
_BALANCE_ORDER = " ORDER BY c.name, c.id, p.name"


# cost codes --------------------------------------------------------------------------------------

def insert_cost_code(conn, fy_id, charge_string, prj_code, pt_code, name, notes=None, expires_on=None) -> int:
    cur = conn.execute(
        "INSERT INTO cost_codes(fy_id, charge_string, prj_code, pt_code, name, notes, expires_on) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fy_id, charge_string, prj_code, pt_code, name, notes, _iso(expires_on)),
    )
    return cur.lastrowid


def update_cost_code(conn, cost_code_id, charge_string, prj_code, pt_code, name, notes=None, expires_on=None) -> None:
    conn.execute(
        "UPDATE cost_codes SET charge_string = ?, prj_code = ?, pt_code = ?, name = ?, notes = ?, expires_on = ? "
        "WHERE id = ?",
        (charge_string, prj_code, pt_code, name, notes, _iso(expires_on), cost_code_id),
    )


def delete_cost_code(conn, cost_code_id) -> None:
    conn.execute("DELETE FROM cost_codes WHERE id = ?", (cost_code_id,))


def get_cost_code(conn, cost_code_id):
    row = conn.execute("SELECT * FROM cost_codes WHERE id = ?", (cost_code_id,)).fetchone()
    return _code(row) if row else None


def get_cost_code_by_string(conn, fy_id, charge_string):
    row = conn.execute(
        "SELECT * FROM cost_codes WHERE fy_id = ? AND charge_string = ?", (fy_id, charge_string)
    ).fetchone()
    return _code(row) if row else None


def list_cost_codes(conn, fy_id) -> list[dict]:
    rows = conn.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM projects p WHERE p.cost_code_id = c.id) AS project_count "
        "FROM cost_codes c WHERE c.fy_id = ? ORDER BY c.name, c.id",
        (fy_id,),
    )
    return [_code(r) for r in rows]


# projects ----------------------------------------------------------------------------------------

def insert_project(conn, cost_code_id, name) -> int:
    cur = conn.execute("INSERT INTO projects(cost_code_id, name) VALUES (?, ?)", (cost_code_id, name))
    return cur.lastrowid


def update_project(conn, project_id, name, status) -> None:
    conn.execute("UPDATE projects SET name = ?, status = ? WHERE id = ?", (name, status, project_id))


def delete_project(conn, project_id) -> None:
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def get_project(conn, project_id):
    row = conn.execute(
        "SELECT p.*, c.fy_id, c.charge_string, c.name AS cost_code_name "
        "FROM projects p JOIN cost_codes c ON c.id = p.cost_code_id WHERE p.id = ?",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def list_projects(conn, fy_id, include_cancelled=False, cost_code_id=None) -> list[dict]:
    sql = (
        "SELECT p.*, c.fy_id, c.charge_string, c.name AS cost_code_name "
        "FROM projects p JOIN cost_codes c ON c.id = p.cost_code_id WHERE c.fy_id = ?"
    )
    params = [fy_id]
    if not include_cancelled:
        sql += " AND p.status <> 'cancelled'"
    if cost_code_id is not None:
        sql += " AND c.id = ?"
        params.append(cost_code_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY c.name, c.id, p.name", params)]


def count_project_references(conn, project_id) -> int:
    """Ledger rows and spending rows that point at the project."""
    row = conn.execute(
        "SELECT (SELECT COUNT(*) FROM allocation_ledger WHERE project_id = :p) "
        "     + (SELECT COUNT(*) FROM spending_ledger WHERE project_id = :p)",
        {"p": project_id},
    ).fetchone()
    return row[0]


# balances ----------------------------------------------------------------------------------------

def project_balances(conn, fy_id) -> list[dict]:
    rows = conn.execute(_BALANCE_SQL + " WHERE c.fy_id = ?" + _BALANCE_ORDER, (fy_id,))
    return [dict(r) for r in rows]


def project_balance(conn, project_id):
    row = conn.execute(_BALANCE_SQL + " WHERE p.id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


# ledger ------------------------------------------------------------------------------------------

def insert_ledger_row(conn, change_set_id, project_id, entry_type, hours, dollars=None, reason=None) -> int:
    cur = conn.execute(
        "INSERT INTO allocation_ledger(change_set_id, project_id, entry_type, hours, dollars, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (change_set_id, project_id, entry_type, hours, dollars, reason),
    )
    return cur.lastrowid


def list_ledger_rows(conn, fy_id, project_id=None, cost_code_id=None) -> list[dict]:
    sql = (
        "SELECT l.id, l.change_set_id, l.entry_type, l.hours, l.dollars, l.reason, l.created_at, "
        "       p.id AS project_id, p.name AS project_name, c.id AS cost_code_id, c.name AS cost_code_name "
        "FROM allocation_ledger l "
        "JOIN projects p ON p.id = l.project_id JOIN cost_codes c ON c.id = p.cost_code_id "
        "WHERE c.fy_id = ?"
    )
    params = [fy_id]
    if project_id is not None:
        sql += " AND p.id = ?"
        params.append(project_id)
    if cost_code_id is not None:
        sql += " AND c.id = ?"
        params.append(cost_code_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY l.id DESC", params)]
