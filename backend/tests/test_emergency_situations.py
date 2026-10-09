"""Tests for predefined and manually-typed emergency situations in VitalRoute."""
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models import CareTag
from app.services import clinical, ttdc


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_custom_emergency_description_in_assessment(client):
    payload = {
        "ambulance_id": "AMB-TEST-1",
        "latitude": 28.6200,
        "longitude": 77.2100,
        "vitals": {
            "respiration_rate": 26,
            "spo2": 90,
            "systolic_bp": 95,
            "heart_rate": 125,
            "consciousness": "V",
            "temperature": 37.0
        },
        "care_tag": "TRAUMA",
        "emergency_description": "Driver ejected in high-speed rollover. Severe paradoxical chest wall movement, active scalp laceration.",
        "custom_requirements": ["Trauma", "ICU"],
        "paramedic_notes": "C-spine secured, 15L O2 via non-rebreather mask, bilateral large-bore IVs placed."
    }
    res = client.post("/api/assessments", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["care_tag"] == "TRAUMA"
    assert "Driver ejected" in data["emergency_description"]
    assert "Trauma" in data["custom_requirements"]
    assert "C-spine secured" in data["paramedic_notes"]
    assert data["news2"] >= 7
    assert data["news2_risk_band"] == "HIGH"
    assert len(data["rankings"]) > 0


def test_manually_typed_situation_in_handshake(client):
    payload = {
        "ambulance_id": "AMB-TEST-2",
        "latitude": 28.6250,
        "longitude": 77.2150,
        "vitals": {
            "respiration_rate": 18,
            "spo2": 98,
            "systolic_bp": 120,
            "heart_rate": 80,
            "consciousness": "A",
            "temperature": 36.8
        },
        "care_tag": "CUSTOM",
        "emergency_description": "Industrial ammonia gas leak exposure; severe chemical ocular burning and bronchospasm.",
        "custom_requirements": ["Toxicology"],
        "paramedic_notes": "Copious eye irrigation initiated with 2L normal saline."
    }
    # Request handshake with H3 (AIIMS Metro General has Toxicology)
    res = client.post("/api/handshake?hospital_id=H3", json=payload)
    assert res.status_code == 201
    hs = res.json()
    assert hs["hospital_id"] == "H3"
    assert hs["patient"]["care_tag"] == "CUSTOM"
    assert "ammonia gas leak" in hs["patient"]["emergency_description"]
    assert hs["patient"]["custom_requirements"] == ["Toxicology"]
    assert "Copious eye irrigation" in hs["patient"]["paramedic_notes"]

    # Hospital queries its handshakes
    res_list = client.get("/api/handshakes/hospital/H3")
    assert res_list.status_code == 200
    h_handshakes = res_list.json()
    assert any(h["id"] == hs["id"] for h in h_handshakes)

    # Hospital triage nurse acknowledges and assigns anticipated ESI 2
    ack = client.post(f"/api/handshake/{hs['id']}/ack", params={"confirm": True, "anticipated_esi": 2})
    assert ack.status_code == 200
    assert ack.json()["status"] == "CONFIRMED"
    assert ack.json()["anticipated_esi"] == 2


def test_suggested_esi_with_emergency_keywords():
    # Normal vitals (NEWS2 = 0), but critical description indicating cardiac arrest
    score = 0
    esi = clinical.suggested_esi(score, "GENERAL", emergency_description="Patient in cardiac arrest, CPR in progress")
    assert esi == 1

    # High-risk keyword: severe hemorrhage
    esi_high = clinical.suggested_esi(score, "GENERAL", emergency_description="Active arterial hemorrhage from femoral wound")
    assert esi_high == 2

    # High acuity tag
    assert clinical.suggested_esi(5, "STEMI") == 1
    assert clinical.suggested_esi(2, "BURNS") == 2


def test_custom_requirements_filtering():
    hospitals = {
        "H_GEN": {
            "id": "H_GEN", "name": "General Clinic",
            "latitude": 28.60, "longitude": 77.20,
            "beds_available": 10, "icu_beds_available": 0,
            "active_boarders": 0, "inbound_ambulances": 0,
            "ct_operational": False, "specialist_status": "ACTIVE",
            "specialties": ["General", "Outpatient"],
            "last_update_ts": 1000.0,
        },
        "H_BURN": {
            "id": "H_BURN", "name": "Super Burn Centre",
            "latitude": 28.61, "longitude": 77.21,
            "beds_available": 5, "icu_beds_available": 2,
            "active_boarders": 0, "inbound_ambulances": 0,
            "ct_operational": True, "specialist_status": "ACTIVE",
            "specialties": ["Burn Unit", "ICU", "Surgery"],
            "last_update_ts": 1000.0,
        }
    }
    # Search with requirement ["Burn Unit"]
    ranked, rationale = ttdc.rank_hospitals(
        hospitals, 28.605, 77.205, CareTag.GENERAL, now=1000.0,
        custom_requirements=["Burn Unit"]
    )
    eligible = [r for r in ranked if r.eligible]
    ineligible = [r for r in ranked if not r.eligible]

    assert len(eligible) == 1
    assert eligible[0].hospital.id == "H_BURN"
    assert len(ineligible) == 1
    assert ineligible[0].hospital.id == "H_GEN"
    assert "Missing requested clinical resource" in (ineligible[0].ineligibility_reason or "")
