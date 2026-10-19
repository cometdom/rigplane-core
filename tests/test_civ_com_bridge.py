"""CI-V COM bridge: a program on a virtual COM port shares the radio."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rigplane.web.civ_com_bridge import (
    CivBridgeManager,
    CivComBridge,
    take_civ_frames,
)

RADIO = 0xA2


class _Tap:
    def __init__(self, taps: list, cb) -> None:  # type: ignore[no-untyped-def]
        self._taps, self._cb = taps, cb

    def close(self) -> None:
        self._taps.remove(self._cb)


class _Radio:
    _radio_addr = RADIO

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.taps: list = []

    def add_civ_tap(self, cb):  # type: ignore[no-untyped-def]
        self.taps.append(cb)
        return _Tap(self.taps, cb)

    async def send_civ_raw_fire_and_forget(self, frame: bytes) -> None:
        self.sent.append(frame)

    def emit(self, frame: bytes) -> None:
        for tap in list(self.taps):
            tap(frame)


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    def close(self) -> None:
        pass


async def _bridge(
    allow_tx: bool = False,
) -> tuple[CivComBridge, _Radio, asyncio.StreamReader, _Writer]:
    radio, reader, writer = _Radio(), asyncio.StreamReader(), _Writer()

    async def open_port(port: str):  # type: ignore[no-untyped-def]
        return reader, writer

    bridge = CivComBridge(
        radio, "COM11", alias=0xE1, allow_tx=allow_tx, open_port=open_port
    )
    await bridge.start()
    return bridge, radio, reader, writer


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def test_frame_splitter_keeps_partials_and_drops_noise() -> None:
    buf = bytearray(b"\x00\xfe\xfe\xa2\xe0\x03\xfd\xfe\xfe\xa2")
    assert take_civ_frames(buf) == [b"\xfe\xfe\xa2\xe0\x03\xfd"]
    assert buf == bytearray(b"\xfe\xfe\xa2")
    buf.extend(b"\xe0\x04\xfd")
    assert take_civ_frames(buf) == [b"\xfe\xfe\xa2\xe0\x04\xfd"]


async def test_request_is_relayed_under_the_alias_and_reply_comes_back() -> None:
    bridge, radio, reader, writer = await _bridge()
    reader.feed_data(b"\xfe\xfe\xa2\xe0\x03")
    reader.feed_data(b"\xfd")
    await _settle()
    assert radio.sent == [b"\xfe\xfe\xa2\xe1\x03\xfd"]
    radio.emit(b"\xfe\xfe\xe1\xa2\x03\x00\x00\x30\x44\x01\xfd")  # reply to the alias
    radio.emit(b"\xfe\xfe\xe0\xa2\x03\x00\x00\x30\x44\x01\xfd")  # rigplane's own reply
    radio.emit(b"\xfe\xfe\x00\xa2\x00\x00\x00\x30\x44\x01\xfd")  # transceive broadcast
    assert bytes(writer.data) == (
        b"\xfe\xfe\xe0\xa2\x03\x00\x00\x30\x44\x01\xfd"
        b"\xfe\xfe\x00\xa2\x00\x00\x00\x30\x44\x01\xfd"
    )
    await bridge.stop()
    assert radio.taps == []


async def test_transmit_commands_are_refused_unless_allowed() -> None:
    bridge, radio, reader, writer = await _bridge()
    reader.feed_data(b"\xfe\xfe\xa2\xe0\x1c\x00\x01\xfd")  # PTT on
    reader.feed_data(b"\xfe\xfe\xa2\xe0\x1c\x00\xfd")  # PTT read: allowed
    await _settle()
    assert bytes(writer.data) == b"\xfe\xfe\xe0\xa2\xfa\xfd"
    assert radio.sent == [b"\xfe\xfe\xa2\xe1\x1c\x00\xfd"]
    await bridge.stop()

    bridge, radio, reader, writer = await _bridge(allow_tx=True)
    reader.feed_data(b"\xfe\xfe\xa2\xe0\x1c\x00\x01\xfd")
    await _settle()
    assert radio.sent == [b"\xfe\xfe\xa2\xe1\x1c\x00\x01\xfd"]
    await bridge.stop()


async def test_manager_saves_config_and_reports_status(tmp_path: Path) -> None:
    radio = _Radio()

    async def open_port(port: str):  # type: ignore[no-untyped-def]
        if port == "COM99":
            raise OSError("could not open port")
        return asyncio.StreamReader(), _Writer()

    manager = CivBridgeManager(lambda: radio, tmp_path / "b.json", open_port=open_port)
    await manager.apply(
        [
            {"port": "COM11", "enabled": True, "allowTx": False},
            {"port": "COM99", "enabled": True, "allowTx": False},
            {"port": "COM13", "enabled": False, "allowTx": True},
        ]
    )
    status = {s["port"]: s["status"] for s in manager.status()}
    assert status["COM11"] == "running"
    assert status["COM99"].startswith("error")
    assert status["COM13"] == "stopped"
    await manager.stop()
    assert radio.taps == []


async def test_bridged_frames_leave_no_unclaimed_ack_for_the_unkey() -> None:
    """A bridged frame is answered to the bridge's own address, which rigplane
    never routes; tracking it as an ACK sink made every later blocking write
    (the PTT unkey) doubt its own FB and settle UNCERTAIN."""
    from rigplane.radio import IcomRadio
    from test_radio import MockTransport

    transport = MockTransport()
    radio = IcomRadio("192.168.1.104", timeout=0.2, model="IC-9700")
    radio._civ_transport = transport
    radio._ctrl_transport = transport
    radio._connected = True
    try:
        await radio.send_civ_raw_fire_and_forget(b"\xfe\xfe\xa2\xe1\x0f\x01\xfd")
        tracker = radio._civ_request_tracker
        tracker.drop_ack_sinks()
        assert tracker.ack_unclaimed_at is None
        # rigplane's own fire-and-forget writes keep their sink.
        await radio.send_civ_raw_fire_and_forget(b"\xfe\xfe\xa2\xe0\x0f\x01\xfd")
        tracker.drop_ack_sinks()
        assert tracker.ack_unclaimed_at is not None
    finally:
        radio._connected = False
