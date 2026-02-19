"""Fleet Scheduler — Device Deployment Planning Tool for Acoustiguide Japan."""
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import date, timedelta
from src import database as db
from src.charts import build_timeline_chart, build_capacity_chart
from src.i18n import get_translations

st.set_page_config(page_title="Fleet Scheduler", layout="wide")

# ---------------------------------------------------------------------------
# Language toggle (visible on login page too)
# ---------------------------------------------------------------------------

lang_option = st.sidebar.radio(
    "Language / 言語",
    ["EN", "日本語"],
    horizontal=True,
)
T = get_translations("ja" if lang_option == "日本語" else "en")

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
    st.error(T["auth_error"])
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.stop()

authenticator.logout(T["auth_logout"], "sidebar")
st.sidebar.caption(f"{T['auth_logged_in']} {st.session_state['name']}")

# ---------------------------------------------------------------------------
# App init (only reached when authenticated)
# ---------------------------------------------------------------------------

db.init_db()

STATUS_OPTIONS = ["◎", "★", "☆", "△"]

# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------

NAV_KEYS = ["Dashboard", "Timeline", "Projects", "Fleet"]
NAV_T_MAP = {
    "Dashboard": "nav_dashboard",
    "Timeline": "nav_timeline",
    "Projects": "nav_projects",
    "Fleet": "nav_fleet",
}

page = st.sidebar.radio(
    T["nav_label"],
    NAV_KEYS,
    format_func=lambda x: T[NAV_T_MAP[x]],
)

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def render_dashboard(T: dict):
    st.title(T["page_dashboard"])

    device_types = db.get_device_types()
    if not device_types:
        st.info(T["dash_no_device_types"])
        return

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    current_usage = db.get_fleet_usage_by_week(monday, monday)
    usage_map = {r["device_type_id"]: r for r in current_usage}

    # Fleet summary cards
    st.subheader(T["dash_current_week"])
    cols = st.columns(len(device_types))
    for i, dt in enumerate(device_types):
        with cols[i]:
            usage = usage_map.get(dt["id"])
            in_use = usage["total_in_use"] if usage else 0
            available = dt["total_fleet"] - dt["under_repair"] - in_use
            st.metric(
                dt["name"],
                f"{available} {T['dash_available']}",
                delta=f"{in_use} {T['dash_in_use']} / {dt['under_repair']} {T['dash_repair']}",
                delta_color="off",
            )

    # Shortage alerts — next 12 weeks
    st.subheader(T["dash_shortage_alerts"])
    end_check = monday + timedelta(weeks=12)
    future_usage = db.get_fleet_usage_by_week(monday, end_check)

    alerts = [r for r in future_usage if r["available"] < 0]
    warnings = [r for r in future_usage if 0 <= r["available"] < r["total_fleet"] * 0.1]

    if alerts:
        for a in alerts:
            st.error(
                f"**{T['dash_shortage_prefix']}** — {a['device_type_name']}: "
                f"{T['dash_week_of']} {a['week_start']} — {T['dash_need']} {a['total_in_use']}, "
                f"{T['dash_available_count']} {a['total_fleet'] - a['under_repair']} "
                f"({T['dash_deficit']}: {abs(a['available'])})"
            )
    if warnings:
        for w in warnings:
            st.warning(
                f"**{T['dash_low_stock_prefix']}** — {w['device_type_name']}: "
                f"{T['dash_week_of']} {w['week_start']} — {w['available']} {T['dash_units_remaining']} "
                f"({w['total_in_use']} {T['dash_in_use']})"
            )
    if not alerts and not warnings:
        st.success(T["dash_no_shortages"])

    # Next 4 weeks table
    st.subheader(T["dash_next_4_weeks"])
    next_4 = db.get_fleet_usage_by_week(monday, monday + timedelta(weeks=3))
    if next_4:
        df = pd.DataFrame(next_4)
        df = df[["week_start", "device_type_name", "total_in_use", "total_fleet", "under_repair", "available"]]
        df.columns = [
            T["dash_col_week"], T["dash_col_device"], T["dash_col_in_use"],
            T["dash_col_fleet_total"], T["dash_col_under_repair"], T["dash_col_available"],
        ]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(T["dash_no_deployments_4w"])


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

PERIOD_KEYS = ["3 months", "6 months", "12 months", "Custom"]
PERIOD_T_MAP = {
    "3 months": "tl_3m",
    "6 months": "tl_6m",
    "12 months": "tl_12m",
    "Custom": "tl_custom",
}


def render_timeline(T: dict):
    st.title(T["page_timeline"])

    device_types = db.get_device_types()

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        period = st.selectbox(
            T["tl_period"],
            PERIOD_KEYS,
            format_func=lambda x: T[PERIOD_T_MAP[x]],
        )
    with col2:
        if period == "Custom":
            start_range = st.date_input(T["tl_start"], value=date.today())
        else:
            start_range = date.today()
    with col3:
        if period == "Custom":
            end_range = st.date_input(T["tl_end"], value=date.today() + timedelta(days=180))
        elif period == "3 months":
            end_range = date.today() + timedelta(days=90)
        elif period == "12 months":
            end_range = date.today() + timedelta(days=365)
        else:
            end_range = date.today() + timedelta(days=180)
    with col4:
        dt_names = ["All"] + [dt["name"] for dt in device_types]
        device_filter = st.selectbox(
            T["tl_device_type"],
            dt_names,
            format_func=lambda x: T["tl_all"] if x == "All" else x,
        )

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.multiselect(T["tl_status"], STATUS_OPTIONS, default=STATUS_OPTIONS)
    with filter_col2:
        search = st.text_input(T["tl_search"], "")

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
                "color": dep.get("device_type_color", "#72B7B2"),
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
    fig = build_timeline_chart(rows, start_range, end_range, T)
    st.plotly_chart(fig, use_container_width=True)

    # Capacity chart
    dt_id = None
    if device_filter != "All":
        dt_id = next((dt["id"] for dt in device_types if dt["name"] == device_filter), None)

    monday = start_range - timedelta(days=start_range.weekday())
    usage_data = db.get_fleet_usage_by_week(monday, end_range, dt_id)
    cap_fig = build_capacity_chart(usage_data, device_types, start_range, end_range, T)
    st.plotly_chart(cap_fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def render_projects(T: dict):
    st.title(T["page_projects"])

    STATUS_LABELS = {
        "◎": T["status_confirmed"],
        "★": T["status_must_win"],
        "☆": T["status_nice"],
        "△": T["status_conditional"],
    }

    device_types = db.get_device_types()
    if not device_types:
        st.warning(T["proj_no_device_types"])
        return

    dt_map = {dt["id"]: dt["name"] for dt in device_types}
    dt_name_to_id = {dt["name"]: dt["id"] for dt in device_types}

    # --- Add new project ---
    if "show_add_project" not in st.session_state:
        st.session_state.show_add_project = False

    if st.button(T["proj_new_btn"], type="primary"):
        st.session_state.show_add_project = not st.session_state.show_add_project

    if st.session_state.show_add_project:
        with st.container(border=True):
            st.markdown(T["proj_new_title"])
            with st.form("new_project", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    p_name = st.text_input(T["proj_name_jp"])
                    p_client = st.text_input(T["proj_client"])
                with col2:
                    p_name_en = st.text_input(T["proj_name_en"])
                    p_status = st.selectbox(T["proj_status"], STATUS_OPTIONS,
                                            format_func=lambda x: STATUS_LABELS[x])
                p_notes = st.text_input(T["proj_notes"])

                c1, c2 = st.columns([3, 1])
                with c1:
                    submitted = st.form_submit_button(T["proj_create_btn"], type="primary")
                with c2:
                    cancelled = st.form_submit_button(T["proj_cancel_btn"])

                if submitted:
                    if p_name:
                        db.create_project(name=p_name, name_en=p_name_en, client=p_client,
                                          status=p_status, notes=p_notes)
                        st.session_state.show_add_project = False
                        st.rerun()
                    else:
                        st.error(T["proj_name_required"])
                if cancelled:
                    st.session_state.show_add_project = False
                    st.rerun()

    st.divider()

    # --- Filters ---
    show_archived = st.checkbox(T["proj_show_archived"])
    all_deployments = db.get_deployments(include_archived=show_archived)
    venues_by_project = {}
    for dep in all_deployments:
        venues_by_project.setdefault(dep["project_id"], []).append(
            f"{dep['venue']} {dep.get('location', '')}".lower()
        )

    fcol1, fcol2 = st.columns([3, 2])
    with fcol1:
        search = st.text_input(
            "Search",
            placeholder=T["proj_search_placeholder"],
            label_visibility="collapsed",
        )
    with fcol2:
        status_filter = st.multiselect(
            T["proj_status"],
            STATUS_OPTIONS,
            default=STATUS_OPTIONS,
            format_func=lambda x: STATUS_LABELS[x],
            label_visibility="collapsed",
        )

    # --- Load all data upfront (single queries, cached) ---
    projects = db.get_projects(include_archived=show_archived)
    all_allocations = db.get_all_weekly_allocations()

    if not projects:
        st.info(T["proj_none"])
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
        st.info(T["proj_no_match"])
        return

    for proj in filtered_projects:
        status_label = STATUS_LABELS.get(proj["status"], proj["status"])
        archived_tag = f" {T['proj_archived_label']}" if proj.get("archived") else ""
        with st.expander(f"{proj['status']} {proj['name']} — {proj['client']} ({status_label}){archived_tag}"):
            # Edit project
            with st.form(f"edit_proj_{proj['id']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    ed_name = st.text_input(T["proj_name"], proj["name"], key=f"pn_{proj['id']}")
                    ed_client = st.text_input(T["proj_client"], proj["client"], key=f"pc_{proj['id']}")
                with col2:
                    ed_name_en = st.text_input(T["proj_name_en_label"], proj["name_en"], key=f"pe_{proj['id']}")
                    ed_status = st.selectbox(
                        T["proj_status"],
                        STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(proj["status"]),
                        format_func=lambda x: STATUS_LABELS[x],
                        key=f"ps_{proj['id']}",
                    )
                with col3:
                    ed_notes = st.text_input(T["proj_notes"], proj["notes"], key=f"pno_{proj['id']}")

                if proj.get("archived"):
                    c1, c2, c3 = st.columns([3, 1, 1])
                else:
                    c1, c2 = st.columns([3, 1])
                with c1:
                    if st.form_submit_button(T["proj_update_btn"]):
                        db.update_project(proj["id"], name=ed_name, name_en=ed_name_en,
                                          client=ed_client, status=ed_status, notes=ed_notes)
                        st.success(T["proj_updated"])
                        st.rerun()
                if proj.get("archived"):
                    with c2:
                        if st.form_submit_button(T["proj_unarchive_btn"]):
                            db.unarchive_project(proj["id"])
                            st.rerun()
                    with c3:
                        if st.form_submit_button(T["proj_delete_btn"], type="secondary"):
                            db.delete_project(proj["id"])
                            st.success(T["proj_deleted"])
                            st.rerun()
                else:
                    with c2:
                        if st.form_submit_button(T["proj_archive_btn"], type="secondary"):
                            db.archive_project(proj["id"])
                            st.rerun()

            # Deployments for this project
            st.markdown(T["proj_deployments"])
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
                        if st.button(T["proj_dep_delete_btn"], key=f"del_dep_{dep['id']}"):
                            db.delete_deployment(dep["id"])
                            st.rerun()

                    # Weekly allocations editor
                    allocations = all_allocations.get(dep["id"], [])
                    if allocations:
                        alloc_df = pd.DataFrame(allocations)
                        alloc_df["week_start"] = pd.to_datetime(alloc_df["week_start"]).dt.strftime("%Y-%m-%d")
                        edited = st.data_editor(
                            alloc_df[["id", "week_start", "device_count"]],
                            column_config={
                                "id": st.column_config.NumberColumn(T["proj_alloc_id"], disabled=True),
                                "week_start": st.column_config.TextColumn(T["proj_alloc_week"], disabled=True),
                                "device_count": st.column_config.NumberColumn(T["proj_alloc_devices"], min_value=0),
                            },
                            hide_index=True,
                            key=f"alloc_{dep['id']}",
                            use_container_width=True,
                        )
                        if st.button(T["proj_save_alloc_btn"], key=f"save_alloc_{dep['id']}"):
                            for _, row in edited.iterrows():
                                db.update_weekly_allocation(int(row["id"]), int(row["device_count"]))
                            st.success(T["proj_alloc_saved"])
                            st.rerun()

                    # Bulk apply from date
                    with st.form(f"bulk_{dep['id']}"):
                        st.caption(T["proj_bulk_caption"])
                        ba1, ba2, ba3 = st.columns([2, 2, 1])
                        with ba1:
                            bulk_count = st.number_input(
                                T["proj_bulk_count"],
                                min_value=0,
                                value=dep["default_device_count"],
                                key=f"bc_{dep['id']}",
                            )
                        with ba2:
                            bulk_from = st.date_input(
                                T["proj_bulk_from"],
                                value=date.today(),
                                key=f"bf_{dep['id']}",
                            )
                        with ba3:
                            st.write("")
                            apply = st.form_submit_button(T["proj_bulk_apply"])
                        if apply:
                            db.bulk_update_allocations_from(dep["id"], bulk_count, bulk_from)
                            st.success(f"{T['proj_bulk_apply']}: {bulk_count} — {bulk_from}")
                            st.rerun()
            else:
                st.caption(T["proj_no_deps"])

            # Add deployment
            with st.form(f"new_dep_{proj['id']}"):
                st.markdown(T["proj_add_dep_title"])
                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    d_venue = st.text_input(T["proj_dep_venue"], key=f"dv_{proj['id']}")
                    d_location = st.text_input(T["proj_dep_location"], key=f"dl_{proj['id']}")
                with dc2:
                    d_start = st.date_input(T["proj_dep_start"], key=f"ds_{proj['id']}")
                    d_end = st.date_input(T["proj_dep_end"], key=f"de_{proj['id']}")
                with dc3:
                    d_device_type = st.selectbox(T["proj_dep_device_type"], list(dt_name_to_id.keys()),
                                                  key=f"ddt_{proj['id']}")
                    d_count = st.number_input(T["proj_dep_count"], min_value=0, value=0,
                                              key=f"dc_{proj['id']}")
                d_app = st.selectbox(T["proj_dep_app"], ["", "App", "Kikubi", "WebApp"],
                                     key=f"da_{proj['id']}")

                if st.form_submit_button(T["proj_dep_add_btn"]):
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
                        st.success(f"{T['proj_dep_added']}: {d_venue}")
                        st.rerun()
                    else:
                        st.error(T["proj_dep_fill_error"])


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------

def render_fleet(T: dict):
    st.title(T["page_fleet"])

    # Add device type
    with st.expander(T["fleet_add_expander"], expanded=False):
        with st.form("new_device_type"):
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            with col1:
                dt_name = st.text_input(T["fleet_dt_name"])
            with col2:
                dt_total = st.number_input(T["fleet_dt_total"], min_value=0, value=0)
            with col3:
                dt_repair = st.number_input(T["fleet_dt_repair"], min_value=0, value=0)
            with col4:
                dt_color = st.color_picker(T["fleet_dt_color"], value="#4C78A8")

            if st.form_submit_button(T["fleet_dt_add_btn"]):
                if dt_name:
                    try:
                        db.create_device_type(dt_name, dt_total, dt_repair, dt_color)
                        st.success(f"{T['fleet_dt_added']}: {dt_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"{T['fleet_dt_error']}: {e}")
                else:
                    st.error(T["fleet_dt_name_required"])

    # List and edit device types
    device_types = db.get_device_types()
    if not device_types:
        st.info(T["fleet_no_dt"])
        return

    st.subheader(T["fleet_dt_title"])
    for dt in device_types:
        with st.form(f"edit_dt_{dt['id']}"):
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
            with col1:
                ed_name = st.text_input(T["fleet_dt_name_label"], dt["name"], key=f"dtn_{dt['id']}")
            with col2:
                ed_total = st.number_input(T["fleet_dt_total"], value=dt["total_fleet"],
                                           min_value=0, key=f"dtt_{dt['id']}")
            with col3:
                ed_repair = st.number_input(T["fleet_dt_repair"], value=dt["under_repair"],
                                            min_value=0, key=f"dtr_{dt['id']}")
            with col4:
                ed_color = st.color_picker(T["fleet_dt_color"], value=dt.get("color", "#4C78A8"),
                                           key=f"dtc_{dt['id']}")
            with col5:
                st.write("")
                save = st.form_submit_button(T["fleet_dt_save_btn"])

            if save:
                db.update_device_type(dt["id"], ed_name, ed_total, ed_repair, ed_color)
                st.success(f"{T['fleet_dt_updated']}: {ed_name}")
                st.rerun()

    # Where are devices now
    st.subheader(T["fleet_current_deps"])
    today = date.today()
    all_deps = db.get_deployments()
    active = [d for d in all_deps
              if date.fromisoformat(d["start_date"]) <= today <= date.fromisoformat(d["end_date"])]

    if active:
        df = pd.DataFrame(active)
        df = df[["device_type_name", "project_name", "venue", "location",
                 "default_device_count", "start_date", "end_date"]]
        df.columns = [
            T["fleet_col_device"], T["fleet_col_project"], T["fleet_col_venue"],
            T["fleet_col_location"], T["fleet_col_count"], T["fleet_col_start"], T["fleet_col_end"],
        ]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(T["fleet_no_active"])

    # Weekly forecast
    st.subheader(T["fleet_forecast"])
    fc1, fc2 = st.columns(2)
    with fc1:
        forecast_dt = st.selectbox(T["fleet_forecast_dt"], device_types,
                                    format_func=lambda x: x["name"])
    with fc2:
        forecast_weeks = st.slider(T["fleet_forecast_weeks"], 4, 52, 12)

    monday = today - timedelta(days=today.weekday())
    end = monday + timedelta(weeks=forecast_weeks)
    forecast = db.get_fleet_usage_by_week(monday, end, forecast_dt["id"])

    col_available = T["fleet_col_available"]
    col_fleet = T["fleet_col_fleet"]

    if forecast:
        df = pd.DataFrame(forecast)
        df = df[["week_start", "total_in_use", "total_fleet", "under_repair", "available"]]
        df.columns = [
            T["fleet_col_week"], T["fleet_col_in_use"], col_fleet,
            T["fleet_col_repair"], col_available,
        ]

        def highlight_shortage(row):
            if row[col_available] < 0:
                return ["background-color: #ffcccc"] * len(row)
            elif row[col_available] < row[col_fleet] * 0.1:
                return ["background-color: #fff3cd"] * len(row)
            return [""] * len(row)

        st.dataframe(df.style.apply(highlight_shortage, axis=1),
                      use_container_width=True, hide_index=True)
    else:
        st.info(T["fleet_no_forecast"])


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

if page == "Dashboard":
    render_dashboard(T)
elif page == "Timeline":
    render_timeline(T)
elif page == "Projects":
    render_projects(T)
elif page == "Fleet":
    render_fleet(T)
