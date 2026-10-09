"""VitalRoute Database Engine.

Provides persistent SQLite storage for hospital operational state,
prehospital handshakes, and clinical audit events.
Zero-configuration, reliable local storage conforming to SDG-3 clinical accountability.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.environ.get("VR_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "vitalroute.db"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Hospitals Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hospitals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                beds_available INTEGER NOT NULL,
                icu_beds_available INTEGER NOT NULL,
                active_boarders INTEGER NOT NULL,
                inbound_ambulances INTEGER NOT NULL,
                ct_operational INTEGER NOT NULL,
                specialist_status TEXT NOT NULL,
                specialties_json TEXT NOT NULL,
                last_update_ts REAL NOT NULL
            )
        """)

        # Handshakes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS handshakes (
                id TEXT PRIMARY KEY,
                ambulance_id TEXT NOT NULL,
                hospital_id TEXT NOT NULL,
                eta_min REAL NOT NULL,
                status TEXT NOT NULL,
                created_ts REAL NOT NULL,
                responded_ts REAL,
                constraint_detail TEXT,
                anticipated_esi INTEGER,
                patient_json TEXT NOT NULL
            )
        """)

        # Clinical Audit Trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL
            )
        """)
        conn.commit()


def save_hospital(h: dict[str, Any]) -> None:
    """Persist or update a hospital's state in SQLite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        specialties_str = json.dumps(h.get("specialties", []))
        raw_status = h["specialist_status"]
        status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        if status_val.startswith("SpecialistStatus."):
            status_val = status_val.split(".", 1)[1]

        cursor.execute("""
            INSERT INTO hospitals (
                id, name, latitude, longitude, beds_available, icu_beds_available,
                active_boarders, inbound_ambulances, ct_operational, specialist_status,
                specialties_json, last_update_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                beds_available=excluded.beds_available,
                icu_beds_available=excluded.icu_beds_available,
                active_boarders=excluded.active_boarders,
                inbound_ambulances=excluded.inbound_ambulances,
                ct_operational=excluded.ct_operational,
                specialist_status=excluded.specialist_status,
                specialties_json=excluded.specialties_json,
                last_update_ts=excluded.last_update_ts
        """, (
            h["id"], h["name"], h["latitude"], h["longitude"],
            int(h["beds_available"]), int(h["icu_beds_available"]),
            int(h["active_boarders"]), int(h.get("inbound_ambulances", 0)),
            1 if h["ct_operational"] else 0,
            status_val,
            specialties_str,
            float(h["last_update_ts"])
        ))
        conn.commit()


def load_hospitals() -> dict[str, dict[str, Any]]:
    """Load all persisted hospital states from database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hospitals")
        rows = cursor.fetchall()
        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            raw_spec = str(r["specialist_status"])
            if raw_spec.startswith("SpecialistStatus."):
                raw_spec = raw_spec.split(".", 1)[1]

            result[r["id"]] = {
                "id": r["id"],
                "name": r["name"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "beds_available": r["beds_available"],
                "icu_beds_available": r["icu_beds_available"],
                "active_boarders": r["active_boarders"],
                "inbound_ambulances": r["inbound_ambulances"],
                "ct_operational": bool(r["ct_operational"]),
                "specialist_status": raw_spec,
                "specialties": json.loads(r["specialties_json"]),
                "last_update_ts": r["last_update_ts"],
            }
        return result


def save_handshake(hs_dict: dict[str, Any]) -> None:
    """Record a prehospital emergency handshake in the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        patient_str = json.dumps(hs_dict.get("patient", {}))
        cursor.execute("""
            INSERT OR REPLACE INTO handshakes (
                id, ambulance_id, hospital_id, eta_min, status,
                created_ts, responded_ts, constraint_detail, anticipated_esi, patient_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hs_dict["id"], hs_dict["ambulance_id"], hs_dict["hospital_id"],
            float(hs_dict["eta_min"]), str(hs_dict["status"]),
            float(hs_dict["created_ts"]),
            hs_dict.get("responded_ts"),
            hs_dict.get("constraint_detail"),
            hs_dict.get("anticipated_esi"),
            patient_str
        ))
        conn.commit()


def update_handshake(hs_id: str, status: str, responded_ts: float | None = None,
                     constraint: str | None = None, esi: int | None = None) -> None:
    """Update handshake acknowledgment or diversion status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE handshakes SET
                status = ?,
                responded_ts = COALESCE(?, responded_ts),
                constraint_detail = COALESCE(?, constraint_detail),
                anticipated_esi = COALESCE(?, anticipated_esi)
            WHERE id = ?
        """, (status, responded_ts, constraint, esi, hs_id))
        conn.commit()


def log_audit_event(event_type: str, details: dict[str, Any]) -> None:
    """Record an immutable clinical audit log event."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_events (timestamp, event_type, details_json)
                VALUES (?, ?, ?)
            """, (time.time(), event_type, json.dumps(details)))
            conn.commit()
    except Exception as e:
        # Never crash the main API if audit logging fails
        print(f"[Audit Log Warning]: {e}")


def get_recent_audit_events(limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve recent audit logs for oversight and inspection."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "event_type": r["event_type"],
                "details": json.loads(r["details_json"]),
            }
            for r in rows
        ]


# Ensure tables exist immediately upon import
try:
    init_db()
except Exception as _e:
    pass
