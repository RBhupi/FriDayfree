"""One-time upgrades of databases created by earlier versions. Each step is idempotent."""
import sqlite3
from datetime import date, datetime
from pathlib import Path

from fridayfree.db import intentions


def _columns(conn, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _backup_file(conn, label: str) -> None:
    database_file = conn.execute("PRAGMA database_list").fetchone()[2]
    if not database_file:
        return
    folder = Path(database_file).parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    copy = sqlite3.connect(str(folder / f"{Path(database_file).stem}-{label}-{datetime.now():%Y%m%d-%H%M%S}.db"))
    try:
        conn.backup(copy)
    finally:
        copy.close()


def move_staging_out_of_database(conn: sqlite3.Connection) -> bool:
    """v1.0 kept saved intentions in change_sets/change_items. They now live in the JSON file.

    Saved (unapproved) items are written to the JSON file, approved change sets are kept, and the
    staging tables disappear. Returns True when an upgrade was performed.
    """
    if "status" not in _columns(conn, "change_sets"):
        return False
    conn.commit()
    _backup_file(conn, "before-upgrade")

    for change_set in conn.execute("SELECT id, fy_id, note FROM change_sets WHERE status = 'saved'").fetchall():
        rows = conn.execute(
            "SELECT i.project_id, i.field, i.person_id, i.week_start, i.target_value, i.dollars, i.reason, p.name "
            "FROM change_items i JOIN projects p ON p.id = i.project_id WHERE i.change_set_id = ? ORDER BY i.id",
            (change_set[0],),
        ).fetchall()
        items = [{
            "project_id": r[0], "field": r[1], "person_id": r[2],
            "week_start": date.fromisoformat(r[3]) if r[3] else None,
            "target_value": r[4], "dollars": r[5], "reason": r[6],
        } for r in rows]
        if items:
            intentions.save(conn, change_set[1], items, note=change_set[2], labels={r[0]: r[7] for r in rows})

    # Standard SQLite table rebuild; foreign keys are switched off so the ledgers keep pointing at change_sets.
    conn.executescript("""
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE change_sets_new (
          id           INTEGER PRIMARY KEY AUTOINCREMENT,
          fy_id        INTEGER NOT NULL REFERENCES fiscal_years(id),
          note         TEXT,
          approved_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO change_sets_new(id, fy_id, note, approved_at)
          SELECT id, fy_id, note, COALESCE(approved_at, updated_at, CURRENT_TIMESTAMP)
          FROM change_sets WHERE status = 'approved';
        DROP TABLE IF EXISTS change_items;
        DROP TABLE change_sets;
        ALTER TABLE change_sets_new RENAME TO change_sets;
        COMMIT;
        PRAGMA foreign_keys = ON;
    """)
    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    if broken:
        raise RuntimeError(f"Upgrade left {len(broken)} dangling reference(s); restore the backup in the backups folder.")
    return True


def add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> bool:
    """Purely additive ALTER TABLE (NULL default), so no table rebuild and no backup is needed."""
    if column in _columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()
    return True


def run_all(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "change_sets" in tables:
        move_staging_out_of_database(conn)
    if "cost_codes" in tables:
        add_column(conn, "cost_codes", "expires_on", "DATE")
    if "fiscal_years" in tables:
        add_column(conn, "fiscal_years", "carried_from_fy_id", "INTEGER REFERENCES fiscal_years(id)")
