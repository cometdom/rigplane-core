"""HTTP route for named radio-menu toggles (GET/PUT /api/v1/radio/menu-toggles)."""

from __future__ import annotations

import asyncio
import json

import pytest

from rigplane.web.server import WebConfig, WebServer

_PATH = "/api/v1/radio/menu-toggles"


class _Writer:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    @property
    def status(self) -> int:
        return int(self.buffer.split(b" ", 2)[1])

    @property
    def payload(self) -> dict[str, object]:
        return json.loads(self.buffer.split(b"\r\n\r\n", 1)[1] or b"{}")


def _reader(payload: object) -> tuple[asyncio.StreamReader, dict[str, str]]:
    body = json.dumps(payload).encode()
    reader = asyncio.StreamReader()
    reader.feed_data(body)
    reader.feed_eof()
    return reader, {"content-length": str(len(body))}


class _Radio:
    def __init__(self) -> None:
        self.values = {"ext_preamp_144": True, "ext_preamp_430": False}
        self.calls: list[tuple[str, ...]] = []

    def menu_toggles(self) -> tuple[str, ...]:
        return tuple(self.values)

    async def get_menu_toggle(self, name: str) -> bool:
        self.calls.append(("get", name))
        return self.values[name]

    async def set_menu_toggle(self, name: str, enabled: bool) -> None:
        self.calls.append(("set", name, str(enabled)))
        self.values[name] = enabled


def _server(radio: _Radio | None, *, read_only: bool = False) -> WebServer:
    server = WebServer(None, WebConfig(host="127.0.0.1", port=0, read_only=read_only))
    server._radio = radio  # type: ignore[assignment]  # noqa: SLF001
    return server


async def _call(server: WebServer, method: str, body: object | None = None) -> _Writer:
    writer = _Writer()
    reader, headers = _reader(body) if body is not None else (None, {})
    await server._handle_http(  # noqa: SLF001
        writer,  # type: ignore[arg-type]
        method,
        _PATH,
        headers=headers,
        reader=reader,
    )
    return writer


@pytest.mark.asyncio
async def test_get_lists_each_declared_toggle_with_its_value() -> None:
    writer = await _call(_server(_Radio()), "GET")
    assert writer.status == 200
    assert writer.payload == {
        "toggles": [
            {"name": "ext_preamp_144", "on": True},
            {"name": "ext_preamp_430", "on": False},
        ]
    }


@pytest.mark.asyncio
async def test_put_writes_then_reads_back() -> None:
    radio = _Radio()
    writer = await _call(_server(radio), "PUT", {"name": "ext_preamp_430", "on": True})
    assert writer.status == 200
    assert writer.payload == {"name": "ext_preamp_430", "on": True}
    assert radio.calls == [("set", "ext_preamp_430", "True"), ("get", "ext_preamp_430")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"name": "ext_preamp_430"},
        {"name": "ext_preamp_430", "on": "yes"},
        {"name": "quick_split", "on": True},
        {"name": "ext_preamp_430", "on": True, "extra": 1},
    ],
)
async def test_put_rejects_a_malformed_or_unknown_request(body: object) -> None:
    radio = _Radio()
    writer = await _call(_server(radio), "PUT", body)
    assert writer.status == 400
    assert radio.calls == []


@pytest.mark.asyncio
async def test_put_is_refused_in_read_only_mode() -> None:
    radio = _Radio()
    writer = await _call(
        _server(radio, read_only=True), "PUT", {"name": "ext_preamp_430", "on": True}
    )
    assert writer.status == 403
    assert radio.calls == []


@pytest.mark.asyncio
async def test_without_a_radio_the_route_is_unavailable() -> None:
    writer = await _call(_server(None), "GET")
    assert writer.status == 503
