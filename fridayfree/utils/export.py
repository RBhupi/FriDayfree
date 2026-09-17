"""Markdown export. Pure functions; no extra dependency (pandas' own to_markdown needs tabulate)."""
from datetime import date

import pandas as pd


def _cell(value) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, float):
        value = f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value).replace("|", "\\|").replace("\n", " ")


def df_to_markdown(df: pd.DataFrame) -> str:
    """A GitHub-flavoured markdown table. An empty frame still yields the header."""
    headers = [_cell(c) for c in df.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in df.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def markdown_filename(stem: str, today: date) -> str:
    slug = "-".join(stem.lower().split())
    return f"{slug}-{today.isoformat()}.md"
