"""IC-9700 per-band External P.AMP menu toggles (CI-V 1A 05 0093/0094/0095).

IC-9700 CI-V Reference Guide p.7: 0093/0094/0095 = SET > Connectors >
External P.AMP > 144M/430M/1200M, 00 = OFF, 01 = ON.
"""

from __future__ import annotations

import pytest

from rigplane.commands import CONTROLLER_ADDR, build_civ_frame
from rigplane.exceptions import CommandError
from rigplane.radio import IcomRadio

from test_radio import MockTransport, _wrap_civ_in_udp

_IC9700 = 0xA2


def _from_radio(command: int, sub: int | None = None, data: bytes = b"") -> bytes:
    return _wrap_civ_in_udp(
        build_civ_frame(CONTROLLER_ADDR, _IC9700, command, sub=sub, data=data)
    )


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


def test_ic9700_declares_the_three_external_preamp_toggles(radio: IcomRadio) -> None:
    assert radio.menu_toggles() == (
        "ext_preamp_144",
        "ext_preamp_430",
        "ext_preamp_1200",
    )


async def test_get_menu_toggle_reads_the_430_setting(
    radio: IcomRadio, mock_transport: MockTransport
) -> None:
    mock_transport.queue_response_on_send(1, _from_radio(0x1A, 0x05, b"\x00\x94\x01"))
    assert await radio.get_menu_toggle("ext_preamp_430") is True
    assert any(b"\x1a\x05\x00\x94\xfd" in p for p in mock_transport.sent_packets)


async def test_set_menu_toggle_writes_and_waits_for_ack(
    radio: IcomRadio, mock_transport: MockTransport
) -> None:
    mock_transport.queue_response_on_send(1, _from_radio(0xFB))
    await radio.set_menu_toggle("ext_preamp_1200", False)
    assert any(b"\x1a\x05\x00\x95\x00\xfd" in p for p in mock_transport.sent_packets)


async def test_set_menu_toggle_raises_when_the_radio_refuses(
    radio: IcomRadio, mock_transport: MockTransport
) -> None:
    mock_transport.queue_response_on_send(1, _from_radio(0xFA))
    with pytest.raises(CommandError):
        await radio.set_menu_toggle("ext_preamp_144", True)


async def test_menu_toggle_outside_the_allowlist_is_refused(radio: IcomRadio) -> None:
    with pytest.raises(ValueError):
        await radio.get_menu_toggle("quick_split")
