"""API and end-to-end workflow tests (assessment -> handshake -> ack)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VITALS = {"respiration_rate": 24, "spo2": 95, "systolic_bp": 108,
          "heart_rate": 112, "consciousness": "A", "temperature": 38.2}

ASSESSMENT = {"ambulance_id": "AMB-T", "latitude": 28.6129, "longitude": 77.2295,
              "vitals": VITALS, "care_tag": "TRAUMA"}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["data_mode"] == "synthetic-simulation"


def test_hospitals_have_freshness_fields():
    r = client.get("/api/hospitals")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 5
    for h in rows:
        assert 0.0 < h["freshness"] <= 1.0
        assert "confidence_adjusted_beds" in h


def test_assessment_returns_rankings_and_rationale():
    r = client.post("/api/assessments", json=ASSESSMENT)
    assert r.status_code == 200
    data = r.json()
    assert data["news2"] >= 0 and data["recommended"]
    top = data["rankings"][0]
    assert top["rank"] == 1
    assert top["ttdc_min"] > 0
    assert isinstance(data["rationale"], list) and data["rationale"]
    assert "Synthetic" in data["data_disclaimer"]


def test_assessment_rejects_invalid_vitals():
    bad = dict(ASSESSMENT, vitals=dict(VITALS, spo2=20))
    assert client.post("/api/assessments", json=bad).status_code == 422


def test_handshake_full_workflow():
    hs = client.post("/api/handshake?hospital_id=H2", json=ASSESSMENT)
    assert hs.status_code == 201
    hs = hs.json()
    assert hs["status"] == "PENDING_RESPONSE"
    assert hs["patient"]["care_tag"] == "TRAUMA"

    ack = client.post(f"/api/handshake/{hs['id']}/ack?confirm=true&anticipated_esi=2")
    assert ack.status_code == 200
    assert ack.json()["status"] == "CONFIRMED"
    assert ack.json()["anticipated_esi"] == 2

    # double-ack rejected
    again = client.post(f"/api/handshake/{hs['id']}/ack?confirm=true")
    assert again.status_code == 409


def test_handshake_constraint_reroute():
    hs = client.post("/api/handshake?hospital_id=H4", json=ASSESSMENT).json()
    ack = client.post(
        f"/api/handshake/{hs['id']}/ack?confirm=false&constraint=Cath%20Lab%20occupied")
    assert ack.json()["status"] == "CONSTRAINED_REROUTE_REQUESTED"
    assert ack.json()["constraint_detail"] == "Cath Lab occupied"


def test_handshake_unknown_hospital_404():
    assert client.post("/api/handshake?hospital_id=HX", json=ASSESSMENT).status_code == 404


def test_event_injection_broadcasts_freshness():
    r = client.post("/api/hospitals/event",
                    json={"hospital_id": "H1", "beds_available": 9})
    assert r.status_code == 200
    assert r.json()["beds_available"] == 9
    assert r.json()["freshness"] > 0.99          # timestamp refreshed


def test_whatif_does_not_mutate_state():
    before = {h["id"]: h["beds_available"]
              for h in client.get("/api/hospitals").json()}
    wi = {"assessment": ASSESSMENT,
          "overrides": {"hospital_id": "H1", "beds_available": 0, "ct_operational": False}}
    r = client.post("/api/whatif", json=wi)
    assert r.status_code == 200
    names = {rk["hospital"]["id"]: rk for rk in r.json()["rankings"]}
    assert not names["H1"]["eligible"]           # 0 beds -> ineligible in sandbox
    after = {h["id"]: h["beds_available"]
             for h in client.get("/api/hospitals").json()}
    assert before == after                        # live network untouched


def test_spa_served():
    assert client.get("/").status_code == 200
    assert b"VitalRoute" in client.get("/").content


def test_spa_path_traversal_guard():
    # Unknown API route returns 404
    r = client.get("/api/nonexistent_route")
    assert r.status_code == 404

    # Traversal attempt should never leak source code
    r2 = client.get("/../../run.py")
    assert b"def " not in r2.content


def test_ws_handshake_and_ack_workflow():
    with client.websocket_connect("/ws/hospital:H2") as ws_hosp:
        with client.websocket_connect("/ws/ambulance:AMB-T") as ws_amb:
            # Request handshake -> hospital receives push
            hs = client.post("/api/handshake?hospital_id=H2", json=ASSESSMENT).json()
            msg_hosp = ws_hosp.receive_json()
            assert msg_hosp["type"] == "handshake_request"
            assert msg_hosp["handshake"]["id"] == hs["id"]

            # Ambulance receives creation notice
            msg_amb_created = ws_amb.receive_json()
            assert msg_amb_created["type"] == "handshake_created"

            # Ack handshake -> ambulance receives ack push
            client.post(f"/api/handshake/{hs['id']}/ack?confirm=true&anticipated_esi=2")
            msg_amb = ws_amb.receive_json()
            assert msg_amb["type"] == "handshake_ack"
            assert msg_amb["handshake"]["status"] == "CONFIRMED"


