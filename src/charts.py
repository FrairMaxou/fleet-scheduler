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


def build_timeline_chart(deployments: list[dict], start_range: date, end_range: date) -> go.Figure:
    """Build a Gantt-style timeline of deployments."""
    if not deployments:
        fig = go.Figure()
        fig.update_layout(title="No deployments in selected range")
        return fig

    fig = go.Figure()

    for dep in deployments:
        dep_start = max(date.fromisoformat(dep["start_date"]), start_range)
        dep_end = min(date.fromisoformat(dep["end_date"]), end_range)
        if dep_start > dep_end:
            continue

        color = _get_color(dep.get("device_type_name", ""))
        status_icon = dep.get("status", "")
        label = f"{dep['default_device_count']} × {dep.get('device_type_name', '')}"
        hover = (
            f"<b>{dep['project_name']}</b><br>"
            f"Venue: {dep['venue']}<br>"
            f"Location: {dep.get('location', '')}<br>"
            f"Devices: {dep['default_device_count']} {dep.get('device_type_name', '')}<br>"
            f"Period: {dep['start_date']} → {dep['end_date']}<br>"
            f"Status: {status_icon}<br>"
            f"Client: {dep.get('client', '')}"
        )
        y_label = f"{status_icon} {dep['project_name']} — {dep['venue']}"

        fig.add_trace(go.Bar(
            x=[dep_end - dep_start],
            y=[y_label],
            base=[dep_start],
            orientation="h",
            marker_color=color,
            text=label,
            textposition="inside",
            hovertext=hover,
            hoverinfo="text",
            showlegend=False,
        ))

    fig.update_layout(
        barmode="stack",
        xaxis=dict(
            type="date",
            range=[start_range, end_range],
            dtick="M1",
            tickformat="%b %Y",
            gridcolor="#eee",
        ),
        yaxis=dict(autorange="reversed"),
        height=max(400, len(deployments) * 32 + 100),
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
            fillcolor=color.replace(")", ", 0.3)").replace("rgb", "rgba") if "rgb" in color else color + "4D",
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
