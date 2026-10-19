"""IC-9700 repeater shift (CI-V 0F) and SSB TX bandwidth read-back (16 58).

IC-9700 CI-V Reference Guide, command 0F: reads 11 = DUP-, 12 = DUP+, and
sets 10 = simplex, 11 = DUP-, 12 = DUP+. Command 16 58: SSB TX bandwidth,
00 = WIDE, 01 = MID, 02 = NAR.
"""

from __future__ import annotations

import pytest

from rigplane.commands import CONTROLLER_ADDR, build_civ_frame
from rigplane.core.types import RepeaterShiftDirection
from rigplane.profiles import resolve_radio_profile
from rigplane.radio import IcomRadio
from rigplane.runtime._state_queries import build_state_queries

from _acquisition_query_helpers import acquisition_query
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


def test_profile_declares_repeater_shift() -> None:
    profile = resolve_radio_profile(model="IC-9700")
    assert "repeater_shift" in profile.capabilities
    assert "repeater_shift_ars" not in profile.capabilities


async def test_set_dup_plus_sends_0f_12(
    radio: IcomRadio, mock_transport: MockTransport
) -> None:
    mock_transport.queue_response_on_send(1, _from_radio(0xFB))
    await radio.set_repeater_shift(RepeaterShiftDirection.PLUS)
    assert any(b"\x0f\x12\xfd" in p for p in mock_transport.sent_packets)


async def test_read_dup_minus(radio: IcomRadio, mock_transport: MockTransport) -> None:
    mock_transport.queue_response_on_send(1, _from_radio(0x0F, data=b"\x11"))
    assert await radio.get_repeater_shift() == RepeaterShiftDirection.MINUS


def test_repeater_shift_and_tbw_are_polled() -> None:
    queries = build_state_queries(resolve_radio_profile(model="IC-9700"))
    assert acquisition_query(0x0F) in queries
    assert acquisition_query(0x16, sub=0x58) in queries


def test_mod_input_sources_include_lan() -> None:
    # IC-9700 CI-V Reference Guide, 1A 05 0115/0116: 05 = LAN.
    profile = resolve_radio_profile(model="IC-9700")
    assert profile.data_mode_inputs is not None
    assert (5, "LAN") in profile.data_mode_inputs


def test_s_meter_is_calibrated() -> None:
    # IC-9700 CI-V Reference Guide, 15 02: 0000=S0, 0120=S9, 0241=S9+60 dB.
    profile = resolve_radio_profile(model="IC-9700")
    assert profile.meter_calibrations is not None
    points = [
        (p["raw"], p["actual"], p["label"])
        for p in profile.meter_calibrations["s_meter"]
    ]
    assert points == [(0, -54.0, "S0"), (120, 0.0, "S9"), (241, 60.0, "S9+60")]
