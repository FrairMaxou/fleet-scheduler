"""Fleet Scheduler — Device Deployment Planning Tool for Acoustiguide Japan."""
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import date, timedelta
from src import database as db
from src.charts import build_timeline_chart, build_capacity_chart

st.set_page_config(page_title="Fleet Scheduler", layout="wide")

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

credentials = {"usernames": {k: dict(v) for k, v in st.secrets["credentials"]["usernames"].items()}}
authenticator = stauth.Authenticate(
    credentials,
    st.secrets["auth"]["cookie_name"],
    st.secrets["auth"]["cookie_key"],
    cookie_expiry_days=30,
)
authenticator.login()

if st.session_state.get("authentication_status") is False:
    st.error("Incorrect username or password.")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.stop()

authenticator.logout("Logout", "sidebar")
st.sidebar.caption(f"Logged in as {st.session_state['name']}")

# ---------------------------------------------------------------------------
# App init (only reached when authenticated)
# ---------------------------------------------------------------------------

db.init_db()

STATUS_OPTIONS = ["◎", "★", "☆", "△"]
STATUS_LABELS = {
    "◎": "◎ Confirmed",
    "★": "★ Must-win",
    "☆": "☆ Nice-to-have",
    "△": "△ Conditional",
}

# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------

page = st.sidebar.radio("Navigation", ["Dashboard", "Timeline", "Projects", "Fleet"])

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def render_dashboard():
    st.title("Dashboard")

    device_types = db.get_device_types()
    if not device_types:
        st.info("No device types configured. Go to Fleet to add device types.")
        return

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    current_usage = db.get_fleet_usage_by_week(monday, monday)
    usage_map = {r["device_type_id"]: r for r in current_usage}

    # Fleet summary cards
    st.subheader("Current Week")
    cols = st.columns(len(device_types))
    for i, dt in enumerate(device_types):
        with cols[i]:
            usage = usage_map.get(dt["id"])
            in_use = usage["total_in_use"] if usage else 0
            available = dt["total_fleet"] - dt["under_repair"] - in_use
            st.metric(dt["name"], f"{available} available",
                      delta=f"{in_use} in use / {dt['under_repair']} repair",
                      delta_color="off")

    # Shortage alerts — next 12 weeks
    st.subheader("Shortage Alerts")
    end_check = monday + timedelta(weeks=12)
    future_usage = db.get_fleet_usage_by_week(monday, end_check)

    alerts = [r for r in future_usage if r["available"] < 0]
    warnings = [r for r in future_usage if 0 <= r["available"] < r["total_fleet"] * 0.1]

    if alerts:
        for a in alerts:
            st.error(
                f"**SHORTAGE** — {a['device_type_name']}: "
                f"Week of {a['week_start']} — need {a['total_in_use']}, "
                f"available {a['total_fleet'] - a['under_repair']} "
                f"(deficit: {abs(a['available'])})"
            )
    if warnings:
        for w in warnings:
            st.warning(
                f"**LOW STOCK** — {w['device_type_name']}: "
                f"Week of {w['week_start']} — {w['available']} units remaining "
                f"({w['total_in_use']} in use)"
            )
    if not alerts and not warnings:
        st.success("No shortages detected in the next 12 weeks.")

    # Next 4 weeks table
    st.subheader("Next 4 Weeks")
    next_4 = db.get_fleet_usage_by_week(monday, monday + timedelta(weeks=3))
    if next_4:
        df = pd.DataFrame(next_4)
        df = df[["week_start", "device_type_name", "total_in_use", "total_fleet", "under_repair", "available"]]
        df.columns = ["Week", "Device", "In Use", "Fleet Total", "Under Repair", "Available"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No deployments scheduled in the next 4 weeks.")


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def render_timeline():
    st.title("Timeline")

    device_types = db.get_device_types()

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        period = st.selectbox("Period", ["3 months", "6 months", "12 months", "Custom"])
    with col2:
        if period == "Custom":
            start_range = st.date_input("Start", value=date.today())
        else:
            start_range = date.today()
    with col3:
        if period == "Custom":
            end_range = st.date_input("End", value=date.today() + timedelta(days=180))
        elif period == "3 months":
            end_range = date.today() + timedelta(days=90)
        elif period == "12 months":
            end_range = date.today() + timedelta(days=365)
        else:
            end_range = date.today() + timedelta(days=180)
    with col4:
        dt_names = ["All"] + [dt["name"] for dt in device_types]
        device_filter = st.selectbox("Device Type", dt_names)

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.multiselect("Status", STATUS_OPTIONS, default=STATUS_OPTIONS)
    with filter_col2:
        search = st.text_input("Search (project/venue)", "")

    # Get deployments with project info
    all_deployments = db.get_deployments()

    # Enrich with project status and client
    projects_map = {p["id"]: p for p in db.get_projects()}
    for dep in all_deployments:
        proj = projects_map.get(dep["project_id"], {})
        dep["status"] = proj.get("status", "◎")
        dep["client"] = proj.get("client", "")

    # Apply filters
    filtered = all_deployments
    if device_filter != "All":
        filtered = [d for d in filtered if d.get("device_type_name") == device_filter]
    filtered = [d for d in filtered if d.get("status") in status_filter]
    if search:
        search_lower = search.lower()
        filtered = [d for d in filtered
                    if search_lower in d.get("project_name", "").lower()
                    or search_lower in d.get("venue", "").lower()]

    # Filter by date overlap
    filtered = [d for d in filtered
                if date.fromisoformat(d["end_date"]) >= start_range
                and date.fromisoformat(d["start_date"]) <= end_range]

    # Aggregate filtered deployments by project × device type
    agg = {}
    for dep in filtered:
        key = (dep["project_id"], dep.get("device_type_id", 0))
        if key not in agg:
            agg[key] = {
                "project_id": dep["project_id"],
                "project_name": dep.get("project_name", ""),
                "device_type_id": dep.get("device_type_id"),
                "device_type_name": dep.get("device_type_name", ""),
                "status": dep.get("status", "◎"),
                "client": dep.get("client", ""),
                "start_date": dep["start_date"],
                "end_date": dep["end_date"],
                "total_count": dep["default_device_count"],
                "deployments": [dep],
            }
        else:
            entry = agg[key]
            entry["start_date"] = min(entry["start_date"], dep["start_date"])
            entry["end_date"] = max(entry["end_date"], dep["end_date"])
            entry["total_count"] += dep["default_device_count"]
            entry["deployments"].append(dep)

    rows = sorted(agg.values(), key=lambda x: (x["start_date"], x["project_name"]))

    # Gantt chart
    fig = build_timeline_chart(rows, start_range, end_range)
    st.plotly_chart(fig, use_container_width=True)

    # Capacity chart
    dt_id = None
    if device_filter != "All":
        dt_id = next((dt["id"] for dt in device_types if dt["name"] == device_filter), None)

    monday = start_range - timedelta(days=start_range.weekday())
    usage_data = db.get_fleet_usage_by_week(monday, end_range, dt_id)
    cap_fig = build_capacity_chart(usage_data, device_types, start_range, end_range)
    st.plotly_chart(cap_fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def render_projects():
    st.title("Projects")

    device_types = db.get_device_types()
    if not device_types:
        st.warning("Add device types in Fleet first.")
        return

    dt_map = {dt["id"]: dt["name"] for dt in device_types}
    dt_name_to_id = {dt["name"]: dt["id"] for dt in device_types}

    # --- Add new project ---
    if "show_add_project" not in st.session_state:
        st.session_state.show_add_project = False

    if st.button("+ New Project", type="primary"):
        st.session_state.show_add_project = not st.session_state.show_add_project

    if st.session_state.show_add_project:
        with st.container(border=True):
            st.markdown("**New Project**")
            with st.form("new_project", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    p_name = st.text_input("Exhibition Name (JP)")
                    p_client = st.text_input("Client")
                with col2:
                    p_name_en = st.text_input("Exhibition Name (EN)")
                    p_status = st.selectbox("Status", STATUS_OPTIONS,
                                            format_func=lambda x: STATUS_LABELS[x])
                p_notes = st.text_input("Notes")

                c1, c2 = st.columns([3, 1])
                with c1:
                    submitted = st.form_submit_button("Create Project", type="primary")
                with c2:
                    cancelled = st.form_submit_button("Cancel")

                if submitted:
                    if p_name:
                        db.create_project(name=p_name, name_en=p_name_en, client=p_client,
                                          status=p_status, notes=p_notes)
                        st.session_state.show_add_project = False
                        st.rerun()
                    else:
                        st.error("Name is required.")
                if cancelled:
                    st.session_state.show_add_project = False
                    st.rerun()

    st.divider()

    # --- Filters ---
    all_deployments = db.get_deployments()
    venues_by_project = {}
    for dep in all_deployments:
        venues_by_project.setdefault(dep["project_id"], []).append(
            f"{dep['venue']} {dep.get('location', '')}".lower()
        )

    fcol1, fcol2 = st.columns([3, 2])
    with fcol1:
        search = st.text_input("Search", placeholder="name, client, venue…", label_visibility="collapsed")
    with fcol2:
        status_filter = st.multiselect("Status", STATUS_OPTIONS, default=STATUS_OPTIONS,
                                       format_func=lambda x: STATUS_LABELS[x],
                                       label_visibility="collapsed")

    # --- List projects ---
    projects = db.get_projects()
    if not projects:
        st.info("No projects yet.")
        return

    search_lower = search.lower()
    filtered_projects = [
        p for p in projects
        if p["status"] in status_filter
        and (
            not search_lower
            or search_lower in p["name"].lower()
            or search_lower in p.get("name_en", "").lower()
            or search_lower in p.get("client", "").lower()
            or search_lower in p.get("notes", "").lower()
            or any(search_lower in v for v in venues_by_project.get(p["id"], []))
        )
    ]

    if not filtered_projects:
        st.info("No projects match the filter.")
        return

    for proj in filtered_projects:
        status_label = STATUS_LABELS.get(proj["status"], proj["status"])
        with st.expander(f"{proj['status']} {proj['name']} — {proj['client']} ({status_label})"):
            # Edit project
            with st.form(f"edit_proj_{proj['id']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    ed_name = st.text_input("Name", proj["name"], key=f"pn_{proj['id']}")
                    ed_client = st.text_input("Client", proj["client"], key=f"pc_{proj['id']}")
                with col2:
                    ed_name_en = st.text_input("Name EN", proj["name_en"], key=f"pe_{proj['id']}")
                    ed_status = st.selectbox("Status", STATUS_OPTIONS,
                                             index=STATUS_OPTIONS.index(proj["status"]),
                                             format_func=lambda x: STATUS_LABELS[x],
                                             key=f"ps_{proj['id']}")
                with col3:
                    ed_notes = st.text_input("Notes", proj["notes"], key=f"pno_{proj['id']}")

                c1, c2 = st.columns([3, 1])
                with c1:
                    if st.form_submit_button("Update Project"):
                        db.update_project(proj["id"], name=ed_name, name_en=ed_name_en,
                                          client=ed_client, status=ed_status, notes=ed_notes)
                        st.success("Updated")
                        st.rerun()
                with c2:
                    if st.form_submit_button("Delete Project", type="secondary"):
                        db.delete_project(proj["id"])
                        st.success("Deleted")
                        st.rerun()

            # Deployments for this project
            st.markdown("**Deployments:**")
            deployments = [d for d in all_deployments if d["project_id"] == proj["id"]]

            if deployments:
                for dep in deployments:
                    dep_label = (f"{dep['venue']} ({dep['location']}) — "
                                 f"{dep['default_device_count']} {dep.get('device_type_name', '')} — "
                                 f"{dep['start_date']} → {dep['end_date']}")
                    col_dep, col_del = st.columns([5, 1])
                    with col_dep:
                        st.text(dep_label)
                    with col_del:
                        if st.button("Delete", key=f"del_dep_{dep['id']}"):
                            db.delete_deployment(dep["id"])
                            st.rerun()

                    # Weekly allocations editor
                    allocations = db.get_weekly_allocations(dep["id"])
                    if allocations:
                        alloc_df = pd.DataFrame(allocations)
                        alloc_df["week_start"] = pd.to_datetime(alloc_df["week_start"]).dt.strftime("%Y-%m-%d")
                        edited = st.data_editor(
                            alloc_df[["id", "week_start", "device_count"]],
                            column_config={
                                "id": st.column_config.NumberColumn("ID", disabled=True),
                                "week_start": st.column_config.TextColumn("Week", disabled=True),
                                "device_count": st.column_config.NumberColumn("Devices", min_value=0),
                            },
                            hide_index=True,
                            key=f"alloc_{dep['id']}",
                            use_container_width=True,
                        )
                        if st.button("Save Allocations", key=f"save_alloc_{dep['id']}"):
                            for _, row in edited.iterrows():
                                db.update_weekly_allocation(int(row["id"]), int(row["device_count"]))
                            st.success("Allocations saved.")
                            st.rerun()
            else:
                st.caption("No deployments yet.")

            # Add deployment
            with st.form(f"new_dep_{proj['id']}"):
                st.markdown("**Add Deployment:**")
                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    d_venue = st.text_input("Venue", key=f"dv_{proj['id']}")
                    d_location = st.text_input("Location (city)", key=f"dl_{proj['id']}")
                with dc2:
                    d_start = st.date_input("Start Date", key=f"ds_{proj['id']}")
                    d_end = st.date_input("End Date", key=f"de_{proj['id']}")
                with dc3:
                    d_device_type = st.selectbox("Device Type", list(dt_name_to_id.keys()),
                                                  key=f"ddt_{proj['id']}")
                    d_count = st.number_input("Default Device Count", min_value=0, value=0,
                                              key=f"dc_{proj['id']}")
                d_app = st.selectbox("App Type", ["", "App", "Kikubi", "WebApp"],
                                     key=f"da_{proj['id']}")

                if st.form_submit_button("Add Deployment"):
                    if d_venue and d_start and d_end and d_count > 0:
                        db.create_deployment(
                            project_id=proj["id"],
                            venue=d_venue,
                            location=d_location,
                            start_date=d_start,
                            end_date=d_end,
                            device_type_id=dt_name_to_id[d_device_type],
                            default_device_count=d_count,
                            app_type=d_app,
                        )
                        st.success(f"Added deployment: {d_venue}")
                        st.rerun()
                    else:
                        st.error("Fill in venue, dates, and device count.")


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------

def render_fleet():
    st.title("Fleet Management")

    # Add device type
    with st.expander("Add Device Type", expanded=False):
        with st.form("new_device_type"):
            col1, col2, col3 = st.columns(3)
            with col1:
                dt_name = st.text_input("Name (e.g., Opus, Mikro)")
            with col2:
                dt_total = st.number_input("Total Fleet", min_value=0, value=0)
            with col3:
                dt_repair = st.number_input("Under Repair", min_value=0, value=0)

            if st.form_submit_button("Add"):
                if dt_name:
                    try:
                        db.create_device_type(dt_name, dt_total, dt_repair)
                        st.success(f"Added: {dt_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("Name is required.")

    # List and edit device types
    device_types = db.get_device_types()
    if not device_types:
        st.info("No device types configured.")
        return

    st.subheader("Device Types")
    for dt in device_types:
        with st.form(f"edit_dt_{dt['id']}"):
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            with col1:
                ed_name = st.text_input("Name", dt["name"], key=f"dtn_{dt['id']}")
            with col2:
                ed_total = st.number_input("Total Fleet", value=dt["total_fleet"],
                                           min_value=0, key=f"dtt_{dt['id']}")
            with col3:
                ed_repair = st.number_input("Under Repair", value=dt["under_repair"],
                                            min_value=0, key=f"dtr_{dt['id']}")
            with col4:
                st.write("")  # spacer
                save = st.form_submit_button("Save")

            if save:
                db.update_device_type(dt["id"], ed_name, ed_total, ed_repair)
                st.success(f"Updated: {ed_name}")
                st.rerun()

    # Where are devices now
    st.subheader("Current Deployments by Device Type")
    today = date.today()
    all_deps = db.get_deployments()
    active = [d for d in all_deps
              if date.fromisoformat(d["start_date"]) <= today <= date.fromisoformat(d["end_date"])]

    if active:
        df = pd.DataFrame(active)
        df = df[["device_type_name", "project_name", "venue", "location",
                 "default_device_count", "start_date", "end_date"]]
        df.columns = ["Device", "Project", "Venue", "Location", "Count", "Start", "End"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No active deployments today.")

    # Weekly forecast
    st.subheader("Weekly Forecast")
    fc1, fc2 = st.columns(2)
    with fc1:
        forecast_dt = st.selectbox("Device Type", device_types,
                                    format_func=lambda x: x["name"])
    with fc2:
        forecast_weeks = st.slider("Weeks ahead", 4, 52, 12)

    monday = today - timedelta(days=today.weekday())
    end = monday + timedelta(weeks=forecast_weeks)
    forecast = db.get_fleet_usage_by_week(monday, end, forecast_dt["id"])

    if forecast:
        df = pd.DataFrame(forecast)
        df = df[["week_start", "total_in_use", "total_fleet", "under_repair", "available"]]
        df.columns = ["Week", "In Use", "Fleet", "Repair", "Available"]

        def highlight_shortage(row):
            if row["Available"] < 0:
                return ["background-color: #ffcccc"] * len(row)
            elif row["Available"] < row["Fleet"] * 0.1:
                return ["background-color: #fff3cd"] * len(row)
            return [""] * len(row)

        st.dataframe(df.style.apply(highlight_shortage, axis=1),
                      use_container_width=True, hide_index=True)
    else:
        st.info("No deployments scheduled for this device type in the selected period.")


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

if page == "Dashboard":
    render_dashboard()
elif page == "Timeline":
    render_timeline()
elif page == "Projects":
    render_projects()
elif page == "Fleet":
    render_fleet()
