"""API and WebSocket Client for VitalRoute Hospital Windows Application."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket


class VitalRouteApiClient(QObject):
    connection_status = Signal(bool, str)       # is_connected, message
    hospitals_loaded = Signal(list)             # list of hospital snapshots
    hospital_data_received = Signal(dict)       # current hospital snapshot
    handshakes_received = Signal(list)          # list of handshakes
    incoming_handshake_event = Signal(dict)     # real-time incoming handshake alert
    ack_response_received = Signal(dict)        # response from ack
    error_occurred = Signal(str)

    def __init__(self, base_url: str = "http://localhost:8000", parent: QObject | None = None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.current_hospital_id: str = "H1"

        self.ws: QWebSocket | None = None
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(4000)
        self._reconnect_timer.timeout.connect(self._reconnect_ws)

    def set_base_url(self, url: str) -> None:
        self.base_url = url.rstrip("/")
        self.disconnect_ws()
        self.connect_ws(self.current_hospital_id)

    # ---------------------------------------------------- Asynchronous HTTP helper
    def _async_get(self, endpoint: str, callback: Callable[[Any], None]) -> None:
        def worker():
            try:
                url = f"{self.base_url}{endpoint}"
                req = urllib.request.Request(url, headers={"User-Agent": "VitalRoute-WindowsApp/1.0"})
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    callback(data)
            except Exception as e:
                self.error_occurred.emit(f"GET {endpoint} failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _async_post(self, endpoint: str, payload: dict | None, callback: Callable[[Any], None]) -> None:
        def worker():
            try:
                url = f"{self.base_url}{endpoint}"
                body = json.dumps(payload).encode("utf-8") if payload is not None else b""
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json", "User-Agent": "VitalRoute-WindowsApp/1.0"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=6) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    callback(data)
            except Exception as e:
                self.error_occurred.emit(f"POST {endpoint} failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------- Public REST API Methods
    def fetch_hospitals(self) -> None:
        self._async_get("/api/hospitals", lambda data: self.hospitals_loaded.emit(data))

    def fetch_hospital(self, hospital_id: str) -> None:
        self._async_get(f"/api/hospitals/{hospital_id}", lambda data: self.hospital_data_received.emit(data))

    def fetch_handshakes(self, hospital_id: str) -> None:
        self._async_get(f"/api/handshakes/hospital/{hospital_id}", lambda data: self.handshakes_received.emit(data))

    def update_hospital_capacity(
        self,
        hospital_id: str,
        beds: int,
        icu_beds: int,
        active_boarders: int,
        specialist_status: str,
        ct_operational: bool,
    ) -> None:
        payload = {
            "hospital_id": hospital_id,
            "beds_available": beds,
            "icu_beds_available": icu_beds,
            "active_boarders": active_boarders,
            "specialist_status": specialist_status,
            "ct_operational": ct_operational,
            "refresh_timestamp": True,
        }
        self._async_post("/api/hospitals/event", payload, lambda data: self.hospital_data_received.emit(data))

    def acknowledge_handshake(
        self,
        handshake_id: str,
        confirm: bool,
        constraint: str | None = None,
        anticipated_esi: int | None = None,
    ) -> None:
        params = f"?confirm={'true' if confirm else 'false'}"
        if constraint:
            params += f"&constraint={urllib.parse.quote(constraint)}"
        if anticipated_esi is not None:
            params += f"&anticipated_esi={anticipated_esi}"

        self._async_post(f"/api/handshake/{handshake_id}/ack{params}", None, lambda data: self.ack_response_received.emit(data))

    # ---------------------------------------------------- WebSocket
    def connect_ws(self, hospital_id: str) -> None:
        self.current_hospital_id = hospital_id
        if self.ws:
            self.disconnect_ws()

        self.ws = QWebSocket()
        self.ws.connected.connect(self._on_ws_connected)
        self.ws.disconnected.connect(self._on_ws_disconnected)
        self.ws.textMessageReceived.connect(self._on_ws_message)

        ws_proto = "wss" if self.base_url.startswith("https") else "ws"
        host_port = self.base_url.split("://", 1)[1]
        ws_url = f"{ws_proto}://{host_port}/ws/hospital:{hospital_id}"

        self.connection_status.emit(False, f"Connecting to {ws_url}...")
        self.ws.open(QUrl(ws_url))

    def disconnect_ws(self) -> None:
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._reconnect_timer.stop()

    def _reconnect_ws(self) -> None:
        if self.current_hospital_id:
            self.connect_ws(self.current_hospital_id)

    def _on_ws_connected(self) -> None:
        self._reconnect_timer.stop()
        self.connection_status.emit(True, f"Connected (Hospital: {self.current_hospital_id})")

    def _on_ws_disconnected(self) -> None:
        self.connection_status.emit(False, "Disconnected from server. Reconnecting...")
        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start()

    def _on_ws_message(self, message: str) -> None:
        try:
            evt = json.loads(message)
            msg_type = evt.get("type")
            if msg_type == "handshake_request":
                self.incoming_handshake_event.emit(evt)
            elif msg_type == "hospital_update":
                h = evt.get("hospital", {})
                if h.get("id") == self.current_hospital_id:
                    self.hospital_data_received.emit(h)
            elif msg_type in ("handshake_ack", "handshake_timeout"):
                # refresh current handshakes
                self.fetch_handshakes(self.current_hospital_id)
        except Exception as e:
            self.error_occurred.emit(f"WS error parsing: {e}")
