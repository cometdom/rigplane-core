"""RemoteMyRig launcher (packaging/remotemyrig/remotemyrig.py): the parts that
run without Windows or a window."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1] / "packaging" / "remotemyrig" / "remotemyrig.py"
)
_spec = importlib.util.spec_from_file_location("remotemyrig", _PATH)
assert _spec is not None and _spec.loader is not None
rmr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rmr)


def test_settings_round_trip_drops_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    rmr.save_settings({**rmr.DEFAULTS, "host": "192.168.1.25", "junk": 1}, path)
    loaded = rmr.load_settings(path)
    assert loaded["host"] == "192.168.1.25"
    assert "junk" not in loaded
    assert rmr.load_settings(tmp_path / "missing.json") == rmr.DEFAULTS


def test_setup_is_needed_until_a_host_is_saved() -> None:
    assert rmr.needs_setup(dict(rmr.DEFAULTS))
    assert not rmr.needs_setup({**rmr.DEFAULTS, "host": "192.168.1.25"})


def test_server_command_and_environment() -> None:
    settings = {**rmr.DEFAULTS, "host": "192.168.1.25", "user": "op"}
    assert rmr.server_command(settings) == [
        "--model",
        "IC-9700",
        "web",
        "--listen",
        "127.0.0.1",
        "--port",
        "8080",
    ]
    env = rmr.server_environment(settings, "secret")
    assert env["RIGPLANE_APP_SHUTDOWN"] == "1"
    assert (env["ICOM_HOST"], env["ICOM_USER"], env["ICOM_PASS"]) == (
        "192.168.1.25",
        "op",
        "secret",
    )


def test_serial_radio_passes_extra_arguments_before_the_command() -> None:
    settings = {
        **rmr.DEFAULTS,
        "model": "IC-7300",
        "extra_args": ["--backend", "serial", "--serial-port", "COM3"],
    }
    command = rmr.server_command(settings)
    assert command[:6] == [
        "--model",
        "IC-7300",
        "--backend",
        "serial",
        "--serial-port",
        "COM3",
    ]
    assert command[6] == "web"


def test_setup_page_escapes_stored_values() -> None:
    page = rmr.setup_page({**rmr.DEFAULTS, "user": "a'><script>"})
    assert "a'><script>" not in page
    assert "a&#x27;&gt;&lt;script&gt;" in page


def test_footswitch_key_table() -> None:
    assert rmr.FOOTSWITCH_KEYS["Insert"] == 0x2D
    assert rmr.FOOTSWITCH_KEYS["F13"] == 0x7C
    assert rmr.FOOTSWITCH_KEYS["F24"] == 0x87
