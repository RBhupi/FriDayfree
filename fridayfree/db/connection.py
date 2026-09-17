"""SQLite connection helpers. The only place that knows where the data lives.

Default location:  ~/FriDayfree/fridayfree.db   (approved data)
                   ~/FriDayfree/fridayfree.intentions.json   (saved, not yet approved)
Override folder:   FRIDAYFREE_HOME=/some/folder
Override file:     FRIDAYFREE_DB=/some/file.db   (wins over the folder)
"""
import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
HOME_ENV_VAR = "FRIDAYFREE_HOME"
DB_ENV_VAR = "FRIDAYFREE_DB"
DB_FILENAME = "fridayfree.db"
ERROR_LOG_FILENAME = "app_errors.log"


def data_dir() -> Path:
    """Folder that holds the database and the error log. Created on first use."""
    if os.environ.get(DB_ENV_VAR):
        folder = Path(os.environ[DB_ENV_VAR]).expanduser().resolve().parent
    else:
        folder = Path(os.environ.get(HOME_ENV_VAR) or Path.home() / "FriDayfree").expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def db_path() -> Path:
    if os.environ.get(DB_ENV_VAR):
        return Path(os.environ[DB_ENV_VAR]).expanduser().resolve()
    return data_dir() / DB_FILENAME


def intentions_path() -> Path:
    """Saved-but-not-approved changes (JSON), always next to the database."""
    database = db_path()
    return database.with_name(database.stem + ".intentions.json")


def error_log_path() -> Path:
    return data_dir() / ERROR_LOG_FILENAME


def get_connection(path=None) -> sqlite3.Connection:
    """Open a connection with row access by name and foreign keys enforced."""
    target = Path(path) if path else db_path()
    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Upgrade an older database if needed, then create all tables, indexes and triggers. Idempotent."""
    from fridayfree.db import migrations

    migrations.run_all(conn)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
