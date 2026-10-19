"""RemoteMyRig launcher (packaging/remotemyrig/remotemyrig.py): the parts that
run without Windows or a window."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1] / "packaging" / "remotemyrig" / "remotemyrig.py"
)
_spec = importlib.util.spec_from_file_location("remotemyrig", _PATH)
assert _spec is not None and _spec.loader is not None
rmr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rmr)

LAN = {
    "name": "IC-9700",
    "model": "IC-9700",
    "connection": "lan",
    "host": "192.168.1.25",
    "user": "op",
}
USB = {
    "name": "IC-7300 USB",
    "model": "IC-7300",
    "connection": "usb",
    "serial_port": "COM3",
    "serial_baud": "19200",
}


def _settings(*radios: dict[str, object]) -> dict[str, object]:
    return {**rmr.DEFAULTS, "radios": [rmr.normalize_radio(r) for r in radios]}


def test_single_radio_settings_from_before_are_migrated(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "model": "IC-9700",
                "host": "192.168.1.25",
                "user": "op",
                "footswitch_key": "F13",
            }
        )
    )
    settings = rmr.load_settings(path)
    assert settings["footswitch_key"] == "F13"
    assert [(r["name"], r["connection"], r["host"]) for r in settings["radios"]] == [
        ("IC-9700", "lan", "192.168.1.25")
    ]


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    rmr.save_settings(_settings(LAN, USB), path)
    loaded = rmr.load_settings(path)
    assert [r["name"] for r in loaded["radios"]] == ["IC-9700", "IC-7300 USB"]
    assert loaded["radios"][1]["serial_baud"] == 19200
    assert rmr.load_settings(tmp_path / "missing.json")["radios"] == []


def test_start_choice() -> None:
    assert rmr.start_choice(_settings())[0] == "setup"
    page, radio = rmr.start_choice(_settings(LAN))
    assert page == "launch" and radio is not None and radio["name"] == "IC-9700"
    assert rmr.start_choice(_settings(LAN, USB))[0] == "choose"


def test_lan_command_and_environment() -> None:
    settings = _settings(LAN)
    radio = settings["radios"][0]  # type: ignore[index]
    assert rmr.server_command(settings, radio) == [
        "--model",
        "IC-9700",
        "web",
        "--listen",
        "127.0.0.1",
        "--port",
        "8080",
    ]
    env = rmr.server_environment(radio, "secret")
    assert (env["ICOM_HOST"], env["ICOM_USER"], env["ICOM_PASS"]) == (
        "192.168.1.25",
        "op",
        "secret",
    )
    assert env["RIGPLANE_APP_SHUTDOWN"] == "1"


def test_usb_command_uses_the_serial_backend_and_no_network_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ICOM_HOST", "192.168.1.25")
    settings = _settings({**USB, "rx_device": "USB Audio CODEC"})
    radio = settings["radios"][0]  # type: ignore[index]
    command = rmr.server_command(settings, radio)
    assert command[: command.index("web")] == [
        "--model",
        "IC-7300",
        "--backend",
        "serial",
        "--serial-port",
        "COM3",
        "--serial-baud",
        "19200",
        "--rx-device",
        "USB Audio CODEC",
    ]
    assert "ICOM_HOST" not in rmr.server_environment(radio, "")


def test_apply_form_validates_and_replaces_the_edited_radio() -> None:
    settings = _settings(LAN)
    radio, error = rmr.apply_form(settings, "", {**USB, "serial_port": ""})
    assert radio is None and "COM" in error
    radio, error = rmr.apply_form(settings, "", {**USB, "name": "IC-9700"})
    assert radio is None and "nom" in error
    radio, error = rmr.apply_form(
        settings, "IC-9700", {**LAN, "name": "IC-9700 LAN", "footswitch_key": "F13"}
    )
    assert error == "" and radio is not None
    assert [r["name"] for r in settings["radios"]] == ["IC-9700 LAN"]  # type: ignore[union-attr]
    assert settings["footswitch_key"] == "F13"


def test_pages_escape_stored_values() -> None:
    settings = _settings({**LAN, "name": "a'><script>x</script>"})
    page = rmr.setup_page(settings, settings["radios"][0])  # type: ignore[index]
    choose = rmr.choose_page(settings)
    for html in (page, choose):
        assert "<script>x</script>" not in html
    assert "a&#x27;&gt;&lt;script&gt;" in page


def test_footswitch_key_table() -> None:
    assert rmr.FOOTSWITCH_KEYS["Insert"] == 0x2D
    assert rmr.FOOTSWITCH_KEYS["F13"] == 0x7C
    assert rmr.FOOTSWITCH_KEYS["F24"] == 0x87
