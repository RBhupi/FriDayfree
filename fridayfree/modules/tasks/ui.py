"""Tasks page: a lightweight list, not a PM tool."""
import streamlit as st

from fridayfree.modules.allocation import service as allocation
from fridayfree.modules.shared_ui import AppContext, run_action, show_flashes
from fridayfree.modules.tasks import service as tasks
from fridayfree.modules.tasks.service import TASK_STATUSES

STATUS_LABEL = {"todo": "To do", "in_progress": "In progress", "done": "Done"}


def _task_row(ctx: AppContext, task: dict, projects: dict) -> None:
    with st.container(border=True):
        title_col, status_col = st.columns([7, 3], vertical_alignment="center")
        overdue = task["due_date"] and task["due_date"] < ctx.today and task["status"] != "done"
        due = f" · due {task['due_date']:%b %d}" + (" ⚠️ overdue" if overdue else "") if task["due_date"] else ""
        project = f" · {task['project_name']}" if task["project_name"] else ""
        title = f"~~{task['title']}~~" if task["status"] == "done" else f"**{task['title']}**"
        title_col.markdown(f"{title}  \n:gray[{(project + due).lstrip(' ·') or 'general'}]")
        status = status_col.selectbox(
            "Status", TASK_STATUSES, index=TASK_STATUSES.index(task["status"]), format_func=STATUS_LABEL.get,
            key=f"task_status_{task['id']}", label_visibility="collapsed",
        )
        if status != task["status"]:
            tasks.set_status(ctx.conn, task["id"], status)
            st.rerun()
        with st.expander("Edit"):
            new_title = st.text_input("Title", value=task["title"], key=f"task_title_{task['id']}")
            project_id = st.selectbox(
                "Project", [None, *projects], format_func=lambda p: projects.get(p, "General"),
                index=([None, *projects].index(task["project_id"]) if task["project_id"] in projects else 0),
                key=f"task_project_{task['id']}",
            )
            due_date = st.date_input("Due date", value=task["due_date"], key=f"task_due_{task['id']}")
            notes = st.text_area("Notes", value=task["notes"] or "", key=f"task_notes_{task['id']}")
            save_col, delete_col = st.columns(2)
            if save_col.button("Save", key=f"task_save_{task['id']}"):
                if run_action(lambda: tasks.update_task(ctx.conn, task["id"], new_title, project_id, status, due_date, notes),
                              "Task updated."):
                    st.rerun()
            if delete_col.button("Delete", key=f"task_del_{task['id']}"):
                tasks.delete_task(ctx.conn, task["id"])
                st.rerun()


def render(ctx: AppContext) -> None:
    st.title("Tasks")
    show_flashes()
    projects = {p["id"]: p["name"] for p in allocation.list_projects(ctx.conn, ctx.fy["id"])}

    with st.form("new_task", clear_on_submit=True):
        title_col, project_col, due_col = st.columns([5, 3, 2])
        title = title_col.text_input("New task")
        project_id = project_col.selectbox("Project", [None, *projects], format_func=lambda p: projects.get(p, "General"))
        due_date = due_col.date_input("Due", value=None)
        if st.form_submit_button("Add task", type="primary"):
            if run_action(lambda: tasks.add_task(ctx.conn, title, project_id=project_id, due_date=due_date), "Task added."):
                st.rerun()

    view_col, done_col = st.columns([3, 2], vertical_alignment="bottom")
    by_project = view_col.segmented_control("View", ["Flat list", "By project"], default="Flat list", key="task_view") == "By project"
    hide_done = done_col.toggle("Hide done", key="task_hide_done")
    items = [t for t in tasks.list_tasks(ctx.conn, ctx.fy["id"]) if not (hide_done and t["status"] == "done")]
    if not items:
        st.info("No tasks yet.")
        return
    if not by_project:
        for task in items:
            _task_row(ctx, task, projects)
        return
    groups = {}
    for task in items:
        groups.setdefault(task["project_name"] or "General", []).append(task)
    for name, members in groups.items():
        st.markdown(f"#### {name}")
        for task in members:
            _task_row(ctx, task, projects)
