"""Tests for Offline Probability-Based Hospital Capacity Forecasting in VitalRoute."""
import time
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models import CareTag
from app.services import confidence, ttdc


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_forecast_capacity_probability_live_fresh():
    now = 1700000000.0  # reference epoch
    res = confidence.forecast_capacity_probability(
        reported_beds=8,
        last_update_ts=now - 60,  # 1 min ago
        travel_time_min=12.0,
        now=now,
        is_offline=False,
        is_icu=False,
    )
    assert res["forecast_mode"] == "LIVE"
    assert res["probability"] >= 0.85
    assert res["confidence_band"] == "VERIFIED_LIVE"
    assert "Live telemetry" in res["disclaimer"]


def test_forecast_capacity_probability_stale_and_offline():
    now = 1700000000.0
    # 2 hours stale
    stale_ts = now - 7200

    res = confidence.forecast_capacity_probability(
        reported_beds=2,
        last_update_ts=stale_ts,
        travel_time_min=25.0,
        now=now,
        is_offline=True,
        is_icu=False,
    )
    assert res["forecast_mode"] == "OFFLINE_PROBABILISTIC"
    assert 0.0 <= res["probability"] <= 1.0
    assert res["confidence_band"] in ("MODERATE", "LOW")
    assert "Unconfirmed estimate" in res["disclaimer"]


def test_forecast_capacity_probability_icu_sensitivity():
    now = 1700000000.0
    # 0 reported ICU beds should yield very low probability
    res_zero = confidence.forecast_capacity_probability(
        reported_beds=0,
        last_update_ts=now - 300,
        travel_time_min=15.0,
        now=now,
        is_offline=True,
        is_icu=True,
    )
    assert res_zero["probability"] < 0.20

    # 4 reported ICU beds should yield significantly higher probability
    res_avail = confidence.forecast_capacity_probability(
        reported_beds=4,
        last_update_ts=now - 300,
        travel_time_min=15.0,
        now=now,
        is_offline=True,
        is_icu=True,
    )
    assert res_avail["probability"] > res_zero["probability"]


def test_ttdc_snapshot_populates_forecast_fields():
    hosp = {
        "id": "H_TEST",
        "name": "Test General",
        "latitude": 28.61,
        "longitude": 77.21,
        "beds_available": 5,
        "icu_beds_available": 2,
        "active_boarders": 1,
        "inbound_ambulances": 0,
        "ct_operational": True,
        "specialist_status": "ACTIVE",
        "specialties": ["Trauma"],
        "last_update_ts": time.time() - 900,  # 15m ago
    }
    snap = ttdc.snapshot(hosp, travel_time_min=10.0, is_offline=True)
    assert snap.capacity_probability > 0.0
    assert snap.icu_probability > 0.0
    assert snap.forecast_mode == "OFFLINE_PROBABILISTIC"
    assert snap.forecast_confidence_band != ""
    assert "Unconfirmed estimate" in snap.forecast_disclaimer


def test_assessment_offline_mode_api(client):
    payload = {
        "ambulance_id": "AMB-OFFLINE-99",
        "latitude": 28.6200,
        "longitude": 77.2100,
        "vitals": {
            "respiration_rate": 22,
            "spo2": 93,
            "systolic_bp": 110,
            "heart_rate": 105,
            "consciousness": "A",
            "temperature": 38.2,
        },
        "care_tag": "RESPIRATORY",
        "emergency_description": "Acute dyspnea in rural cellular dead zone. Wheezing, unable to complete sentences.",
        "custom_requirements": ["ICU"],
        "paramedic_notes": "Continuous albuterol nebulizer initiated.",
        "offline_mode": True,
    }

    res = client.post("/api/assessments", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["offline_mode"] is True
    assert data["system_status"] == "OFFLINE_PREDICTIVE"
    assert data["offline_warning"] is not None
    assert "Offline Probabilistic Mode" in data["offline_warning"]
    assert len(data["rankings"]) > 0

    top = data["rankings"][0]
    hosp = top["hospital"]
    assert "capacity_probability" in hosp
    assert "icu_probability" in hosp
    assert hosp["forecast_mode"] == "OFFLINE_PROBABILISTIC"
    assert "Unconfirmed estimate" in hosp["forecast_disclaimer"]

    # Rationale contains probabilistic capacity mention
    rationale_str = " ".join(data["rationale"])
    assert "probabilistic" in rationale_str.lower() or "predicted" in rationale_str.lower()
