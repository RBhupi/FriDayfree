"""SQL only: the run-once marker for carrying a fiscal year forward."""
from datetime import date


def _fy(row) -> dict:
    return {"id": row["id"], "label": row["label"],
            "start_date": date.fromisoformat(row["start_date"]), "end_date": date.fromisoformat(row["end_date"])}


def carried_into(conn, source_fy_id: int):
    """The fiscal year this one was already carried into, or None."""
    row = conn.execute("SELECT * FROM fiscal_years WHERE carried_from_fy_id = ?", (source_fy_id,)).fetchone()
    return _fy(row) if row else None


def carried_from(conn, target_fy_id: int):
    row = conn.execute("SELECT carried_from_fy_id FROM fiscal_years WHERE id = ?", (target_fy_id,)).fetchone()
    return row[0] if row else None


def set_carried_from(conn, target_fy_id: int, source_fy_id: int) -> None:
    conn.execute("UPDATE fiscal_years SET carried_from_fy_id = ? WHERE id = ?", (source_fy_id, target_fy_id))


def carry_note_exists(conn, target_fy_id: int, note: str) -> bool:
    """Belt and braces: change_sets is append-only, so this sentinel note can never be edited away."""
    row = conn.execute(
        "SELECT 1 FROM change_sets WHERE fy_id = ? AND note = ? LIMIT 1", (target_fy_id, note)
    ).fetchone()
    return row is not None
