"""In-memory state store: synthetic multi-hospital network + handshakes.

All data is SYNTHETIC (docs/04 section 5 standard) modelled on published
ED queueing distributions. No live patient data is accessed.
"""
from __future__ import annotations

import threading
import time

from .models import Handshake, SpecialistStatus

_lock = threading.Lock()

# Synthetic network: 5 hospitals around a mid-size city centre (28.6129, 77.2295).
HOSPITALS: dict[str, dict] = {
    "H1": {
        "id": "H1", "name": "Apollo Trauma Centre",
        "latitude": 28.6280, "longitude": 77.2190,
        "beds_available": 4, "icu_beds_available": 1,
        "active_boarders": 2, "inbound_ambulances": 1,
        "ct_operational": True, "specialist_status": SpecialistStatus.ACTIVE,
        "specialties": ["Trauma", "Cath Lab", "ICU", "Surgery", "Burns", "General", "Respiratory"],
        "last_update_ts": time.time() - 180,   # 3 min stale
    },
    "H2": {
        "id": "H2", "name": "Max Institute of Cardiac Sciences",
        "latitude": 28.5686, "longitude": 77.2781,
        "beds_available": 6, "icu_beds_available": 2,
        "active_boarders": 7, "inbound_ambulances": 2,
        "ct_operational": True, "specialist_status": SpecialistStatus.ACTIVE,
        "specialties": ["Cath Lab", "Cardiology", "ICU", "Surgery", "General", "Respiratory"],
        "last_update_ts": time.time() - 240,   # 4 min stale
    },
    "H3": {
        "id": "H3", "name": "AIIMS Metro General",
        "latitude": 28.5672, "longitude": 77.2100,
        "beds_available": 3, "icu_beds_available": 0,
        "active_boarders": 4, "inbound_ambulances": 0,
        "ct_operational": True, "specialist_status": SpecialistStatus.ON_CALL,
        "specialties": ["General", "Trauma", "Pediatrics", "Obstetrics", "Toxicology"],
        "last_update_ts": time.time() - 2280,  # 38 min stale -> "phantom bed" scenario
    },
    "H4": {
        "id": "H4", "name": "Sir Ganga Ram Neuro Sciences",
        "latitude": 28.6418, "longitude": 77.1900,
        "beds_available": 5, "icu_beds_available": 2,
        "active_boarders": 1, "inbound_ambulances": 1,
        "ct_operational": True, "specialist_status": SpecialistStatus.ACTIVE,
        "specialties": ["Neurology", "CT Scanner", "Stroke", "Neurosurgery", "ICU", "General"],
        "last_update_ts": time.time() - 60,
    },
    "H5": {
        "id": "H5", "name": "Lok Nayak Emergency",
        "latitude": 28.6430, "longitude": 77.2410,
        "beds_available": 2, "icu_beds_available": 1,
        "active_boarders": 9, "inbound_ambulances": 3,
        "ct_operational": True, "specialist_status": SpecialistStatus.UNAVAILABLE,
        "specialties": ["General", "Pediatrics", "Trauma", "Toxicology", "Obstetrics"],
        "last_update_ts": time.time() - 900,   # 15 min stale
    },
}

HANDSHAKES: dict[str, Handshake] = {}   # handshake_id -> Handshake
AMBULANCES: dict[str, dict] = {}        # ambulance_id -> {lat, lon, ...}


def get_hospitals() -> dict[str, dict]:
    with _lock:
        return {k: dict(v) for k, v in HOSPITALS.items()}


def update_hospital(hospital_id: str, **fields) -> dict:
    with _lock:
        h = HOSPITALS[hospital_id]
        if "specialist_status" in fields and fields["specialist_status"] is not None:
            val = fields["specialist_status"]
            if isinstance(val, str):
                fields["specialist_status"] = SpecialistStatus(val)
        h.update({k: val for k, val in fields.items() if val is not None})
        if fields.get("refresh_timestamp"):
            h["last_update_ts"] = time.time()
        return dict(h)



def add_handshake(hs: Handshake) -> None:
    with _lock:
        HANDSHAKES[hs.id] = hs


def get_handshake(hs_id: str) -> Handshake | None:
    with _lock:
        return HANDSHAKES.get(hs_id)


def all_handshakes() -> list[Handshake]:
    with _lock:
        return list(HANDSHAKES.values())
