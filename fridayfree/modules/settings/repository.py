"""SQL only: fiscal_years and people."""
from datetime import date


def _fy(row) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "start_date": date.fromisoformat(row["start_date"]),
        "end_date": date.fromisoformat(row["end_date"]),
    }


def insert_fiscal_year(conn, label: str, start_date: date, end_date: date) -> int:
    cur = conn.execute(
        "INSERT INTO fiscal_years(label, start_date, end_date) VALUES (?, ?, ?)",
        (label, start_date.isoformat(), end_date.isoformat()),
    )
    return cur.lastrowid


def list_fiscal_years(conn) -> list[dict]:
    return [_fy(r) for r in conn.execute("SELECT * FROM fiscal_years ORDER BY start_date DESC")]


def get_fiscal_year(conn, fy_id: int):
    row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
    return _fy(row) if row else None


def get_fiscal_year_by_label(conn, label: str):
    row = conn.execute("SELECT * FROM fiscal_years WHERE label = ?", (label,)).fetchone()
    return _fy(row) if row else None


def get_person_for_fy(conn, fy_id: int):
    row = conn.execute("SELECT * FROM people WHERE fy_id = ? ORDER BY id LIMIT 1", (fy_id,)).fetchone()
    return dict(row) if row else None


def insert_person(conn, fy_id, name, badge, rate_dollar, fte) -> int:
    cur = conn.execute(
        "INSERT INTO people(name, badge, fy_id, rate_dollar, fte) VALUES (?, ?, ?, ?, ?)",
        (name, badge, fy_id, rate_dollar, fte),
    )
    return cur.lastrowid


def update_person(conn, person_id, name, badge, rate_dollar, fte) -> None:
    conn.execute(
        "UPDATE people SET name = ?, badge = ?, rate_dollar = ?, fte = ? WHERE id = ?",
        (name, badge, rate_dollar, fte, person_id),
    )
