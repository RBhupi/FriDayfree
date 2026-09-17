import sqlite3

from fridayfree import cli
from fridayfree.db import connection


def test_default_data_folder_is_in_the_home_directory(monkeypatch, tmp_path):
    monkeypatch.delenv(connection.DB_ENV_VAR, raising=False)
    monkeypatch.delenv(connection.HOME_ENV_VAR, raising=False)
    monkeypatch.setattr(connection.Path, "home", lambda: tmp_path)
    assert connection.db_path() == tmp_path / "FriDayfree" / "fridayfree.db"
    assert connection.error_log_path().parent == connection.db_path().parent
    assert (tmp_path / "FriDayfree").is_dir()


def test_folder_and_file_overrides(monkeypatch, tmp_path):
    monkeypatch.delenv(connection.DB_ENV_VAR, raising=False)
    monkeypatch.setenv(connection.HOME_ENV_VAR, str(tmp_path / "elsewhere"))
    assert connection.db_path() == tmp_path / "elsewhere" / "fridayfree.db"
    monkeypatch.setenv(connection.DB_ENV_VAR, str(tmp_path / "mine" / "fy26.db"))
    assert connection.db_path() == (tmp_path / "mine" / "fy26.db").resolve()
    assert connection.error_log_path().parent == (tmp_path / "mine").resolve()


def test_where_prints_the_location(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(connection.HOME_ENV_VAR, str(tmp_path))
    monkeypatch.delenv(connection.DB_ENV_VAR, raising=False)
    assert cli.main(["where"]) == 0
    assert str(tmp_path / "fridayfree.db") in capsys.readouterr().out


def test_db_option_and_backup(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(connection.DB_ENV_VAR, "")            # restored after the test
    db = tmp_path / "work.db"
    assert cli.main(["--db", str(db), "backup"]) == 1         # nothing there yet
    conn = connection.get_connection(db)
    connection.init_db(conn)
    conn.execute("INSERT INTO fiscal_years(label, start_date, end_date) VALUES ('FY26', '2025-10-01', '2026-09-30')")
    conn.commit()
    conn.close()
    assert cli.main(["--db", str(db), "backup", "--to", str(tmp_path / "safe")]) == 0
    (copy,) = (tmp_path / "safe").glob("fridayfree-*.db")
    assert sqlite3.connect(str(copy)).execute("SELECT label FROM fiscal_years").fetchone()[0] == "FY26"


def test_demo_refuses_a_database_that_has_data(monkeypatch, tmp_path):
    monkeypatch.setenv(connection.DB_ENV_VAR, "")
    db = tmp_path / "demo.db"
    assert cli.main(["--db", str(db), "demo"]) == 0
    try:
        cli.main(["--db", str(db), "demo"])
    except SystemExit as exc:
        assert "already has data" in str(exc)
    else:
        raise AssertionError("second demo run should refuse")
