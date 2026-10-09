"""Emergency Surge Simulator — multi-hospital digital twin (Innovation 5).

Background thread injects stochastic capacity fluctuation, ambulance arrivals
and boarder movement into the synthetic network so the demo is alive.
"""
from __future__ import annotations

import random
import threading
import time

from .. import state
from ..models import SpecialistStatus


class Simulator:
    def __init__(self, interval_sec: float = 20.0):
        self.interval = interval_sec
        self.running = False
        self._thread: threading.Thread | None = None
        self._on_update = None  # async callback scheduled by main event loop

    def set_broadcaster(self, fn) -> None:
        self._on_update = fn


    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self.running:
            time.sleep(self.interval)
            try:
                changes = self.tick()
                if changes and self._on_update:
                    self._on_update(changes)
            except Exception:
                pass

    def tick(self) -> list[dict]:
        hospitals = state.get_hospitals()
        hid = random.choice(list(hospitals))
        h = hospitals[hid]
        roll = random.random()
        if roll < 0.35:      # boarder flux
            delta = random.choice([-2, -1, 1, 1, 2])
            new = max(0, h["active_boarders"] + delta)
            state.update_hospital(hid, active_boarders=new, refresh_timestamp=False)
            return [{"hospital_id": hid, "field": "active_boarders", "value": new}]
        elif roll < 0.60:    # bed count drift (update = data becomes fresh)
            delta = random.choice([-1, 1])
            new = max(0, min(12, h["beds_available"] + delta))
            state.update_hospital(hid, beds_available=new)
            return [{"hospital_id": hid, "field": "beds_available", "value": new,
                     "refreshed": True}]
        elif roll < 0.75:    # inbound ambulance movement
            delta = random.choice([-1, 1])
            new = max(0, min(5, h["inbound_ambulances"] + delta))
            state.update_hospital(hid, inbound_ambulances=new, refresh_timestamp=False)
            return [{"hospital_id": hid, "field": "inbound_ambulances", "value": new}]
        elif roll < 0.85:    # specialist scrub-in / off duty
            new_s = random.choice(list(SpecialistStatus))
            state.update_hospital(hid, specialist_status=new_s)
            return [{"hospital_id": hid, "field": "specialist_status", "value": new_s.value}]
        return []


simulator = Simulator()
