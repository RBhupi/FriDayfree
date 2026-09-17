"""Plotly figures. Pure functions: data in, Figure out. One y-axis per chart, status colours always labelled."""
import pandas as pd
import plotly.graph_objects as go

from fridayfree.utils.formatting import RISK_HEX, RISK_LABEL, risk_color

SERIES_BLUE = "#2a78d6"
MUTED = "#898781"
_LAYOUT = dict(margin=dict(l=10, r=10, t=30, b=10), height=320, hovermode="x unified",
               legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))


def _base(fig: go.Figure, y_title: str = "Hours", **overrides) -> go.Figure:
    fig.update_layout(**{**_LAYOUT, **overrides})
    fig.update_yaxes(title_text=y_title, rangemode="tozero")
    return fig


def burn_chart(burn: pd.DataFrame) -> go.Figure:
    """Hours charged per week."""
    fig = go.Figure(go.Bar(
        x=burn["week_start"], y=burn["hours"], name="Hours charged", marker_color=SERIES_BLUE,
        hovertemplate="%{y:.2f} h<extra></extra>",
    ))
    fig.update_xaxes(title_text="Week starting")
    return _base(fig, showlegend=False, bargap=0.25)


def remaining_chart(balances) -> go.Figure:
    """Available hours per active project, coloured and labelled by risk."""
    rows = sorted((b for b in balances if b.status == "active"), key=lambda b: b.available)
    colors = [risk_color(b.pct_remaining, b.overdrawn) for b in rows]
    fig = go.Figure(go.Bar(
        x=[b.available for b in rows], y=[b.project_name for b in rows], orientation="h",
        marker_color=[RISK_HEX[c] for c in colors],
        text=[f"{b.available:g} h · {RISK_LABEL[c]}" for b, c in zip(rows, colors)], textposition="auto",
        customdata=[[b.allocated, b.spent, b.held] for b in rows],
        hovertemplate="%{y}<br>available %{x:.2f} h<br>allocated %{customdata[0]:.2f} · spent %{customdata[1]:.2f}"
                      " · held %{customdata[2]:.2f}<extra></extra>",
    ))
    fig.update_xaxes(title_text="Available hours")
    return _base(fig, y_title=None, showlegend=False, hovermode="closest", height=max(220, 60 + 36 * len(rows)))


def cumulative_chart(cumulative: pd.DataFrame, projection=None) -> go.Figure:
    """Cumulative hours against the total allocation, with an optional dashed end-of-FY projection."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cumulative["week_start"], y=cumulative["cumulative_hours"], name="Spent (cumulative)",
        mode="lines", line=dict(color=SERIES_BLUE, width=2), hovertemplate="%{y:.2f} h<extra>spent</extra>",
    ))
    if projection is not None and len(projection.series) > 1:
        fig.add_trace(go.Scatter(
            x=projection.series["week_start"], y=projection.series["projected"], name="Projected at current pace",
            mode="lines", line=dict(color=SERIES_BLUE, width=2, dash="dash"),
            hovertemplate="%{y:.2f} h<extra>projected</extra>",
        ))
    x_end = projection.series["week_start"].iloc[-1] if projection is not None and len(projection.series) else None
    xs = list(cumulative["week_start"])
    if xs or x_end:
        span = [xs[0] if xs else x_end, x_end or xs[-1]]
        allocation = cumulative["allocation"].iloc[0] if len(cumulative) else projection.total_allocated
        fig.add_trace(go.Scatter(
            x=span, y=[allocation, allocation], name="Total allocation", mode="lines",
            line=dict(color=MUTED, width=2, dash="dot"), hovertemplate="%{y:.2f} h<extra>allocation</extra>",
        ))
    fig.update_xaxes(title_text="Week starting")
    return _base(fig)
