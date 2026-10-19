"""POST /api/v1/app/shutdown: a local window (RemoteMyRig) asks the server to
stop through the same graceful path as Ctrl+C."""

from __future__ import annotations

import asyncio

import pytest

from rigplane.web.server import WebConfig, WebServer


class _Writer:
    def __init__(self, peer: str) -> None:
        self.buffer = bytearray()
        self._peer = peer

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def get_extra_info(self, name: str, default: object = None) -> object:
        return (self._peer, 50000) if name == "peername" else default

    @property
    def status(self) -> int:
        return int(bytes(self.buffer).split(b" ", 2)[1])


async def _post(server: WebServer, peer: str = "127.0.0.1") -> _Writer:
    writer = _Writer(peer)
    await server._handle_http(  # noqa: SLF001
        writer,  # type: ignore[arg-type]
        "POST",
        "/api/v1/app/shutdown",
        headers={},
        reader=None,
    )
    return writer


def _server(*, app_shutdown: bool) -> tuple[WebServer, list[str]]:
    server = WebServer(
        None,
        WebConfig(
            host="127.0.0.1", port=0, radio_model="IC-9700", app_shutdown=app_shutdown
        ),
    )
    calls: list[str] = []
    server._request_shutdown = lambda: calls.append("stop")  # noqa: SLF001
    return server, calls


async def test_enabled_local_request_triggers_the_graceful_stop() -> None:
    server, calls = _server(app_shutdown=True)
    writer = await _post(server)
    await asyncio.sleep(0)
    assert writer.status == 202
    assert calls == ["stop"]


@pytest.mark.parametrize(
    ("enabled", "peer"), [(False, "127.0.0.1"), (True, "10.0.0.2")]
)
async def test_disabled_or_remote_request_is_refused(enabled: bool, peer: str) -> None:
    server, calls = _server(app_shutdown=enabled)
    writer = await _post(server, peer)
    assert writer.status == 403
    assert calls == []
