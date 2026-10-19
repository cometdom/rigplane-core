"""Settings routes for CI-V COM bridges and com0com pairs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from rigplane.web import com0com
from rigplane.web.civ_com_bridge import CivBridgeManager
from rigplane.web.server import WebConfig, WebServer


class _Writer:
    def __init__(self, peer: str) -> None:
        self.buffer = bytearray()
        self._peer = peer

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    def get_extra_info(self, name: str, default: object = None) -> object:
        return (self._peer, 50000) if name == "peername" else default

    @property
    def status(self) -> int:
        return int(bytes(self.buffer).split(b" ", 2)[1])

    @property
    def payload(self) -> dict[str, object]:
        return json.loads(bytes(self.buffer).split(b"\r\n\r\n", 1)[1] or b"{}")


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WebServer:
    async def no_pairs() -> list[dict[str, str]]:
        return [{"a": "COM10", "b": "COM11"}]

    monkeypatch.setattr(com0com, "list_pairs", no_pairs)
    srv = WebServer(None, WebConfig(host="127.0.0.1", port=0, radio_model="IC-9700"))
    srv._civ_bridges = CivBridgeManager(lambda: None, tmp_path / "b.json")  # noqa: SLF001
    return srv


async def _call(
    server: WebServer,
    method: str,
    path: str,
    body: object = None,
    peer: str = "127.0.0.1",
) -> _Writer:
    writer = _Writer(peer)
    reader, headers = None, {}
    if body is not None:
        data = json.dumps(body).encode()
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        headers = {"content-length": str(len(data))}
    await server._handle_http(writer, method, path, headers=headers, reader=reader)  # type: ignore[arg-type]  # noqa: SLF001
    return writer


async def test_put_saves_bridges_and_get_reports_them(server: WebServer) -> None:
    put = await _call(
        server,
        "PUT",
        "/api/v1/civ-bridges",
        {"bridges": [{"port": "COM11", "allowTx": True}]},
    )
    assert put.status == 200
    got = await _call(server, "GET", "/api/v1/civ-bridges")
    assert got.payload["bridges"] == [
        {"port": "COM11", "enabled": True, "allowTx": True, "status": "stopped"}
    ]
    assert got.payload["pairs"] == [{"a": "COM10", "b": "COM11"}]


@pytest.mark.parametrize(
    ("body", "peer", "status"),
    [
        ({"bridges": [{"port": "COM11"}]}, "192.168.1.7", 403),
        ({"bridges": [{"port": "/dev/ttyS0"}]}, "127.0.0.1", 400),
        ({"bridges": [{"port": "COM11"}, {"port": "COM11"}]}, "127.0.0.1", 400),
    ],
)
async def test_put_refusals(
    server: WebServer, body: object, peer: str, status: int
) -> None:
    assert (
        await _call(server, "PUT", "/api/v1/civ-bridges", body, peer)
    ).status == status


async def test_pair_creation_is_local_and_validated(
    server: WebServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []

    async def create(a: str, b: str) -> int:
        if not (com0com.valid_port(a) and com0com.valid_port(b)):
            raise ValueError("bad names")
        calls.append((a, b))
        return 0

    monkeypatch.setattr(com0com, "create_pair", create)
    ok = await _call(
        server, "POST", "/api/v1/com0com/pairs", {"a": "COM20", "b": "COM21"}
    )
    assert (ok.status, ok.payload["code"], calls) == (200, 0, [("COM20", "COM21")])
    assert (
        await _call(server, "POST", "/api/v1/com0com/pairs", {"a": "X", "b": "COM21"})
    ).status == 400
    remote = await _call(
        server,
        "POST",
        "/api/v1/com0com/pairs",
        {"a": "COM20", "b": "COM21"},
        "10.0.0.2",
    )
    assert remote.status == 403


def test_pairs_from_the_serialcomm_registry_values() -> None:
    values = {
        r"\Device\com0com10": "COM10",
        r"\Device\com0com20": "COM11",
        r"\Device\com0com11": "COM20",  # its B side is absent
        r"\Device\Serial0": "COM1",
    }
    assert com0com.pairs_from_serialcomm(values) == [{"a": "COM10", "b": "COM11"}]
