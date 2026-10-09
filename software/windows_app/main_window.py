"""Flagship Main Window for VitalRoute Hospital Emergency Department Windows Application."""
from __future__ import annotations

import csv
import datetime
import os
import sys
import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMenuBar, QMessageBox, QPushButton,
                               QSizePolicy, QSpinBox, QSplitter, QStatusBar,
                               QTableWidget, QTableWidgetItem, QTextEdit,
                               QVBoxLayout, QWidget)
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

try:
    from .api_client import VitalRouteApiClient
    from .styles import DARK_MEDICAL_THEME
except (ImportError, ValueError):
    from api_client import VitalRouteApiClient
    from styles import DARK_MEDICAL_THEME


class HospitalMainWindow(QMainWindow):
    def __init__(self, server_url: str = "http://localhost:8000"):
        super().__init__()
        self.setWindowTitle("VitalRoute — Hospital Emergency Department Triage HUD")
        self.resize(1280, 840)
        self.setMinimumSize(1020, 700)

        # Set application icon
        self._load_icon()

        self.server_url = server_url
        self.api = VitalRouteApiClient(base_url=server_url, parent=self)
        self.hospitals_cache: list[dict] = []
        self.handshakes_cache: list[dict] = []
        self.selected_handshake: dict | None = None
        self.sound_enabled: bool = True
        self.last_ping_ms: float = 0.0

        self.setStyleSheet(DARK_MEDICAL_THEME)

        self._init_menu()
        self._init_ui()
        self._connect_signals()

        # Initial data loading
        self.api.fetch_hospitals()
        self.api.connect_ws("H1")

        # Background poll every 5s for reliability fallback
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(5000)
        self.poll_timer.timeout.connect(self._on_poll_tick)
        self.poll_timer.start()

    def _load_icon(self) -> None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_candidates = [
            os.path.join(base_dir, "vitalroute.ico"),
            os.path.join(os.path.dirname(__file__), "vitalroute.ico"),
            os.path.join(getattr(sys, "_MEIPASS", ""), "vitalroute.ico"),
        ]
        for icp in icon_candidates:
            if os.path.exists(icp):
                self.setWindowIcon(QIcon(icp))
                break

    def _init_menu(self) -> None:
        mb = self.menuBar()

        # File Menu
        menu_file = mb.addMenu("&File")

        act_conn = QAction("⚙ &Server Connection Settings...", self)
        act_conn.triggered.connect(self._open_connection_dialog)
        menu_file.addAction(act_conn)

        act_export = QAction("📁 &Export Handshakes (CSV)...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self._export_handshakes_csv)
        menu_file.addAction(act_export)

        menu_file.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence("Alt+F4"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # Facility Menu
        menu_facility = mb.addMenu("F&acility")
        self.facility_menu_group = menu_facility

        act_refresh = QAction("🔄 &Refresh Network State", self)
        act_refresh.setShortcut(QKeySequence("F5"))
        act_refresh.triggered.connect(self._on_manual_refresh)
        menu_facility.addAction(act_refresh)

        # Triage Menu
        menu_triage = mb.addMenu("&Triage")
        act_ack = QAction("✅ Acknowledge & Reserve Bay", self)
        act_ack.setShortcut(QKeySequence("Return"))
        act_ack.triggered.connect(self._on_confirm_handshake)
        menu_triage.addAction(act_ack)

        act_reroute = QAction("⚠️ Report Constraint / Diversion", self)
        act_reroute.setShortcut(QKeySequence("Escape"))
        act_reroute.triggered.connect(self._on_constraint_handshake)
        menu_triage.addAction(act_reroute)

        # Help Menu
        menu_help = mb.addMenu("&Help")
        act_about = QAction("ℹ &About VitalRoute...", self)
        act_about.triggered.connect(self._show_about_dialog)
        menu_help.addAction(act_about)

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(10)

        # ------------------------------------------------ Top Bar
        top_bar = QFrame(self)
        top_bar.setStyleSheet("background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 6px;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 6, 10, 6)

        title_lbl = QLabel("🏥 VitalRoute Emergency HUD", self)
        title_font = QFont("Segoe UI", 12)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #38bdf8;")
        top_layout.addWidget(title_lbl)

        tag_flagship = QLabel("FLAGSHIP EDITION", self)
        tag_flagship.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-size: 10px; font-weight: bold; padding: 3px 6px; border-radius: 4px; margin-left: 6px;")
        top_layout.addWidget(tag_flagship)

        top_layout.addSpacing(20)
        top_layout.addWidget(QLabel("Receiving Facility:", self))

        self.combo_hospitals = QComboBox(self)
        self.combo_hospitals.setMinimumWidth(280)
        self.combo_hospitals.currentIndexChanged.connect(self._on_hospital_changed)
        top_layout.addWidget(self.combo_hospitals)

        top_layout.addStretch()

        self.btn_refresh = QPushButton("🔄 Refresh (F5)", self)
        self.btn_refresh.clicked.connect(self._on_manual_refresh)
        top_layout.addWidget(self.btn_refresh)

        self.chk_sound = QCheckBox("🔔 Audio Alerts", self)
        self.chk_sound.setChecked(True)
        self.chk_sound.toggled.connect(lambda v: setattr(self, "sound_enabled", v))
        top_layout.addWidget(self.chk_sound)

        self.lbl_ws_status = QLabel("● Connecting...", self)
        self.lbl_ws_status.setStyleSheet("color: #f59e0b; font-weight: bold; margin-left: 12px;")
        top_layout.addWidget(self.lbl_ws_status)

        root_layout.addWidget(top_bar)

        # ------------------------------------------------ Main Splitter (Left: Controls, Right: Queue & Details)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(6)

        # ----------------------- Left Panel: Capacity Controls
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        cap_group = QGroupBox("Hospital ED Capacity & Specialists", self)
        cap_layout = QFormLayout(cap_group)
        cap_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        cap_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        cap_layout.setVerticalSpacing(10)

        self.spin_beds = QSpinBox(self)
        self.spin_beds.setRange(0, 100)
        cap_layout.addRow("ED Beds Available:", self.spin_beds)

        self.spin_icu = QSpinBox(self)
        self.spin_icu.setRange(0, 50)
        cap_layout.addRow("ICU Beds Available:", self.spin_icu)

        self.spin_boarders = QSpinBox(self)
        self.spin_boarders.setRange(0, 100)
        cap_layout.addRow("Active ED Boarders:", self.spin_boarders)

        self.combo_specialist = QComboBox(self)
        self.combo_specialist.addItems(["ACTIVE", "ON_CALL", "UNAVAILABLE"])
        cap_layout.addRow("Specialist Team:", self.combo_specialist)

        self.chk_ct = QCheckBox("CT Scanner Operational", self)
        self.chk_ct.setChecked(True)
        cap_layout.addRow("CT Diagnostics:", self.chk_ct)

        self.btn_save_capacity = QPushButton("💾 Update ED Capacity", self)
        self.btn_save_capacity.setObjectName("btnUpdateCapacity")
        self.btn_save_capacity.clicked.connect(self._on_save_capacity)
        cap_layout.addRow(self.btn_save_capacity)

        left_layout.addWidget(cap_group)

        # Confidence Metrics Box
        conf_group = QGroupBox("Data Freshness & Confidence", self)
        conf_layout = QVBoxLayout(conf_group)
        self.lbl_freshness = QLabel("Freshness Score: --", self)
        self.lbl_staleness = QLabel("Staleness: -- min", self)
        self.lbl_conf_beds = QLabel("Confidence-Adjusted Beds: --", self)
        conf_layout.addWidget(self.lbl_freshness)
        conf_layout.addWidget(self.lbl_staleness)
        conf_layout.addWidget(self.lbl_conf_beds)
        left_layout.addWidget(conf_group)

        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # ----------------------- Right Panel: Pre-Arrival Queue & Detailed HUD
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)

        # Queue Table
        queue_group = QGroupBox("Live Pre-Arrival Emergency Queue", self)
        queue_layout = QVBoxLayout(queue_group)

        self.table_queue = QTableWidget(self)
        self.table_queue.setColumnCount(7)
        self.table_queue.setHorizontalHeaderLabels([
            "Status", "ETA (min)", "Emergency Category", "NEWS2 Score", "Ambulance", "Incident ID", "Time Received"
        ])
        self.table_queue.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_queue.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_queue.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_queue.itemSelectionChanged.connect(self._on_queue_selection_changed)
        queue_layout.addWidget(self.table_queue)

        right_layout.addWidget(queue_group, stretch=4)

        # Selected Case Details Group
        self.case_group = QGroupBox("Selected Emergency Case — Pre-Arrival Triage Detail", self)
        case_layout = QGridLayout(self.case_group)
        case_layout.setContentsMargins(12, 14, 12, 10)
        case_layout.setSpacing(10)

        # Paramedic Emergency Situation Description (highlighted in prominent box)
        lbl_sit_title = QLabel("Paramedic Emergency Situation & Scene Observations (Free-Text):", self)
        lbl_sit_title.setStyleSheet("font-weight: bold; color: #38bdf8;")
        case_layout.addWidget(lbl_sit_title, 0, 0, 1, 2)

        self.txt_situation = QTextEdit(self)
        self.txt_situation.setReadOnly(True)
        self.txt_situation.setMaximumHeight(70)
        self.txt_situation.setStyleSheet("background-color: #030712; color: #f97316; font-size: 13px; font-weight: 500; border: 1px solid #374151; border-radius: 5px;")
        case_layout.addWidget(self.txt_situation, 1, 0, 1, 2)

        # Custom Requirements & Paramedic Notes
        self.lbl_custom_req = QLabel("Specialized Resources Requested: None", self)
        self.lbl_custom_req.setStyleSheet("color: #a7f3d0; font-weight: 600;")
        case_layout.addWidget(self.lbl_custom_req, 2, 0)

        self.lbl_paramedic_notes = QLabel("Paramedic Field Notes: None", self)
        self.lbl_paramedic_notes.setStyleSheet("color: #cbd5e1;")
        case_layout.addWidget(self.lbl_paramedic_notes, 2, 1)

        # NEWS2 Vitals Grid
        self.lbl_vitals_summary = QLabel("Vitals: RR: -- | SpO2: -- | SBP: -- | HR: -- | Temp: -- | AVPU: --", self)
        self.lbl_vitals_summary.setStyleSheet("background-color: #0f172a; padding: 6px; border-radius: 4px; font-family: monospace;")
        case_layout.addWidget(self.lbl_vitals_summary, 3, 0, 1, 2)

        # Triage Actions Area
        action_frame = QFrame(self)
        action_frame.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 8px;")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(6, 4, 6, 4)

        action_layout.addWidget(QLabel("Suggested ESI:", self))
        self.lbl_sug_esi = QLabel("ESI --", self)
        self.lbl_sug_esi.setStyleSheet("font-weight: bold; color: #fbbf24; font-size: 14px;")
        action_layout.addWidget(self.lbl_sug_esi)

        action_layout.addSpacing(15)
        action_layout.addWidget(QLabel("Triage Nurse Anticipated ESI:", self))
        self.combo_esi = QComboBox(self)
        self.combo_esi.addItems(["ESI 1 (Immediate)", "ESI 2 (Emergent)", "ESI 3 (Urgent)", "ESI 4 (Less Urgent)", "ESI 5 (Non-urgent)"])
        self.combo_esi.setCurrentIndex(1)
        action_layout.addWidget(self.combo_esi)

        action_layout.addStretch()

        self.btn_confirm_ack = QPushButton("✅ Acknowledge & Reserve Bay", self)
        self.btn_confirm_ack.setObjectName("btnConfirm")
        self.btn_confirm_ack.clicked.connect(self._on_confirm_handshake)
        action_layout.addWidget(self.btn_confirm_ack)

        self.btn_constraint_ack = QPushButton("⚠️ Report Constraint / Reroute", self)
        self.btn_constraint_ack.setObjectName("btnConstraint")
        self.btn_constraint_ack.clicked.connect(self._on_constraint_handshake)
        action_layout.addWidget(self.btn_constraint_ack)

        case_layout.addWidget(action_frame, 4, 0, 1, 2)

        right_layout.addWidget(self.case_group, stretch=3)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        root_layout.addWidget(splitter)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("VitalRoute HUD ready. Listening for pre-arrival emergency ambulances.")

    def _connect_signals(self) -> None:
        self.api.connection_status.connect(self._on_connection_status)
        self.api.hospitals_loaded.connect(self._on_hospitals_loaded)
        self.api.hospital_data_received.connect(self._on_hospital_data_received)
        self.api.handshakes_received.connect(self._on_handshakes_received)
        self.api.incoming_handshake_event.connect(self._on_incoming_handshake)
        self.api.ack_response_received.connect(self._on_ack_response)
        self.api.error_occurred.connect(self._on_api_error)

    # ------------------------------------------------ Dialogs
    def _open_connection_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Server Connection Settings")
        dlg.resize(400, 160)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        txt_url = QLineEdit(dlg)
        txt_url.setText(self.api.base_url)
        form.addRow("VitalRoute Core URL:", txt_url)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_url = txt_url.text().strip()
            if new_url:
                self.api.set_base_url(new_url)
                self.status_bar.showMessage(f"Target server set to {new_url}", 4000)
                self._on_manual_refresh()

    def _export_handshakes_csv(self) -> None:
        if not self.handshakes_cache:
            QMessageBox.information(self, "Export Handshakes", "No handshakes available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Handshake Audit Log",
            f"VitalRoute_Handshakes_{datetime.date.today()}.csv",
            "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Incident_ID", "Timestamp", "Ambulance_ID", "Hospital_ID", "Status",
                    "ETA_Min", "Care_Tag", "Emergency_Description", "Specialized_Requirements",
                    "Paramedic_Notes", "NEWS2_Score", "NEWS2_Risk_Band", "Anticipated_ESI",
                    "Constraint_Detail"
                ])
                for hs in self.handshakes_cache:
                    p = hs.get("patient", {})
                    ts = hs.get("created_ts", 0)
                    time_str = datetime.datetime.fromtimestamp(ts).isoformat() if ts else ""
                    writer.writerow([
                        hs.get("id"),
                        time_str,
                        hs.get("ambulance_id"),
                        hs.get("hospital_id"),
                        hs.get("status"),
                        hs.get("eta_min"),
                        p.get("care_tag"),
                        p.get("emergency_description", ""),
                        "; ".join(p.get("custom_requirements", [])),
                        p.get("paramedic_notes", ""),
                        p.get("news2"),
                        p.get("news2_risk_band"),
                        hs.get("anticipated_esi", ""),
                        hs.get("constraint_detail", "")
                    ])
            QMessageBox.information(self, "Export Success", f"Successfully exported {len(self.handshakes_cache)} handshake logs to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {e}")

    def _show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About VitalRoute — Hospital ED Triage HUD",
            "<h2>VitalRoute Emergency Triage HUD</h2>"
            "<p><b>Version:</b> 1.0.0 (Flagship Production Edition)</p>"
            "<p><b>SDG 3 Alignment:</b> Good Health and Well-Being (Target 3.6 & 3.8)</p>"
            "<p><b>Architecture:</b> Confidence-Aware Emergency Destination Orchestration with Pre-Arrival Verification Handshake</p>"
            "<hr>"
            "<p>Designed for hospital triage nurses and emergency department coordinators to prevent offload delays and phantom bed diversions.</p>"
            "<p><b>Open Source:</b> 100% Free & Open-Source Stack (PySide6 / FastAPI / WebSockets).</p>"
        )

    # ------------------------------------------------ Slots & Events
    def _play_alert_sound(self) -> None:
        if not self.sound_enabled:
            return
        try:
            import winsound
            winsound.Beep(880, 120)
            winsound.Beep(1175, 180)
        except Exception:
            from PySide6.QtWidgets import QApplication
            QApplication.beep()

    def _on_poll_tick(self) -> None:
        curr_id = self._get_current_hospital_id()
        if curr_id:
            self.api.fetch_hospital(curr_id)
            self.api.fetch_handshakes(curr_id)

    def _on_manual_refresh(self) -> None:
        curr_id = self._get_current_hospital_id()
        if curr_id:
            self.api.fetch_hospitals()
            self.api.fetch_hospital(curr_id)
            self.api.fetch_handshakes(curr_id)

    def _on_connection_status(self, connected: bool, msg: str) -> None:
        if connected:
            self.lbl_ws_status.setText("● Connected")
            self.lbl_ws_status.setStyleSheet("color: #10b981; font-weight: bold; margin-left: 12px;")
        else:
            self.lbl_ws_status.setText("● Disconnected")
            self.lbl_ws_status.setStyleSheet("color: #ef4444; font-weight: bold; margin-left: 12px;")
        self.status_bar.showMessage(msg)

    def _on_hospitals_loaded(self, hospitals: list[dict]) -> None:
        self.hospitals_cache = hospitals
        current_id = self._get_current_hospital_id()
        self.combo_hospitals.blockSignals(True)
        self.combo_hospitals.clear()
        for idx, h in enumerate(hospitals):
            self.combo_hospitals.addItem(f"{h['id']} — {h['name']}", h['id'])
            if h['id'] == current_id:
                self.combo_hospitals.setCurrentIndex(idx)
        self.combo_hospitals.blockSignals(False)

        if not current_id and hospitals:
            self._select_hospital_by_id(hospitals[0]["id"])

    def _on_hospital_changed(self) -> None:
        h_id = self._get_current_hospital_id()
        if h_id:
            self.api.connect_ws(h_id)
            self.api.fetch_hospital(h_id)
            self.api.fetch_handshakes(h_id)

    def _select_hospital_by_id(self, h_id: str) -> None:
        for i in range(self.combo_hospitals.count()):
            if self.combo_hospitals.itemData(i) == h_id:
                self.combo_hospitals.setCurrentIndex(i)
                break

    def _get_current_hospital_id(self) -> str:
        data = self.combo_hospitals.currentData()
        return str(data) if data else "H1"

    def _on_hospital_data_received(self, h: dict) -> None:
        self.spin_beds.setValue(h.get("beds_available", 0))
        self.spin_icu.setValue(h.get("icu_beds_available", 0))
        self.spin_boarders.setValue(h.get("active_boarders", 0))

        spec = h.get("specialist_status", "ACTIVE")
        idx = self.combo_specialist.findText(spec)
        if idx >= 0:
            self.combo_specialist.setCurrentIndex(idx)

        self.chk_ct.setChecked(bool(h.get("ct_operational", True)))

        f = h.get("freshness", 1.0)
        stale_min = h.get("staleness_minutes", 0.0)
        conf_beds = h.get("confidence_adjusted_beds", h.get("beds_available", 0))

        self.lbl_freshness.setText(f"Freshness Score: {f:.2f}")
        self.lbl_staleness.setText(f"Staleness: {stale_min:.1f} min ago")
        self.lbl_conf_beds.setText(f"Confidence-Adjusted Beds: {conf_beds:.1f}")

    def _on_save_capacity(self) -> None:
        h_id = self._get_current_hospital_id()
        if not h_id:
            return
        self.api.update_hospital_capacity(
            hospital_id=h_id,
            beds=self.spin_beds.value(),
            icu_beds=self.spin_icu.value(),
            active_boarders=self.spin_boarders.value(),
            specialist_status=self.combo_specialist.currentText(),
            ct_operational=self.chk_ct.isChecked(),
        )
        self.status_bar.showMessage(f"Updated capacity for {h_id}. Broadcast sent to regional ambulance network.", 4000)

    def _on_handshakes_received(self, handshakes: list[dict]) -> None:
        self.handshakes_cache = handshakes
        self.table_queue.setRowCount(len(handshakes))

        for row, hs in enumerate(handshakes):
            patient = hs.get("patient", {})
            vitals = patient.get("vitals", {})

            # Status item with distinct color styling
            st = hs.get("status", "PENDING_RESPONSE")
            status_item = QTableWidgetItem(st)
            if st == "CONFIRMED":
                status_item.setForeground(QColor("#10b981"))
            elif st == "CONSTRAINED_REROUTE_REQUESTED":
                status_item.setForeground(QColor("#ef4444"))
            elif st == "TIMED_OUT":
                status_item.setForeground(QColor("#9ca3af"))
            else:
                status_item.setForeground(QColor("#f59e0b"))

            eta_item = QTableWidgetItem(f"{hs.get('eta_min', 0):.1f}")
            tag_item = QTableWidgetItem(str(patient.get("care_tag", "GENERAL")))

            news_val = patient.get("news2", 0)
            risk_band = patient.get("news2_risk_band", "LOW")
            news2_item = QTableWidgetItem(f"{news_val} ({risk_band})")
            if news_val >= 7:
                news2_item.setForeground(QColor("#ef4444"))
            elif news_val >= 5:
                news2_item.setForeground(QColor("#f59e0b"))

            amb_item = QTableWidgetItem(hs.get("ambulance_id", "AMB-1"))
            inc_item = QTableWidgetItem(hs.get("id", ""))

            ts = hs.get("created_ts", 0)
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
            time_item = QTableWidgetItem(time_str)

            self.table_queue.setItem(row, 0, status_item)
            self.table_queue.setItem(row, 1, eta_item)
            self.table_queue.setItem(row, 2, tag_item)
            self.table_queue.setItem(row, 3, news2_item)
            self.table_queue.setItem(row, 4, amb_item)
            self.table_queue.setItem(row, 5, inc_item)
            self.table_queue.setItem(row, 6, time_item)

        # Retain or select row
        if handshakes and self.table_queue.currentRow() < 0:
            self.table_queue.selectRow(0)

    def _on_queue_selection_changed(self) -> None:
        row = self.table_queue.currentRow()
        if 0 <= row < len(self.handshakes_cache):
            self.selected_handshake = self.handshakes_cache[row]
            self._render_selected_case(self.selected_handshake)

    def _render_selected_case(self, hs: dict) -> None:
        patient = hs.get("patient", {})
        vitals = patient.get("vitals", {})

        # Manually typed situation
        desc = patient.get("emergency_description")
        if desc:
            self.txt_situation.setPlainText(desc)
        else:
            tag = patient.get("care_tag", "GENERAL")
            self.txt_situation.setPlainText(f"Predefined Category: {tag} (No additional manual situation typed by crew)")

        # Custom requirements
        reqs = patient.get("custom_requirements", [])
        if reqs:
            self.lbl_custom_req.setText(f"Specialized Resources Requested: {', '.join(reqs)}")
        else:
            self.lbl_custom_req.setText("Specialized Resources Requested: Standard ED Protocol")

        # Paramedic notes
        notes = patient.get("paramedic_notes")
        self.lbl_paramedic_notes.setText(f"Paramedic Notes: {notes if notes else 'None'}")

        # Vitals
        rr = vitals.get("respiration_rate", "--")
        spo2 = vitals.get("spo2", "--")
        sbp = vitals.get("systolic_bp", "--")
        hr = vitals.get("heart_rate", "--")
        temp = vitals.get("temperature", "--")
        avpu = vitals.get("consciousness", "--")
        news2 = patient.get("news2", 0)
        risk = patient.get("news2_risk_band", "LOW")

        self.lbl_vitals_summary.setText(
            f"NEWS2: {news2} [{risk}] | RR: {rr} | SpO2: {spo2}% | SBP: {sbp} mmHg | HR: {hr} bpm | Temp: {temp}°C | AVPU: {avpu}"
        )

        # Suggested ESI
        sug_esi = hs.get("anticipated_esi") or 2
        self.lbl_sug_esi.setText(f"ESI {sug_esi}")
        if 1 <= sug_esi <= 5:
            self.combo_esi.setCurrentIndex(sug_esi - 1)

        st = hs.get("status")
        is_pending = st == "PENDING_RESPONSE"
        self.btn_confirm_ack.setEnabled(is_pending)
        self.btn_constraint_ack.setEnabled(is_pending)

    def _on_incoming_handshake(self, evt: dict) -> None:
        hs = evt.get("handshake", {})
        sug_esi = evt.get("suggested_esi", 2)
        hs["anticipated_esi"] = sug_esi

        curr_id = self._get_current_hospital_id()
        self.api.fetch_handshakes(curr_id)

        amb_id = hs.get("ambulance_id", "Ambulance")
        desc = hs.get("patient", {}).get("emergency_description") or hs.get("patient", {}).get("care_tag", "EMERGENCY")
        self.status_bar.showMessage(f"🚨 INCOMING EMERGENCY: {amb_id} inbound! ({desc})", 9000)

        # Play chime
        self._play_alert_sound()

    def _on_confirm_handshake(self) -> None:
        if not self.selected_handshake:
            return
        hs_id = self.selected_handshake.get("id")
        chosen_esi = self.combo_esi.currentIndex() + 1
        self.api.acknowledge_handshake(
            handshake_id=hs_id,
            confirm=True,
            anticipated_esi=chosen_esi
        )

    def _on_constraint_handshake(self) -> None:
        if not self.selected_handshake:
            return
        hs_id = self.selected_handshake.get("id")

        dialog = QDialog(self)
        dialog.setWindowTitle("Report Hospital Capacity Constraint")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Specify reason for diversion / reroute:", dialog))

        edit_reason = QLineEdit(dialog)
        edit_reason.setText("ED Resuscitation Bay at Critical Capacity / CT Scanner Surge")
        layout.addWidget(edit_reason)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            reason = edit_reason.text().strip()
            self.api.acknowledge_handshake(
                handshake_id=hs_id,
                confirm=False,
                constraint=reason
            )

    def _on_ack_response(self, hs: dict) -> None:
        st = hs.get("status")
        msg = "Confirmed and bay reserved." if st == "CONFIRMED" else "Diverted / constraint logged."
        self.status_bar.showMessage(f"Handshake {hs.get('id')} updated: {msg}", 5000)
        curr_id = self._get_current_hospital_id()
        self.api.fetch_handshakes(curr_id)

    def _on_api_error(self, err_msg: str) -> None:
        self.status_bar.showMessage(f"Notice: {err_msg}", 4000)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    server = os.environ.get("VR_SERVER_URL", "http://localhost:8000")
    window = HospitalMainWindow(server_url=server)
    window.show()
    sys.exit(app.exec())

