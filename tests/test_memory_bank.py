"""Local memory banks imported from Icom CS-9700 CSV exports."""

from __future__ import annotations

from pathlib import Path

import pytest

from rigplane.web.memory_bank import MemoryBankStore, parse_icom_csv

_HEADER = (
    "CH No;Name;SEL;Frequency;Dup;Offset;Mode;DATA;Filter;TONE;Repeater Tone;"
    "TSQL Frequency;DTCS Code;DTCS Polarity;DV SQL;DV CSQL Code;Your Call Sign;"
    "RPT1 Call Sign;RPT2 Call Sign"
)
# Rows in the exact shape CS-9700 exports (French locale: ';' and decimal ',').
_CSV = "\r\n".join(
    [
        _HEADER,
        "01;APPEL 144MHz;OFF;144,300000;OFF;0,600000;USB;OFF;1;OFF;67,0Hz;67,0Hz;023;BOTH N;OFF;0;CQCQCQ;;",
        "04;APPEL FT8;OFF;144,174000;OFF;0,600000;USB;ON;1;OFF;67,0Hz;67,0Hz;023;BOTH N;OFF;0;CQCQCQ;;",
        "19;;;;;;;;;;;;;;;;;;",
        "21; R 0;OFF;145,600000;DUP-;0,600000;FM;OFF;1;OFF;67,0Hz;67,0Hz;023;BOTH N;OFF;0;CQCQCQ;;",
        "30; FRU 12;OFF;430,300000;DUP+;1,600000;FM;OFF;1;TONE;123,0Hz;67,0Hz;023;BOTH N;OFF;0;CQCQCQ;;",
        "34; R 5 X;OFF;145,737500;DUP-;0,600000;FM;OFF;1;TSQL;67,0Hz;85,4Hz;023;BOTH N;OFF;0;CQCQCQ;;",
    ]
)


def test_parses_the_cs9700_export() -> None:
    channels = parse_icom_csv(_CSV)
    assert [c["ch"] for c in channels] == [1, 4, 21, 30, 34]  # empty 19 skipped
    assert channels[0] == {
        "ch": 1,
        "name": "APPEL 144MHz",
        "freqHz": 144_300_000,
        "mode": "USB",
        "data": False,
        "filter": 1,
        "dup": "off",
        "offsetHz": 600_000,
        "tone": "off",
        "toneCentiHz": 6700,
        "tsqlCentiHz": 6700,
    }
    assert channels[1]["data"] is True
    assert (channels[2]["dup"], channels[2]["name"]) == ("minus", "R 0")
    assert channels[3]["dup"] == "plus"
    assert channels[3]["offsetHz"] == 1_600_000
    assert (channels[3]["tone"], channels[3]["toneCentiHz"]) == ("tone", 12300)
    assert (channels[4]["tone"], channels[4]["tsqlCentiHz"]) == ("tsql", 8540)


def test_dot_decimal_comma_separated_export() -> None:
    text = _CSV.replace(",", ".").replace(";", ",")
    assert parse_icom_csv(text)[3]["freqHz"] == 430_300_000


def test_a_file_without_the_icom_columns_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_icom_csv("a;b;c\n1;2;3")


def test_store_keeps_banks_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "banks.json"
    store = MemoryBankStore(path)
    store.save("144 Memory", parse_icom_csv(_CSV))
    store.save("432 Memory", parse_icom_csv(_CSV)[:1])
    banks = MemoryBankStore(path).load()
    assert [b["name"] for b in banks] == ["144 Memory", "432 Memory"]
    assert len(banks[0]["channels"]) == 5
    MemoryBankStore(path).delete("144 Memory")
    assert [b["name"] for b in MemoryBankStore(path).load()] == ["432 Memory"]


# ── HTTP routes ─────────────────────────────────────────────────────────

import asyncio  # noqa: E402
import json  # noqa: E402

from rigplane.web.server import WebConfig, WebServer  # noqa: E402


class _Writer:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    def get_extra_info(self, name: str, default: object = None) -> object:
        return ("127.0.0.1", 50000) if name == "peername" else default

    @property
    def status(self) -> int:
        return int(bytes(self.buffer).split(b" ", 2)[1])

    @property
    def payload(self) -> dict[str, object]:
        return json.loads(bytes(self.buffer).split(b"\r\n\r\n", 1)[1] or b"{}")


class _Radio:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def set_duplex_offset(self, hz: int) -> None:
        self.offsets.append(hz)

    async def get_duplex_offset(self) -> int:
        return self.offsets[-1] if self.offsets else 600_000


def _server(
    tmp_path: Path, *, read_only: bool = False, radio: object = None
) -> WebServer:
    server = WebServer(
        None,
        WebConfig(host="127.0.0.1", port=0, radio_model="IC-9700", read_only=read_only),
    )
    server._memory_banks = MemoryBankStore(tmp_path / "banks.json")  # noqa: SLF001
    server._radio = radio  # type: ignore[assignment]  # noqa: SLF001
    return server


async def _call(
    server: WebServer, method: str, path: str, body: object = None
) -> _Writer:
    writer = _Writer()
    reader = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode()
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        headers = {"content-length": str(len(data))}
    await server._handle_http(  # noqa: SLF001
        writer,  # type: ignore[arg-type]
        method,
        path,
        headers=headers,
        reader=reader,
    )
    return writer


async def test_import_list_and_delete_a_bank(tmp_path: Path) -> None:
    server = _server(tmp_path)
    created = await _call(
        server, "POST", "/api/v1/memory-banks", {"name": "144", "csv": _CSV}
    )
    assert (created.status, created.payload) == (200, {"name": "144", "count": 5})
    listed = await _call(server, "GET", "/api/v1/memory-banks")
    banks = listed.payload["banks"]
    assert isinstance(banks, list) and banks[0]["name"] == "144"
    deleted = await _call(
        server, "POST", "/api/v1/memory-banks/delete", {"name": "144"}
    )
    assert deleted.status == 200
    assert (await _call(server, "GET", "/api/v1/memory-banks")).payload == {"banks": []}


@pytest.mark.parametrize(
    "body",
    [{"name": "x", "csv": "a;b\n1;2"}, {"name": "", "csv": _CSV}, {"csv": _CSV}],
)
async def test_bad_imports_are_refused(tmp_path: Path, body: dict[str, str]) -> None:
    writer = await _call(_server(tmp_path), "POST", "/api/v1/memory-banks", body)
    assert writer.status == 400


async def test_import_is_refused_read_only(tmp_path: Path) -> None:
    server = _server(tmp_path, read_only=True)
    writer = await _call(
        server, "POST", "/api/v1/memory-banks", {"name": "x", "csv": _CSV}
    )
    assert writer.status == 403


async def test_duplex_offset_route(tmp_path: Path) -> None:
    radio = _Radio()
    server = _server(tmp_path, radio=radio)
    put = await _call(server, "PUT", "/api/v1/radio/duplex-offset", {"hz": 1_600_000})
    assert (put.status, put.payload) == (200, {"hz": 1_600_000})
    assert radio.offsets == [1_600_000]
    bad = await _call(server, "PUT", "/api/v1/radio/duplex-offset", {"hz": "1.6"})
    assert bad.status == 400
    none = await _call(
        _server(tmp_path, radio=object()), "GET", "/api/v1/radio/duplex-offset"
    )
    assert none.status == 503
