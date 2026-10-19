"""RC-28 channel (/api/v1/rc28).

Server → client: the bridge's JSON messages (``status``, ``rotate``, ``key``).
Client → server: ``{"leds": {"tx": bool, "f1": bool, "f2": bool, "link": bool}}``.
The LEDs go dark when the last client leaves (``Rc28Bridge.unsubscribe``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from ..rc28 import Rc28Bridge  # noqa: TID251
from ..websocket import WS_OP_TEXT, WebSocketConnection  # noqa: TID251

__all__ = ["Rc28Handler"]

_LED_NAMES = ("tx", "f1", "f2", "link")


class Rc28Handler:
    def __init__(self, ws: WebSocketConnection, bridge: Rc28Bridge) -> None:
        self._ws = ws
        self._bridge = bridge

    async def run(self) -> None:
        queue = self._bridge.subscribe()
        try:
            await self._ws.send_text(json.dumps(self._bridge.status()))
            sender = asyncio.create_task(self._forward(queue))
            try:
                while True:
                    opcode, payload = await self._ws.recv()
                    if opcode == WS_OP_TEXT:
                        self._apply(payload)
            except EOFError:
                pass
            finally:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender
        finally:
            self._bridge.unsubscribe(queue)

    async def _forward(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        while True:
            message = await queue.get()
            await self._ws.send_text(json.dumps(message))

    def _apply(self, payload: bytes) -> None:
        try:
            message = json.loads(payload)
        except ValueError:
            return
        leds = message.get("leds") if isinstance(message, dict) else None
        if not isinstance(leds, dict):
            return
        self._bridge.set_leds(**{name: leds.get(name) is True for name in _LED_NAMES})
