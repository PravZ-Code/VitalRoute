"""Unit tests for the four algorithmic pillars + clinical scoring."""
import math
import time

from app import config, state
from app.models import CareTag, SpecialistStatus, Vitals
from app.services import clinical, confidence, ttdc


# ------------------------------------------------------------- Pillar 1
def test_freshness_decays_with_half_life():
    now = time.time()
    assert confidence.freshness(now, now) == 1.0
    f = confidence.freshness(now - 15 * 60, now)          # one half-life
    assert math.isclose(f, 0.5, abs_tol=0.01)
    f2 = confidence.freshness(now - 30 * 60, now)
    assert math.isclose(f2, 0.25, abs_tol=0.02)


def test_stale_threshold():
    assert not confidence.is_stale(0.5)
    assert confidence.is_stale(0.49)


def test_confidence_adjusted_penalises_stale_data():
    recent = confidence.confidence_adjusted_capacity(5, 1.0)
    old = confidence.confidence_adjusted_capacity(5, 0.2)
    assert recent == 5
    assert old < recent


# ------------------------------------------------------------- Pillar 2
def test_offload_model():
    h = {"active_boarders": 3, "inbound_ambulances": 2}
    assert ttdc.offload_delay_min(h) == config.OFFLOAD_BETA * 3 + config.OFFLOAD_GAMMA * 2


def test_readiness_model():
    assert ttdc.readiness_min({"specialist_status": SpecialistStatus.ACTIVE}) == 0
    assert ttdc.readiness_min({"specialist_status": SpecialistStatus.ON_CALL}) == config.READINESS_ON_CALL_MIN
    assert ttdc.readiness_min({"specialist_status": SpecialistStatus.UNAVAILABLE}) == float("inf")


def test_ttdc_prefers_faster_care_over_faster_drive():
    """Core differentiator: a farther hospital with low offload delay beats a
    close hospital with a crowded hallway queue."""
    now = time.time()
    near_jammed = {"id": "A", "name": "Near", "latitude": 28.613, "longitude": 77.229,
                   "beds_available": 5, "icu_beds_available": 1, "active_boarders": 12,
                   "inbound_ambulances": 3, "ct_operational": True,
                   "specialist_status": SpecialistStatus.ACTIVE, "last_update_ts": now}
    far_open = {"id": "B", "name": "Far", "latitude": 28.63, "longitude": 77.24,
                "beds_available": 5, "icu_beds_available": 1, "active_boarders": 0,
                "inbound_ambulances": 0, "ct_operational": True,
                "specialist_status": SpecialistStatus.ACTIVE, "last_update_ts": now}
    ranked, rationale = ttdc.rank_hospitals({"A": near_jammed, "B": far_open},
                                            28.6129, 77.2295, CareTag.GENERAL, now)
    assert ranked[0].hospital.id == "B"
    assert any("offload" in r for r in rationale)


def test_stroke_requires_ct():
    now = time.time()
    no_ct = {"id": "X", "name": "NoCT", "latitude": 28.613, "longitude": 77.229,
             "beds_available": 5, "icu_beds_available": 1, "active_boarders": 0,
             "inbound_ambulances": 0, "ct_operational": False,
             "specialist_status": SpecialistStatus.ACTIVE, "last_update_ts": now}
    ranked, _ = ttdc.rank_hospitals({"X": no_ct}, 28.6129, 77.2295, CareTag.STROKE, now)
    assert not ranked[0].eligible
    assert "CT" in ranked[0].ineligibility_reason


def test_stale_top_recommendation_triggers_warning():
    now = time.time()
    stale_best = {"id": "S", "name": "Stale", "latitude": 28.613, "longitude": 77.229,
                  "beds_available": 5, "icu_beds_available": 1, "active_boarders": 0,
                  "inbound_ambulances": 0, "ct_operational": True,
                  "specialist_status": SpecialistStatus.ACTIVE,
                  "last_update_ts": now - 40 * 60}
    fresh_far = {"id": "F", "name": "Fresh", "latitude": 28.70, "longitude": 77.30,
                 "beds_available": 5, "icu_beds_available": 1, "active_boarders": 0,
                 "inbound_ambulances": 0, "ct_operational": True,
                 "specialist_status": SpecialistStatus.ACTIVE, "last_update_ts": now}
    ranked, rationale = ttdc.rank_hospitals({"S": stale_best, "F": fresh_far},
                                            28.6129, 77.2295, CareTag.GENERAL, now)
    # Stale data must NOT silently pass: the top recommendation must be
    # flagged as unverified and a mandated handshake warning surfaced.
    assert ranked[0].hospital.stale
    assert any(r.lower().startswith("warning") for r in rationale)


# ------------------------------------------------------------- clinical
def test_news2_known_profile():
    # classic moderate deterioration profile
    v = Vitals(respiration_rate=26, spo2=94, systolic_bp=95, heart_rate=120,
               consciousness="V", temperature=38.5)
    # rr26->3, spo2 94->1, sbp95->2, hr120->2, V->3, t38.5->1 = 12
    assert clinical.news2_score(v) == 12
    assert clinical.risk_band(12) == "HIGH"


def test_news2_zero_for_baseline():
    v = Vitals(respiration_rate=16, spo2=98, systolic_bp=120, heart_rate=70,
               consciousness="A", temperature=37.0)
    assert clinical.news2_score(v) == 0
    assert clinical.risk_band(0) == "LOW"
    assert clinical.risk_band(2) == "LOW-MEDIUM"
    assert clinical.risk_band(5) == "MEDIUM"
    assert clinical.risk_band(7) == "HIGH"


def test_esi_suggested_only_at_hospital():
    assert clinical.suggested_esi(12, "STEMI") == 1
    assert clinical.suggested_esi(1, "GENERAL") == 4


# ------------------------------------------------------------- store
def test_event_update_refreshes_timestamp():
    before = state.get_hospitals()["H3"]["last_update_ts"]
    state.update_hospital("H3", beds_available=7, refresh_timestamp=True)
    after = state.get_hospitals()["H3"]["last_update_ts"]
    assert after > before


def test_specialist_status_coercion_from_string():
    state.update_hospital("H5", specialist_status="ACTIVE")
    h5 = state.get_hospitals()["H5"]
    assert h5["specialist_status"] == SpecialistStatus.ACTIVE
    assert isinstance(h5["specialist_status"], SpecialistStatus)

