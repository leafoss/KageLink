from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass(slots=True)
class RuntimeStatus:
    game_online: bool = False
    game_foreground: bool = False
    chat_found: bool = False
    ooc_input_found: bool = False
    ic_input_found: bool = False
    chat_hwnd: int | None = None
    ooc_input_hwnd: int | None = None
    ic_input_hwnd: int | None = None
    last_chat_update: float | None = None
    last_send: float | None = None
    last_error: str | None = None
    send_state: str = "idle"

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_online": self.game_online,
            "game_foreground": self.game_foreground,
            "chat_found": self.chat_found,
            "ooc_input_found": self.ooc_input_found,
            "ic_input_found": self.ic_input_found,
            "chat_hwnd": self.chat_hwnd,
            "ooc_input_hwnd": self.ooc_input_hwnd,
            "ic_input_hwnd": self.ic_input_hwnd,
            # Backward-compatible aliases for older mobile/web clients.
            "input_found": self.ooc_input_found,
            "input_hwnd": self.ooc_input_hwnd,
            "last_chat_update": self.last_chat_update,
            "last_send": self.last_send,
            "last_error": self.last_error,
            "send_state": self.send_state,
            "server_time": time.time(),
        }


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        if stale:
            async with self._lock:
                for websocket in stale:
                    self._connections.discard(websocket)
