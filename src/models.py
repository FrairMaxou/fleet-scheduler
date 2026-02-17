"""Dataclasses for Fleet Scheduler entities."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class DeviceType:
    id: Optional[int] = None
    name: str = ""
    total_fleet: int = 0
    under_repair: int = 0


@dataclass
class Project:
    id: Optional[int] = None
    name: str = ""
    name_en: str = ""
    client: str = ""
    status: str = "◎"  # ◎ ★ ☆ △
    entity: str = "AGJ"  # AP / AGJ
    notes: str = ""


@dataclass
class Deployment:
    id: Optional[int] = None
    project_id: Optional[int] = None
    venue: str = ""
    location: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    device_type_id: Optional[int] = None
    default_device_count: int = 0
    app_type: str = ""  # App, Kikubi, WebApp, or empty
    notes: str = ""


@dataclass
class WeeklyAllocation:
    id: Optional[int] = None
    deployment_id: Optional[int] = None
    week_start: Optional[date] = None
    device_count: int = 0
