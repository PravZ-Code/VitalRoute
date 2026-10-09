"""Native WebSocket manager — real-time layer (FastAPI native, zero fees).

Channels:
  - "ambulance:<id>" : cockpit clients receive handshake acks / reroutes
  - "hospital:<id>"  : hospital HUD receives pre-arrival handshake requests
  - "hud"            : all hospital HUDs (network ticker)
  - "sim"            : simulator console broadcasts
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {}

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        self._channels.setdefault(channel, set()).add(ws)

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        if channel in self._channels:
            self._channels[channel].discard(ws)
            if not self._channels[channel]:
                del self._channels[channel]

    async def broadcast(self, channel: str, message: dict[str, Any]) -> int:
        dead: list[WebSocket] = []
        sent = 0
        sockets = list(self._channels.get(channel, set()))
        for ws in sockets:
            try:
                await ws.send_text(json.dumps(message))
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)
        return sent

    async def broadcast_all(self, message: dict[str, Any]) -> int:
        total = 0
        for ch in list(self._channels):
            total += await self.broadcast(ch, message)
        return total


manager = ConnectionManager()
