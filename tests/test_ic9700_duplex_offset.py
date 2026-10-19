"""IC-9700 duplex offset (CI-V 0C read, 0D set).

IC-9700 CI-V Reference Guide, "Duplex Offset frequency setting": three
bytes, each two BCD digits: (1 kHz, 100 Hz), (100 kHz, 10 kHz),
(10 MHz, 1 MHz).
"""

from __future__ import annotations

import pytest

from rigplane.commands import CONTROLLER_ADDR, build_civ_frame
from rigplane.commands.vfo import decode_duplex_offset, encode_duplex_offset
from rigplane.radio import IcomRadio

from test_radio import MockTransport, _wrap_civ_in_udp

_IC9700 = 0xA2


@pytest.mark.parametrize(
    ("hz", "wire"),
    [
        (600_000, b"\x00\x60\x00"),
        (1_600_000, b"\x00\x60\x01"),
        (7_600_000, b"\x00\x60\x07"),
        (12_345_600, b"\x56\x34\x12"),
    ],
)
def test_offset_encoding_round_trips(hz: int, wire: bytes) -> None:
    assert encode_duplex_offset(hz) == wire
    assert decode_duplex_offset(wire) == hz


@pytest.mark.parametrize("hz", [-100, 50, 100_000_000])
def test_offset_outside_the_wire_range_is_refused(hz: int) -> None:
    with pytest.raises(ValueError):
        encode_duplex_offset(hz)


@pytest.fixture
def mock_transport() -> MockTransport:
    return MockTransport()


@pytest.fixture
def radio(mock_transport: MockTransport):
    r = IcomRadio("192.168.1.104", timeout=0.2, model="IC-9700")
    r._civ_transport = mock_transport
    r._ctrl_transport = mock_transport
    r._connected = True
    yield r
    r._connected = False


async def test_set_offset_sends_0d(
    radio: IcomRadio, mock_transport: MockTransport
) -> None:
    mock_transport.queue_response_on_send(
        1, _wrap_civ_in_udp(build_civ_frame(CONTROLLER_ADDR, _IC9700, 0xFB))
    )
    await radio.set_duplex_offset(1_600_000)
    assert any(b"\x0d\x00\x60\x01\xfd" in p for p in mock_transport.sent_packets)


async def test_get_offset_reads_0c(
    radio: IcomRadio, mock_transport: MockTransport
) -> None:
    mock_transport.queue_response_on_send(
        1,
        _wrap_civ_in_udp(
            build_civ_frame(CONTROLLER_ADDR, _IC9700, 0x0C, data=b"\x00\x60\x00")
        ),
    )
    assert await radio.get_duplex_offset() == 600_000
