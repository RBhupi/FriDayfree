from datetime import date

import pytest

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.errors import ValidationError
from fridayfree.modules.tasks import service as tasks


def test_add_update_delete(conn, fy, project):
    task_id = tasks.add_task(conn, " Write Analysis report ", project_id=project, due_date=date(2026, 3, 1), notes="draft")
    task = tasks.list_tasks(conn, fy["id"])[0]
    assert (task["title"], task["project_name"], task["status"], task["due_date"]) == (
        "Write Analysis report", "alpha_main", "todo", date(2026, 3, 1))
    tasks.update_task(conn, task_id, "Write report", None, "in_progress", None, None)
    task = tasks.list_tasks(conn, fy["id"])[0]
    assert (task["title"], task["project_id"], task["status"], task["due_date"]) == ("Write report", None, "in_progress", None)
    tasks.delete_task(conn, task_id)
    assert tasks.list_tasks(conn, fy["id"]) == []


def test_validation(conn):
    with pytest.raises(ValidationError, match="title"):
        tasks.add_task(conn, "  ")
    with pytest.raises(ValidationError, match="Status"):
        tasks.add_task(conn, "x", status="blocked")
    with pytest.raises(ValidationError, match="Status"):
        tasks.set_status(conn, 1, "blocked")


def test_filters_and_sort_order(conn, fy, project):
    tasks.add_task(conn, "undated")
    tasks.add_task(conn, "later", due_date=date(2026, 5, 1))
    tasks.add_task(conn, "sooner", project_id=project, due_date=date(2026, 1, 1))
    finished = tasks.add_task(conn, "finished", due_date=date(2025, 11, 1))
    tasks.set_status(conn, finished, "done")
    assert [t["title"] for t in tasks.list_tasks(conn, fy["id"])] == ["sooner", "later", "undated", "finished"]
    assert [t["title"] for t in tasks.list_tasks(conn, fy["id"], project_id=project)] == ["sooner"]
    assert [t["title"] for t in tasks.list_tasks(conn, fy["id"], status="done")] == ["finished"]


def test_deleting_a_project_keeps_its_tasks_as_general(conn, fy, project):
    tasks.add_task(conn, "orphan me", project_id=project)
    allocation.delete_project(conn, project)
    assert tasks.list_tasks(conn, fy["id"])[0]["project_id"] is None
