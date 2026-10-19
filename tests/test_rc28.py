"""ICOM RC-28 remote encoder: report decoding, LED reports and the HID bridge.

The input reports below were captured from a real RC-28 on 2026-10-19
(rc28-probe.py); the LED bit assignment comes from rc28-led-probe2.py runs
on the same unit.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from rigplane.web.rc28 import (
    RC28_PRODUCT_ID,
    RC28_VENDOR_ID,
    Rc28Bridge,
    Rc28Decoder,
    Rc28Key,
    Rc28Rotate,
    led_report,
)


def _report(ticks: int, direction: int, keys: int = 0x07) -> list[int]:
    head = [0x01, ticks, 0x00, direction, 0x00, keys, 0x32, 0x31, 0x30]
    return head + [0x00] * (32 - len(head))


def test_clockwise_ticks_are_positive() -> None:
    assert Rc28Decoder().feed(_report(0x1B, 0x01)) == [Rc28Rotate(27)]


def test_counter_clockwise_ticks_are_negative() -> None:
    assert Rc28Decoder().feed(_report(0x02, 0x02)) == [Rc28Rotate(-2)]


def test_key_press_and_release_are_edges() -> None:
    decoder = Rc28Decoder()
    assert decoder.feed(_report(0, 0, keys=0x05)) == [Rc28Key("f1", pressed=True)]
    assert decoder.feed(_report(0, 0, keys=0x05)) == []
    assert decoder.feed(_report(0, 0, keys=0x07)) == [Rc28Key("f1", pressed=False)]


@pytest.mark.parametrize(
    ("keys", "name"), [(0x05, "f1"), (0x03, "f2"), (0x06, "transmit")]
)
def test_each_key_bit(keys: int, name: str) -> None:
    assert Rc28Decoder().feed(_report(0, 0, keys=keys)) == [Rc28Key(name, pressed=True)]


def test_foreign_or_short_report_is_ignored() -> None:
    assert Rc28Decoder().feed([0x02, 0x05, 0x00, 0x01, 0x00, 0x07]) == []
    assert Rc28Decoder().feed([0x01, 0x05]) == []


def test_led_report_is_active_low_without_report_id() -> None:
    report = led_report(tx=True, link=True)
    assert len(report) == 33
    assert report[:3] == [0x00, 0x01, 0x06]
    assert led_report()[:3] == [0x00, 0x01, 0x0F]
    assert led_report(f1=True, f2=True)[2] == 0x09


class _FakeDevice:
    def __init__(self, reports: list[list[int]]) -> None:
        self.reports = list(reports)
        self.writes: list[list[int]] = []
        self.closed = False

    def open_path(self, path: bytes) -> None:
        assert path == b"rc28"

    def read(self, size: int, timeout_ms: int = 0) -> list[int]:
        if self.reports:
            return self.reports.pop(0)
        threading.Event().wait(timeout_ms / 1000)
        return []

    def write(self, data: list[int]) -> int:
        self.writes.append(list(data))
        return len(data)

    def close(self) -> None:
        self.closed = True


class _FakeHid:
    def __init__(self, device: _FakeDevice) -> None:
        self._device = device

    def enumerate(self, vid: int, pid: int) -> list[dict[str, object]]:
        assert (vid, pid) == (RC28_VENDOR_ID, RC28_PRODUCT_ID)
        return [{"path": b"rc28"}]

    def device(self) -> _FakeDevice:
        return self._device


async def test_bridge_publishes_events_and_writes_leds() -> None:
    device = _FakeDevice([_report(3, 0x01), _report(0, 0, keys=0x06)])
    bridge = Rc28Bridge(hid_module=_FakeHid(device), poll_timeout_ms=10)
    queue = bridge.subscribe()
    bridge.start()
    try:
        events = [await asyncio.wait_for(queue.get(), 2) for _ in range(3)]
        assert events[0] == {"type": "status", "connected": True, "available": True}
        assert events[1:] == [
            {"type": "rotate", "ticks": 3},
            {"type": "key", "key": "transmit", "pressed": True},
        ]
        bridge.set_leds(tx=True)
        for _ in range(100):
            if device.writes and device.writes[-1][2] == 0x0E:
                break
            await asyncio.sleep(0.01)
        assert device.writes[-1][:3] == [0x00, 0x01, 0x0E]
    finally:
        await bridge.stop()
    assert device.closed
    assert device.writes[-1][:3] == [0x00, 0x01, 0x0F]


async def test_bridge_without_hid_module_reports_unavailable() -> None:
    bridge = Rc28Bridge(hid_module=None)
    assert bridge.status() == {"type": "status", "connected": False, "available": False}
    bridge.start()
    await bridge.stop()


class _FakeWs:
    def __init__(self, incoming: list[bytes]) -> None:
        self.incoming = list(incoming)
        self.sent: list[dict[str, object]] = []

    async def send_text(self, text: str) -> None:
        import json

        self.sent.append(json.loads(text))

    async def recv(self) -> tuple[int, bytes]:
        await asyncio.sleep(0)
        if not self.incoming:
            raise EOFError
        return 0x1, self.incoming.pop(0)


class _RecordingBridge(Rc28Bridge):
    def __init__(self) -> None:
        super().__init__(hid_module=None)
        self.calls: list[dict[str, bool]] = []

    def set_leds(self, **leds: bool) -> None:  # type: ignore[override]
        self.calls.append(leds)


async def test_handler_sends_status_and_applies_led_requests() -> None:
    from rigplane.web.handlers.rc28 import Rc28Handler

    bridge = _RecordingBridge()
    ws = _FakeWs([b'{"leds": {"tx": true, "link": true, "f1": "yes"}}', b"not json"])
    await Rc28Handler(ws, bridge).run()  # type: ignore[arg-type]
    assert ws.sent[0] == {"type": "status", "connected": False, "available": False}
    assert bridge.calls[0] == {"tx": True, "f1": False, "f2": False, "link": True}
    # The last client leaving turns every LED off.
    assert bridge.calls[-1] == {}


class _HttpWriter:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None


async def _capabilities(bridge: Rc28Bridge) -> list[str]:
    import json

    from rigplane.web.server import WebConfig, WebServer

    server = WebServer(None, WebConfig(host="127.0.0.1", port=0, radio_model="IC-9700"))
    server._rc28 = bridge  # noqa: SLF001
    writer = _HttpWriter()
    await server._handle_http(  # noqa: SLF001
        writer,  # type: ignore[arg-type]
        "GET",
        "/api/v1/capabilities",
        headers={},
        reader=None,
    )
    body = json.loads(bytes(writer.buffer).split(b"\r\n\r\n", 1)[1])
    return list(body["capabilities"])


async def test_capabilities_advertise_rc28_only_with_hidapi() -> None:
    assert "rc28" in await _capabilities(Rc28Bridge(hid_module=object()))
    assert "rc28" not in await _capabilities(Rc28Bridge(hid_module=None))


class _PeerWriter(_HttpWriter):
    def __init__(self, peer: str) -> None:
        super().__init__()
        self._peer = peer

    def get_extra_info(self, name: str, default: object = None) -> object:
        return (self._peer, 50000) if name == "peername" else default

    @property
    def status(self) -> int:
        return int(bytes(self.buffer).split(b" ", 2)[1])


async def _post_transmit(
    body: bytes, *, peer: str = "127.0.0.1", read_only: bool = False
) -> tuple[_PeerWriter, Rc28Bridge, asyncio.Queue[dict[str, object]]]:
    from rigplane.web.server import WebConfig, WebServer

    server = WebServer(
        None,
        WebConfig(host="127.0.0.1", port=0, radio_model="IC-9700", read_only=read_only),
    )
    bridge = Rc28Bridge(hid_module=None)
    server._rc28 = bridge  # noqa: SLF001
    queue = bridge.subscribe()
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()
    writer = _PeerWriter(peer)
    await server._handle_http(  # noqa: SLF001
        writer,  # type: ignore[arg-type]
        "POST",
        "/api/v1/rc28/transmit",
        headers={"content-length": str(len(body))},
        reader=reader,
    )
    return writer, bridge, queue


async def test_local_transmit_input_reaches_rc28_clients() -> None:
    writer, _, queue = await _post_transmit(b'{"pressed": true}')
    assert writer.status == 200
    message = await asyncio.wait_for(queue.get(), 1)
    assert message == {"type": "key", "key": "transmit", "pressed": True}


@pytest.mark.parametrize(
    ("body", "peer", "read_only", "status"),
    [
        (b'{"pressed": true}', "192.168.1.50", False, 403),
        (b'{"pressed": true}', "127.0.0.1", True, 403),
        (b'{"pressed": "yes"}', "127.0.0.1", False, 400),
        (b'{"pressed": true, "x": 1}', "127.0.0.1", False, 400),
    ],
)
async def test_transmit_input_refusals(
    body: bytes, peer: str, read_only: bool, status: int
) -> None:
    writer, _, queue = await _post_transmit(body, peer=peer, read_only=read_only)
    assert writer.status == status
    await asyncio.sleep(0)
    assert queue.empty()
