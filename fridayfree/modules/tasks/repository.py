"""SQL only: tasks."""
from datetime import date


def _task(row) -> dict:
    out = dict(row)
    out["due_date"] = date.fromisoformat(out["due_date"]) if out["due_date"] else None
    return out


def insert_task(conn, title, project_id=None, status="todo", due_date: date = None, notes=None) -> int:
    cur = conn.execute(
        "INSERT INTO tasks(title, project_id, status, due_date, notes) VALUES (?, ?, ?, ?, ?)",
        (title, project_id, status, due_date.isoformat() if due_date else None, notes),
    )
    return cur.lastrowid


def update_task(conn, task_id, title, project_id, status, due_date: date, notes) -> None:
    conn.execute(
        "UPDATE tasks SET title = ?, project_id = ?, status = ?, due_date = ?, notes = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, project_id, status, due_date.isoformat() if due_date else None, notes, task_id),
    )


def set_status(conn, task_id, status) -> None:
    conn.execute("UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, task_id))


def delete_task(conn, task_id) -> None:
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def get_task(conn, task_id):
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task(row) if row else None


def list_tasks(conn, fy_id) -> list[dict]:
    """Tasks linked to a project of this FY, plus general tasks (no project)."""
    rows = conn.execute(
        "SELECT t.*, p.name AS project_name FROM tasks t "
        "LEFT JOIN projects p ON p.id = t.project_id LEFT JOIN cost_codes c ON c.id = p.cost_code_id "
        "WHERE t.project_id IS NULL OR c.fy_id = ? ORDER BY t.id",
        (fy_id,),
    )
    return [_task(r) for r in rows]
