"""The `fridayfree` command (short alias: `fdf`).

    fridayfree              start the app (opens your browser)
    fridayfree --port 8600  ... on another port;  --db FILE  ... with another database
    fridayfree where        show where your data is stored
    fridayfree backup       copy the database to a dated backup file
    fridayfree demo         fill an EMPTY database with demo data
"""
import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fridayfree import __version__
from fridayfree.db import connection

APP_FILE = Path(__file__).resolve().parent / "app.py"


def _run(args) -> int:
    print(f"FriDayfree {__version__}")
    print(f"Data file: {connection.db_path()}")
    print(f"Opening http://localhost:{args.port}  (press Ctrl+C here to stop)\n")
    command = [
        sys.executable, "-m", "streamlit", "run", str(APP_FILE),
        "--server.port", str(args.port),
        "--server.address", "localhost",                 # this machine only
        "--server.headless", "true" if args.no_browser else "false",
        "--browser.gatherUsageStats", "false",
    ]
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 0


def _where(args) -> int:
    path = connection.db_path()
    print(f"Data folder : {path.parent}")
    print(f"Database    : {path}" + ("" if path.exists() else "   (created the first time you start the app)"))
    print(f"Intentions  : {connection.intentions_path()}   (saved, not yet approved; only exists while something is pending)")
    print(f"Error log   : {connection.error_log_path()}")
    return 0


def _backup(args) -> int:
    source = connection.db_path()
    if not source.exists():
        print(f"Nothing to back up yet: {source} does not exist.")
        return 1
    folder = Path(args.to).expanduser() if args.to else source.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"fridayfree-{datetime.now():%Y%m%d-%H%M%S}.db"
    live, copy = sqlite3.connect(str(source)), sqlite3.connect(str(target))
    try:
        live.backup(copy)                                # safe even while the app is running
    finally:
        copy.close()
        live.close()
    print(f"Backup written to {target}")
    pending = connection.intentions_path()
    if pending.exists():
        shutil.copy2(pending, target.with_name(target.stem + ".intentions.json"))
        print(f"Saved intentions copied to {target.stem}.intentions.json")
    return 0


def _demo(args) -> int:
    from fridayfree.db import seed

    seed.main()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="fridayfree", description="FriDayfree — cost code hours tracker. `fdf` is a short alias for this command.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--db", help="use this database file instead of the default")
    parser.add_argument("--port", type=int, default=8501, help="port for the local web page (default 8501)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    parser.set_defaults(handler=_run)
    commands = parser.add_subparsers(title="commands")

    commands.add_parser("run", help="start the app (default)").set_defaults(handler=_run)

    commands.add_parser("where", help="show where your data is stored").set_defaults(handler=_where)

    backup = commands.add_parser("backup", help="copy the database to a dated backup file")
    backup.add_argument("--to", help="folder for the backup (default: <data folder>/backups)")
    backup.set_defaults(handler=_backup)

    commands.add_parser("demo", help="fill an EMPTY database with demo data").set_defaults(handler=_demo)

    args = parser.parse_args(argv)
    if args.db:
        os.environ[connection.DB_ENV_VAR] = str(Path(args.db).expanduser().resolve())
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
