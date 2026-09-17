"""Display formatting and risk thresholds. Pure functions."""

GREEN_ABOVE = 0.30   # > 30 % remaining
AMBER_FROM = 0.10    # 10-30 % remaining; below is red

# Status colours (good / warning / critical / muted). Always shown with a label, never colour alone.
RISK_HEX = {"green": "#0ca30c", "amber": "#fab219", "red": "#d03b3b", "grey": "#898781"}
RISK_LABEL = {"green": "healthy", "amber": "running low", "red": "critical", "grey": "no allocation"}
RISK_DOT = {"green": "🟢", "amber": "🟠", "red": "🔴", "grey": "⚪"}


def format_hours(hours) -> str:
    if hours is None:
        return ""
    return f"{hours:,.2f}".rstrip("0").rstrip(".") + " h"


def format_dollar(amount) -> str:
    if amount is None:
        return ""
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def to_dollars(hours, rate):
    """Hours priced at the person's rate, or None when no rate is known."""
    if rate is None or hours is None:
        return None
    return round(hours * rate, 2)


def risk_color(pct_remaining, overdrawn: bool = False) -> str:
    """'green' | 'amber' | 'red' | 'grey' (grey = nothing allocated, so no percentage exists)."""
    if overdrawn:
        return "red"
    if pct_remaining is None:
        return "grey"
    if pct_remaining > GREEN_ABOVE:
        return "green"
    if pct_remaining >= AMBER_FROM:
        return "amber"
    return "red"
