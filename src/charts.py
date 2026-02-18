"""Plotly chart builders for Fleet Scheduler."""
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta


# Color palette for device types
DEVICE_COLORS = {
    "Opus": "#4C78A8",
    "Mikro": "#E45756",
    "タッチ4": "#54A24B",
}

STATUS_COLORS = {
    "◎": "#4C78A8",  # confirmed - blue
    "★": "#E45756",  # must-win - red
    "☆": "#F58518",  # nice-to-have - orange
    "△": "#BABBBD",  # conditional - grey
}


def _get_color(device_type_name: str) -> str:
    return DEVICE_COLORS.get(device_type_name, "#72B7B2")


def _hex_to_rgba(hex_color: str, alpha: float = 0.3) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def build_timeline_chart(rows: list[dict], start_range: date, end_range: date) -> go.Figure:
    """Build a Gantt-style timeline. One bar per project × device type, sorted by start date."""
    if not rows:
        fig = go.Figure()
        fig.update_layout(title="No deployments in selected range")
        return fig

    # Detect projects that have more than one device type → need type suffix in label
    from collections import Counter
    project_device_count = Counter(r["project_name"] for r in rows)
    multi_device = {name for name, c in project_device_count.items() if c > 1}

    fig = go.Figure()
    y_order = []  # built in start_date ascending order; reversed for chart display

    for row in rows:
        dep_start = max(date.fromisoformat(row["start_date"]), start_range)
        dep_end = min(date.fromisoformat(row["end_date"]), end_range)
        if dep_start > dep_end:
            continue

        proj_name = row["project_name"]
        device_type_name = row.get("device_type_name", "")
        status_icon = row.get("status", "")
        total_count = row.get("total_count", 0)

        y_label = (
            f"{status_icon} {proj_name} · {device_type_name}"
            if proj_name in multi_device
            else f"{status_icon} {proj_name}"
        )

        dep_detail = "<br>".join(
            f"  · {d['venue']} ({d.get('location', '')}) — "
            f"{d['default_device_count']} units [{d['start_date']} → {d['end_date']}]"
            for d in row.get("deployments", [])
        )
        hover = (
            f"<b>{proj_name}</b><br>"
            f"Device: {device_type_name}<br>"
            f"Total: {total_count}<br>"
            f"Period: {row['start_date']} → {row['end_date']}<br>"
            f"Status: {status_icon} | Client: {row.get('client', '')}<br>"
            f"<br>{dep_detail}"
        )

        color = _get_color(device_type_name)
        duration_ms = (dep_end - dep_start).days * 24 * 3600 * 1000

        fig.add_trace(go.Bar(
            x=[duration_ms],
            y=[y_label],
            base=[dep_start.isoformat()],
            orientation="h",
            marker_color=color,
            text=f"{total_count} {device_type_name}",
            textposition="inside",
            hovertext=hover,
            hoverinfo="text",
            showlegend=False,
        ))

        if y_label not in y_order:
            y_order.append(y_label)

    fig.update_layout(
        barmode="overlay",
        xaxis=dict(
            type="date",
            range=[start_range, end_range],
            dtick="M1",
            tickformat="%b %Y",
            gridcolor="#eee",
        ),
        yaxis=dict(
            categoryorder="array",
            categoryarray=list(reversed(y_order)),  # earliest project at top
        ),
        height=max(400, len(y_order) * 36 + 100),
        margin=dict(l=10, r=10, t=40, b=40),
        title="Device Deployment Timeline",
    )
    return fig


def build_capacity_chart(usage_data: list[dict], device_types: list[dict],
                         start_range: date, end_range: date) -> go.Figure:
    """Build stacked area chart: usage vs capacity per device type."""
    if not usage_data:
        fig = go.Figure()
        fig.update_layout(title="No usage data in selected range")
        return fig

    df = pd.DataFrame(usage_data)
    df["week_start"] = pd.to_datetime(df["week_start"])

    fig = go.Figure()

    for dt in device_types:
        dt_data = df[df["device_type_id"] == dt["id"]].sort_values("week_start")
        if dt_data.empty:
            continue

        color = _get_color(dt["name"])
        capacity = dt["total_fleet"] - dt["under_repair"]

        # Usage area
        fig.add_trace(go.Scatter(
            x=dt_data["week_start"],
            y=dt_data["total_in_use"],
            name=f"{dt['name']} — in use",
            fill="tozeroy",
            mode="lines",
            line=dict(color=color),
            fillcolor=_hex_to_rgba(color, 0.3),
        ))

        # Capacity line
        fig.add_trace(go.Scatter(
            x=dt_data["week_start"],
            y=[capacity] * len(dt_data),
            name=f"{dt['name']} — capacity ({capacity})",
            mode="lines",
            line=dict(color=color, dash="dash", width=2),
        ))

    fig.update_layout(
        xaxis=dict(
            type="date",
            range=[start_range, end_range],
            dtick="M1",
            tickformat="%b %Y",
        ),
        yaxis=dict(title="Devices"),
        height=350,
        margin=dict(l=10, r=10, t=40, b=40),
        title="Fleet Capacity vs Usage",
        legend=dict(orientation="h", y=-0.2),
    )
    return fig
