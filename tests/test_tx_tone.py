"""1750 Hz tone burst: the server replaces outgoing TX PCM with a tone."""

from __future__ import annotations

import math
import struct

import pytest

from rigplane.web.tx_tone import TxTone


def _samples(pcm: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(pcm) // 2}h", pcm))


def test_inactive_tone_leaves_frames_alone() -> None:
    assert TxTone(clock=lambda: 0.0).render(1920, 48_000) is None


def test_tone_has_the_requested_pitch_and_duration() -> None:
    now = [0.0]
    tone = TxTone(clock=lambda: now[0])
    tone.start(1750, 1.0)
    pcm = tone.render(1920, 48_000)  # 20 ms of 48 kHz mono PCM16
    assert pcm is not None and len(pcm) == 1920
    samples = _samples(pcm)
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)
    assert crossings == pytest.approx(1750 * 0.02, abs=1)
    assert max(abs(s) for s in samples) == pytest.approx(0.45 * 32767, rel=0.02)
    now[0] = 1.01
    assert tone.render(1920, 48_000) is None


def test_phase_continues_across_frames() -> None:
    tone = TxTone(clock=lambda: 0.0)
    tone.start(1750, 1.0)
    first = _samples(tone.render(96, 48_000) or b"")
    second = _samples(tone.render(96, 48_000) or b"")
    step = 2 * math.pi * 1750 / 48_000
    expected = round(0.45 * 32767 * math.sin(step * len(first)))
    assert second[0] == pytest.approx(expected, abs=2)


@pytest.mark.parametrize(("hz", "seconds"), [(100, 1.0), (1750, 0.0), (1750, 5.0)])
def test_out_of_range_requests_are_refused(hz: int, seconds: float) -> None:
    with pytest.raises(ValueError):
        TxTone().start(hz, seconds)


async def test_audio_handler_replaces_pcm_frames_during_the_burst() -> None:
    from rigplane.web.handlers.audio import AudioHandler

    class _Radio:
        def __init__(self) -> None:
            self.pushed: list[bytes] = []

        async def push_tx(self, data: bytes) -> None:
            self.pushed.append(data)

    radio = _Radio()
    tone = TxTone(clock=lambda: 0.0)
    handler = AudioHandler(object(), radio, tx_tone=tone)  # type: ignore[arg-type]
    mic = b"\x01\x00" * 960
    await handler._push_tx(mic, legacy_method="push_audio_tx_pcm")  # noqa: SLF001
    assert radio.pushed[-1] == mic
    tone.start(1750, 1.0)
    await handler._push_tx(mic, legacy_method="push_audio_tx_pcm")  # noqa: SLF001
    assert radio.pushed[-1] != mic and len(radio.pushed[-1]) == len(mic)


async def test_tx_tone_route(tmp_path: object) -> None:
    import asyncio
    import json

    from rigplane.web.server import WebConfig, WebServer

    class _Writer:
        def __init__(self) -> None:
            self.buffer = bytearray()

        def write(self, data: bytes) -> None:
            self.buffer.extend(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

    async def post(server: WebServer, body: object) -> int:
        data = json.dumps(body).encode()
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        writer = _Writer()
        await server._handle_http(  # noqa: SLF001
            writer,  # type: ignore[arg-type]
            "POST",
            "/api/v1/tx-tone",
            headers={"content-length": str(len(data))},
            reader=reader,
        )
        return int(bytes(writer.buffer).split(b" ", 2)[1])

    server = WebServer(None, WebConfig(host="127.0.0.1", port=0, radio_model="IC-9700"))
    assert await post(server, {"hz": 1750, "ms": 1000}) == 200
    assert server._tx_tone.render(96, 48_000) is not None  # noqa: SLF001
    assert await post(server, {"hz": 1750}) == 400
    assert await post(server, {"hz": 50, "ms": 1000}) == 400
    read_only = WebServer(
        None,
        WebConfig(host="127.0.0.1", port=0, radio_model="IC-9700", read_only=True),
    )
    assert await post(read_only, {"hz": 1750, "ms": 1000}) == 403
