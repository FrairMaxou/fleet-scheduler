"""SQLite database operations for Fleet Scheduler.

Pattern: same as sales-analysis — raw SQL, connections opened/closed per function,
init_db() called on startup with CREATE TABLE IF NOT EXISTS for idempotency.
"""
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "fleet.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS device_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            total_fleet INTEGER NOT NULL DEFAULT 0,
            under_repair INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_en TEXT DEFAULT '',
            client TEXT DEFAULT '',
            status TEXT DEFAULT '◎',
            entity TEXT DEFAULT 'AGJ',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS deployments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            venue TEXT NOT NULL,
            location TEXT DEFAULT '',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            device_type_id INTEGER NOT NULL,
            default_device_count INTEGER NOT NULL DEFAULT 0,
            app_type TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (device_type_id) REFERENCES device_types(id)
        );

        CREATE TABLE IF NOT EXISTS weekly_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deployment_id INTEGER NOT NULL,
            week_start TEXT NOT NULL,
            device_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helper: generate Monday-aligned weeks between two dates
# ---------------------------------------------------------------------------

def _week_mondays(start: date, end: date) -> list[date]:
    """Return list of Mondays covering the period from start to end."""
    # Align to Monday of the start week
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
    rows = conn.execute("SELECT * FROM device_types ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_device_type(device_type_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM device_types WHERE id = ?", (device_type_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_device_type(name: str, total_fleet: int, under_repair: int = 0) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO device_types (name, total_fleet, under_repair) VALUES (?, ?, ?)",
        (name, total_fleet, under_repair)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def update_device_type(device_type_id: int, name: str, total_fleet: int, under_repair: int):
    conn = get_connection()
    conn.execute(
        "UPDATE device_types SET name = ?, total_fleet = ?, under_repair = ? WHERE id = ?",
        (name, total_fleet, under_repair, device_type_id)
    )
    conn.commit()
    conn.close()


def delete_device_type(device_type_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM device_types WHERE id = ?", (device_type_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------

def get_projects() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_project(name: str, name_en: str = "", client: str = "",
                   status: str = "◎", entity: str = "AGJ", notes: str = "") -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO projects (name, name_en, client, status, entity, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (name, name_en, client, status, entity, notes)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def update_project(project_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [project_id]
    conn = get_connection()
    conn.execute(f"UPDATE projects SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def delete_project(project_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Deployments CRUD
# ---------------------------------------------------------------------------

def get_deployments(project_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    if project_id:
        rows = conn.execute(
            """SELECT d.*, p.name as project_name, dt.name as device_type_name
               FROM deployments d
               JOIN projects p ON d.project_id = p.id
               JOIN device_types dt ON d.device_type_id = dt.id
               WHERE d.project_id = ?
               ORDER BY d.start_date""",
            (project_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT d.*, p.name as project_name, dt.name as device_type_name
               FROM deployments d
               JOIN projects p ON d.project_id = p.id
               JOIN device_types dt ON d.device_type_id = dt.id
               ORDER BY d.start_date"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_deployment(project_id: int, venue: str, location: str,
                      start_date: date, end_date: date, device_type_id: int,
                      default_device_count: int, app_type: str = "",
                      notes: str = "") -> int:
    """Create deployment and auto-generate weekly allocations."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO deployments
           (project_id, venue, location, start_date, end_date, device_type_id,
            default_device_count, app_type, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, venue, location, str(start_date), str(end_date),
         device_type_id, default_device_count, app_type, notes)
    )
    deployment_id = cur.lastrowid

    # Auto-generate weekly allocations
    weeks = _week_mondays(start_date, end_date)
    for monday in weeks:
        conn.execute(
            "INSERT INTO weekly_allocations (deployment_id, week_start, device_count) VALUES (?, ?, ?)",
            (deployment_id, str(monday), default_device_count)
        )

    conn.commit()
    conn.close()
    return deployment_id


def update_deployment(deployment_id: int, **kwargs):
    """Update deployment fields. Does NOT regenerate weekly allocations."""
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [deployment_id]
    conn = get_connection()
    conn.execute(f"UPDATE deployments SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def delete_deployment(deployment_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM deployments WHERE id = ?", (deployment_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Weekly Allocations
# ---------------------------------------------------------------------------

def get_weekly_allocations(deployment_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM weekly_allocations WHERE deployment_id = ? ORDER BY week_start",
        (deployment_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_weekly_allocation(allocation_id: int, device_count: int):
    conn = get_connection()
    conn.execute(
        "UPDATE weekly_allocations SET device_count = ? WHERE id = ?",
        (device_count, allocation_id)
    )
    conn.commit()
    conn.close()


def regenerate_weekly_allocations(deployment_id: int, start_date: date,
                                  end_date: date, default_count: int):
    """Delete existing allocations and regenerate from scratch."""
    conn = get_connection()
    conn.execute("DELETE FROM weekly_allocations WHERE deployment_id = ?", (deployment_id,))
    for monday in _week_mondays(start_date, end_date):
        conn.execute(
            "INSERT INTO weekly_allocations (deployment_id, week_start, device_count) VALUES (?, ?, ?)",
            (deployment_id, str(monday), default_count)
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fleet Queries (aggregation)
# ---------------------------------------------------------------------------

def get_fleet_usage_by_week(start_date: date, end_date: date,
                            device_type_id: Optional[int] = None) -> list[dict]:
    """Get total device usage per week per device type for a date range.

    Returns rows with: week_start, device_type_id, device_type_name, total_in_use
    """
    conn = get_connection()
    query = """
        SELECT wa.week_start, dt.id as device_type_id, dt.name as device_type_name,
               dt.total_fleet, dt.under_repair,
               SUM(wa.device_count) as total_in_use
        FROM weekly_allocations wa
        JOIN deployments d ON wa.deployment_id = d.id
        JOIN device_types dt ON d.device_type_id = dt.id
        WHERE wa.week_start >= ? AND wa.week_start <= ?
    """
    params = [str(start_date), str(end_date)]

    if device_type_id:
        query += " AND dt.id = ?"
        params.append(device_type_id)

    query += " GROUP BY wa.week_start, dt.id ORDER BY wa.week_start, dt.name"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["available"] = d["total_fleet"] - d["under_repair"] - d["total_in_use"]
        result.append(d)
    return result


def get_fleet_summary_current_week() -> list[dict]:
    """Get fleet summary for the current week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return get_fleet_usage_by_week(monday, monday)
