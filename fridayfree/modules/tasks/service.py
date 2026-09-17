"""Lightweight tasks/notes. Not a PM tool."""
from datetime import date

from fridayfree.modules.errors import ValidationError
from fridayfree.modules.tasks import repository as repo

TASK_STATUSES = ("todo", "in_progress", "done")


def _check(title, status):
    title = (title or "").strip()
    if not title:
        raise ValidationError("A task needs a title.")
    if status not in TASK_STATUSES:
        raise ValidationError(f"Status must be one of {', '.join(TASK_STATUSES)}.")
    return title


def add_task(conn, title, project_id=None, status="todo", due_date: date = None, notes=None) -> int:
    title = _check(title, status)
    with conn:
        return repo.insert_task(conn, title, project_id, status, due_date, (notes or "").strip() or None)


def update_task(conn, task_id, title, project_id=None, status="todo", due_date: date = None, notes=None) -> None:
    title = _check(title, status)
    with conn:
        repo.update_task(conn, task_id, title, project_id, status, due_date, (notes or "").strip() or None)


def set_status(conn, task_id, status) -> None:
    _check("x", status)
    with conn:
        repo.set_status(conn, task_id, status)


def delete_task(conn, task_id) -> None:
    with conn:
        repo.delete_task(conn, task_id)


def list_tasks(conn, fy_id, project_id=None, status=None) -> list[dict]:
    """Open work first, then by due date (undated last), then oldest first."""
    tasks = repo.list_tasks(conn, fy_id)
    if project_id is not None:
        tasks = [t for t in tasks if t["project_id"] == project_id]
    if status is not None:
        tasks = [t for t in tasks if t["status"] == status]
    return sorted(tasks, key=lambda t: (t["status"] == "done", t["due_date"] is None, t["due_date"] or date.max, t["id"]))
