"""CI-V over a (virtual) COM port, shared with rigplane.

A logging or contest program opens one end of a com0com pair and talks
Icom CI-V to it as if the radio were attached; rigplane opens the other end.
Each bridge relays the program's frames under its own controller address
(``alias``), so the radio's replies to it never mix with rigplane's, and
hands the replies back with the program's own address restored. Transceive
broadcasts (``to == 0x00``) are forwarded too, so the program follows
changes made elsewhere.

Commands that make the radio transmit (PTT set ``1C 00 xx``, tuner start
``1C 01 xx``, CW send ``17``) are refused with a NAK unless ``allow_tx``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

__all__ = [
    "CivBridgeManager",
    "CivComBridge",
    "default_bridge_config_path",
    "take_civ_frames",
]

logger = logging.getLogger(__name__)

_PREAMBLE = b"\xfe\xfe"
_NAK = 0xFA
FIRST_ALIAS = 0xE1

OpenPort = Callable[[str], Awaitable[tuple[asyncio.StreamReader, Any]]]


async def _open_serial(port: str) -> tuple[asyncio.StreamReader, Any]:
    import serial_asyncio  # type: ignore[import-untyped]

    reader, writer = await serial_asyncio.open_serial_connection(
        url=port, baudrate=115200
    )
    return reader, writer


def take_civ_frames(buffer: bytearray) -> list[bytes]:
    """Remove and return the complete ``FE FE … FD`` frames in ``buffer``.

    Bytes before a preamble are dropped; a trailing partial frame stays.
    """
    frames: list[bytes] = []
    while True:
        start = buffer.find(_PREAMBLE)
        if start < 0:
            # Keep a lone trailing FE: it may start the next preamble.
            del buffer[: len(buffer) - (1 if buffer.endswith(b"\xfe") else 0)]
            return frames
        end = buffer.find(b"\xfd", start + 2)
        if end < 0:
            del buffer[:start]
            return frames
        frames.append(bytes(buffer[start : end + 1]))
        del buffer[: end + 1]


def _causes_transmit(frame: bytes) -> bool:
    command = frame[4]
    if command == 0x17:
        return True
    # 1C 00 / 1C 01 with a data byte set PTT / start the tuner; without
    # one they are reads.
    return command == 0x1C and len(frame) >= 8 and frame[5] in (0x00, 0x01)


class CivComBridge:
    def __init__(
        self,
        radio: Any,
        port: str,
        *,
        alias: int,
        allow_tx: bool = False,
        open_port: OpenPort = _open_serial,
    ) -> None:
        self.port = port
        self.allow_tx = allow_tx
        self.status = "stopped"
        self._radio = radio
        self._alias = alias
        self._open_port = open_port
        self._client_addr = 0xE0
        self._writer: Any = None
        self._task: asyncio.Task[None] | None = None
        self._tap: Any = None

    @property
    def _radio_addr(self) -> int:
        return int(getattr(self._radio, "_radio_addr", 0))

    async def start(self) -> None:
        try:
            reader, writer = await self._open_port(self.port)
        except Exception as exc:  # noqa: BLE001 - reported to the operator
            self.status = f"error: {exc}"
            logger.warning("civ-bridge %s: %s", self.port, exc)
            return
        self._writer = writer
        self._tap = self._radio.add_civ_tap(self._on_radio_frame)
        self._task = asyncio.create_task(self._read_loop(reader))
        self.status = "running"
        logger.info("civ-bridge %s: running (alias 0x%02X)", self.port, self._alias)

    async def stop(self) -> None:
        if self._tap is not None:
            self._tap.close()
            self._tap = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()
            self._writer = None
        self.status = "stopped"

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        buffer = bytearray()
        try:
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    break
                buffer.extend(chunk)
                for frame in take_civ_frames(buffer):
                    await self._from_client(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - port vanished
            self.status = f"error: {exc}"
            logger.warning("civ-bridge %s: %s", self.port, exc)

    def _write(self, frame: bytes) -> None:
        if self._writer is not None:
            self._writer.write(frame)

    async def _from_client(self, frame: bytes) -> None:
        if len(frame) < 6 or frame[2] != self._radio_addr:
            return
        self._client_addr = frame[3]
        if not self.allow_tx and _causes_transmit(frame):
            self._write(bytes([0xFE, 0xFE, frame[3], frame[2], _NAK, 0xFD]))
            return
        relayed = bytearray(frame)
        relayed[3] = self._alias
        try:
            await self._radio.send_civ_raw_fire_and_forget(bytes(relayed))
        except Exception as exc:  # noqa: BLE001 - radio not connected
            logger.debug("civ-bridge %s: not relayed: %s", self.port, exc)

    def _on_radio_frame(self, frame: bytes) -> None:
        if frame[2] == self._alias:
            reply = bytearray(frame)
            reply[2] = self._client_addr
            self._write(bytes(reply))
        elif frame[2] == 0x00:
            self._write(frame)


def default_bridge_config_path() -> Path:
    import platformdirs

    return Path(platformdirs.user_data_path("rigplane")) / "civ-com-bridges.json"


class CivBridgeManager:
    """The configured bridges: ``[{port, enabled, allowTx}]`` in a JSON file."""

    def __init__(
        self,
        radio_getter: Callable[[], Any],
        path: Path,
        *,
        open_port: OpenPort = _open_serial,
    ) -> None:
        self._radio_getter = radio_getter
        self._path = path
        self._open_port = open_port
        self._bridges: list[CivComBridge] = []
        self._lock = threading.Lock()

    def config(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return (
            [
                {
                    "port": str(item["port"]),
                    "enabled": item.get("enabled") is not False,
                    "allowTx": item.get("allowTx") is True,
                }
                for item in data
                if isinstance(item, dict) and isinstance(item.get("port"), str)
            ]
            if isinstance(data, list)
            else []
        )

    def status(self) -> list[dict[str, Any]]:
        running = {bridge.port: bridge.status for bridge in self._bridges}
        return [
            {**item, "status": running.get(item["port"], "stopped")}
            for item in self.config()
        ]

    async def apply(self, config: list[dict[str, Any]] | None = None) -> None:
        """Save ``config`` (when given) and restart the bridges from it."""
        if config is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        await self.stop()
        radio = self._radio_getter()
        if radio is None or not callable(getattr(radio, "add_civ_tap", None)):
            return
        alias = FIRST_ALIAS
        for item in self.config():
            if not item["enabled"]:
                continue
            bridge = CivComBridge(
                radio,
                item["port"],
                alias=alias,
                allow_tx=item["allowTx"],
                open_port=self._open_port,
            )
            alias += 1
            await bridge.start()
            self._bridges.append(bridge)

    async def stop(self) -> None:
        bridges, self._bridges = self._bridges, []
        for bridge in bridges:
            await bridge.stop()
