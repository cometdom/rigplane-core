"""IC-9700 digital voice/data modes (DV 0x17, DD 0x22).

IC-9700 CI-V Reference Guide p.13, "Operating mode": 17 = DV, 22 = DD.
"""

from __future__ import annotations

from rigplane.commands._frame import parse_civ_frame
from rigplane.commands.mode import parse_mode_response
from rigplane.profiles import resolve_radio_profile
from rigplane.types import Mode


def test_mode_reply_in_dd_parses() -> None:
    frame = parse_civ_frame(bytes.fromhex("fefee0a20422fd"))
    assert parse_mode_response(frame) == (Mode.DD, None)


def test_profile_offers_dv_and_dd_with_fixed_width() -> None:
    profile = resolve_radio_profile(model="IC-9700")
    assert {"DV", "DD"} <= set(profile.modes)
    for mode in ("DV", "DD"):
        rule = profile.resolve_filter_rule(mode, data_mode=0)
        assert rule is not None and rule.fixed, mode
