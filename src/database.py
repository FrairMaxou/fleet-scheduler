"""PostgreSQL database operations for Fleet Scheduler (Supabase).

Connection string read from st.secrets["database"]["url"].
Uses psycopg2 with RealDictCursor so all rows come back as plain dicts —
same interface as the previous sqlite3 version.
"""
import psycopg2
import psycopg2.extras
import streamlit as st
from datetime import date, timedelta
from typing import Optional


def get_connection() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(st.secrets["database"]["url"])
    return conn


def _cur(conn) -> psycopg2.extras.RealDictCursor:
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_types (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            total_fleet INTEGER NOT NULL DEFAULT 0,
            under_repair INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            name_en TEXT DEFAULT '',
            client TEXT DEFAULT '',
            status TEXT DEFAULT '◎',
            entity TEXT DEFAULT 'AGJ',
            notes TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deployments (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            venue TEXT NOT NULL,
            location TEXT DEFAULT '',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            device_type_id INTEGER NOT NULL REFERENCES device_types(id),
            default_device_count INTEGER NOT NULL DEFAULT 0,
            app_type TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_allocations (
            id SERIAL PRIMARY KEY,
            deployment_id INTEGER NOT NULL REFERENCES deployments(id) ON DELETE CASCADE,
            week_start TEXT NOT NULL,
            device_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Helper: generate Monday-aligned weeks between two dates
# ---------------------------------------------------------------------------

def _week_mondays(start: date, end: date) -> list[date]:
    monday = start - timedelta(days=start.weekday())
    weeks = []
    while monday <= end:
        weeks.append(monday)
        monday += timedelta(days=7)
    return weeks


# ---------------------------------------------------------------------------
# Device Types CRUD
# ---------------------------------------------------------------------------

def get_device_types() -> list[dict]:
    conn = get_connection()
    cur = _cur(conn)
    cur.execute("SELECT * FROM device_types ORDER BY name")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_device_type(device_type_id: int) -> Optional[dict]:
    conn = get_connection()
    cur = _cur(conn)
    cur.execute("SELECT * FROM device_types WHERE id = %s", (device_type_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def create_device_type(name: str, total_fleet: int, under_repair: int = 0) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO device_types (name, total_fleet, under_repair) VALUES (%s, %s, %s) RETURNING id",
        (name, total_fleet, under_repair)
    )
    row_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return row_id


def update_device_type(device_type_id: int, name: str, total_fleet: int, under_repair: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE device_types SET name = %s, total_fleet = %s, under_repair = %s WHERE id = %s",
        (name, total_fleet, under_repair, device_type_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_device_type(device_type_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM device_types WHERE id = %s", (device_type_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------

def get_projects() -> list[dict]:
    conn = get_connection()
    cur = _cur(conn)
    cur.execute("SELECT * FROM projects ORDER BY name")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> Optional[dict]:
    conn = get_connection()
    cur = _cur(conn)
    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def create_project(name: str, name_en: str = "", client: str = "",
                   status: str = "◎", entity: str = "AGJ", notes: str = "") -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO projects (name, name_en, client, status, entity, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (name, name_en, client, status, entity, notes)
    )
    row_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return row_id


def update_project(project_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = %s" for k in kwargs)
    vals = list(kwargs.values()) + [project_id]
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE projects SET {sets} WHERE id = %s", vals)
    conn.commit()
    cur.close()
    conn.close()


def delete_project(project_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Deployments CRUD
# ---------------------------------------------------------------------------

def get_deployments(project_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    cur = _cur(conn)
    if project_id:
        cur.execute(
            """SELECT d.*, p.name as project_name, dt.name as device_type_name
               FROM deployments d
               JOIN projects p ON d.project_id = p.id
               JOIN device_types dt ON d.device_type_id = dt.id
               WHERE d.project_id = %s
               ORDER BY d.start_date""",
            (project_id,)
        )
    else:
        cur.execute(
            """SELECT d.*, p.name as project_name, dt.name as device_type_name
               FROM deployments d
               JOIN projects p ON d.project_id = p.id
               JOIN device_types dt ON d.device_type_id = dt.id
               ORDER BY d.start_date"""
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def create_deployment(project_id: int, venue: str, location: str,
                      start_date: date, end_date: date, device_type_id: int,
                      default_device_count: int, app_type: str = "",
                      notes: str = "") -> int:
    """Create deployment and auto-generate weekly allocations."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO deployments
           (project_id, venue, location, start_date, end_date, device_type_id,
            default_device_count, app_type, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (project_id, venue, location, str(start_date), str(end_date),
         device_type_id, default_device_count, app_type, notes)
    )
    deployment_id = cur.fetchone()[0]

    for monday in _week_mondays(start_date, end_date):
        cur.execute(
            "INSERT INTO weekly_allocations (deployment_id, week_start, device_count) VALUES (%s, %s, %s)",
            (deployment_id, str(monday), default_device_count)
        )

    conn.commit()
    cur.close()
    conn.close()
    return deployment_id


def update_deployment(deployment_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = %s" for k in kwargs)
    vals = list(kwargs.values()) + [deployment_id]
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE deployments SET {sets} WHERE id = %s", vals)
    conn.commit()
    cur.close()
    conn.close()


def delete_deployment(deployment_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM deployments WHERE id = %s", (deployment_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Weekly Allocations
# ---------------------------------------------------------------------------

def get_weekly_allocations(deployment_id: int) -> list[dict]:
    conn = get_connection()
    cur = _cur(conn)
    cur.execute(
        "SELECT * FROM weekly_allocations WHERE deployment_id = %s ORDER BY week_start",
        (deployment_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def update_weekly_allocation(allocation_id: int, device_count: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE weekly_allocations SET device_count = %s WHERE id = %s",
        (device_count, allocation_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def regenerate_weekly_allocations(deployment_id: int, start_date: date,
                                  end_date: date, default_count: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM weekly_allocations WHERE deployment_id = %s", (deployment_id,))
    for monday in _week_mondays(start_date, end_date):
        cur.execute(
            "INSERT INTO weekly_allocations (deployment_id, week_start, device_count) VALUES (%s, %s, %s)",
            (deployment_id, str(monday), default_count)
        )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Fleet Queries (aggregation)
# ---------------------------------------------------------------------------

def get_fleet_usage_by_week(start_date: date, end_date: date,
                            device_type_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    cur = _cur(conn)
    query = """
        SELECT wa.week_start, dt.id as device_type_id, dt.name as device_type_name,
               dt.total_fleet, dt.under_repair,
               SUM(wa.device_count) as total_in_use
        FROM weekly_allocations wa
        JOIN deployments d ON wa.deployment_id = d.id
        JOIN device_types dt ON d.device_type_id = dt.id
        WHERE wa.week_start >= %s AND wa.week_start <= %s
    """
    params: list = [str(start_date), str(end_date)]

    if device_type_id:
        query += " AND dt.id = %s"
        params.append(device_type_id)

    query += " GROUP BY wa.week_start, dt.id, dt.name, dt.total_fleet, dt.under_repair ORDER BY wa.week_start, dt.name"

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["available"] = d["total_fleet"] - d["under_repair"] - d["total_in_use"]
        result.append(d)
    return result


def get_fleet_summary_current_week() -> list[dict]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return get_fleet_usage_by_week(monday, monday)
