from pathlib import Path
import sys
import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError as import_error:
    QApplication = None
    PYSIDE_IMPORT_ERROR = import_error
else:
    PYSIDE_IMPORT_ERROR = None

SOFTWARE_DIR = Path(__file__).resolve().parent.parent.parent / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

try:
    from windows_app.main_window import HospitalMainWindow
except ImportError as import_error:
    try:
        from app.windows_app.main_window import HospitalMainWindow
    except ImportError:
        HospitalMainWindow = None
        WINDOWS_APP_IMPORT_ERROR = import_error
    else:
        WINDOWS_APP_IMPORT_ERROR = None
else:
    WINDOWS_APP_IMPORT_ERROR = None


@pytest.fixture(scope="session")
def qapp():
    if QApplication is None:
        pytest.skip(f"PySide6 is unavailable in this environment: {PYSIDE_IMPORT_ERROR}")
    if HospitalMainWindow is None:
        pytest.skip(f"Windows app dependencies are unavailable in this environment: {WINDOWS_APP_IMPORT_ERROR}")
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_hospital_main_window_init(qapp):
    window = HospitalMainWindow(server_url="http://localhost:8000")
    assert window is not None
    assert "VitalRoute" in window.windowTitle()
    assert window.spin_beds is not None
    assert window.table_queue is not None
    assert window.txt_situation is not None

    # Test rendering a sample handshake
    sample_handshake = {
        "id": "HS-TEST-99",
        "ambulance_id": "AMB-205",
        "hospital_id": "H1",
        "eta_min": 7.4,
        "status": "PENDING_RESPONSE",
        "created_ts": 1700000000.0,
        "patient": {
            "incident_id": "INC-8888",
            "news2": 8,
            "news2_risk_band": "HIGH",
            "care_tag": "TRAUMA",
            "emergency_description": "Multi-car highway collision; trapped driver with open flail chest and pelvic instability.",
            "custom_requirements": ["Trauma", "ICU"],
            "paramedic_notes": "Bilateral needle thoracostomy performed, pelvic binder secured.",
            "vitals": {
                "respiration_rate": 28,
                "spo2": 89,
                "systolic_bp": 85,
                "heart_rate": 130,
                "consciousness": "P",
                "temperature": 36.2
            }
        }
    }

    window._render_selected_case(sample_handshake)
    assert "open flail chest" in window.txt_situation.toPlainText()
    assert "Trauma, ICU" in window.lbl_custom_req.text()
    assert "needle thoracostomy" in window.lbl_paramedic_notes.text()
    assert "NEWS2: 8 [HIGH]" in window.lbl_vitals_summary.text()

    window.close()
