"""Saved intentions live in a JSON file next to the database, NOT in the database.

The database only ever holds what has been approved. Until then a change is just a line in

    <database name>.intentions.json        e.g. ~/FriDayfree/fridayfree.intentions.json

Format (human-readable; project/cost code names are informational, ids are what bind):

    {"version": 1,
     "fiscal_years": {"1": {"note": "...", "updated_at": "2026-01-05T09:30:00",
                            "items": [{"project_id": 3, "project": "alpha_main", "field": "week_hours",
                                       "week_start": "2026-01-05", "person_id": 1, "target_value": 8.0,
                                       "dollars": null, "reason": null}]}}}
"""
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

VERSION = 1
ITEM_KEYS = ("project_id", "field", "person_id", "week_start", "target_value", "dollars", "reason")

_memory = {}   # in-memory databases (tests) have no file to sit next to


def store_path(conn: sqlite3.Connection):
    """The JSON file paired with this connection's database, or None for an in-memory database."""
    database_file = conn.execute("PRAGMA database_list").fetchone()[2]
    if not database_file:
        return None
    database_file = Path(database_file)
    return database_file.with_name(database_file.stem + ".intentions.json")


def forget(conn: sqlite3.Connection) -> None:
    """Drop anything remembered for an in-memory connection (used by tests)."""
    _memory.pop(id(conn), None)


def _read(conn) -> dict:
    path = store_path(conn)
    if path is None:
        return _memory.setdefault(id(conn), {"version": VERSION, "fiscal_years": {}})
    if not path.exists():
        return {"version": VERSION, "fiscal_years": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("fiscal_years", {})
    return data


def _write(conn, data: dict) -> None:
    path = store_path(conn)
    if path is None:
        _memory[id(conn)] = data
        return
    data["fiscal_years"] = {k: v for k, v in data["fiscal_years"].items() if v.get("items")}
    if not data["fiscal_years"]:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)   # atomic: never a half-written file


def load(conn, fy_id: int) -> dict:
    """{'note': str | None, 'items': [dict]} with week_start as a date."""
    entry = _read(conn)["fiscal_years"].get(str(fy_id), {})
    items = []
    for raw in entry.get("items", []):
        item = {key: raw.get(key) for key in ITEM_KEYS}
        item["week_start"] = date.fromisoformat(item["week_start"]) if item["week_start"] else None
        items.append(item)
    return {"note": entry.get("note"), "items": items}


def save(conn, fy_id: int, items: list[dict], note=None, labels: dict = None) -> None:
    """Replace the fiscal year's intentions. `labels` maps project_id -> name, for readability only."""
    data = _read(conn)
    rows = []
    for item in items:
        row = {key: item.get(key) for key in ITEM_KEYS}
        row["week_start"] = row["week_start"].isoformat() if row["week_start"] else None
        if labels and row["project_id"] in labels:
            row["project"] = labels[row["project_id"]]
        rows.append(row)
    data["version"] = VERSION
    data["fiscal_years"][str(fy_id)] = {
        "note": note, "updated_at": datetime.now().isoformat(timespec="seconds"), "items": rows,
    }
    _write(conn, data)


def clear(conn, fy_id: int) -> None:
    data = _read(conn)
    if data["fiscal_years"].pop(str(fy_id), None) is not None:
        _write(conn, data)


def count_for_project(conn, project_id: int) -> int:
    return sum(
        1 for entry in _read(conn)["fiscal_years"].values() for item in entry.get("items", [])
        if item.get("project_id") == project_id
    )
