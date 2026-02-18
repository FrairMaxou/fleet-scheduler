-- Fleet Scheduler — Supabase schema
-- Run this once in the Supabase SQL editor (Database > SQL Editor > New query)

CREATE TABLE IF NOT EXISTS device_types (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    total_fleet INTEGER NOT NULL DEFAULT 0,
    under_repair INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    name_en TEXT DEFAULT '',
    client TEXT DEFAULT '',
    status TEXT DEFAULT '◎',
    entity TEXT DEFAULT 'AGJ',
    notes TEXT DEFAULT ''
);

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
);

CREATE TABLE IF NOT EXISTS weekly_allocations (
    id SERIAL PRIMARY KEY,
    deployment_id INTEGER NOT NULL REFERENCES deployments(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    device_count INTEGER NOT NULL DEFAULT 0
);
