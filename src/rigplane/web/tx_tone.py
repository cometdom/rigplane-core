"""Tone burst for repeater access (1750 Hz): while active, outgoing browser
TX PCM frames are replaced by a sine at the requested pitch, so the tone is
transmitted through the same LAN audio path as the operator's voice."""

from __future__ import annotations

import math
import struct
import time
from collections.abc import Callable

__all__ = ["TxTone"]

_AMPLITUDE = 0.45  # of full scale; the level of normal speech peaks on this path


class TxTone:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hz = 0
        self._until = 0.0
        self._phase = 0.0

    def start(self, hz: int, seconds: float) -> None:
        if not 300 <= hz <= 3000 or not 0.0 < seconds <= 3.0:
            raise ValueError("tone must be 300-3000 Hz for 0-3 s")
        self._hz = hz
        self._phase = 0.0
        self._until = self._clock() + seconds

    def render(self, nbytes: int, sample_rate: int) -> bytes | None:
        """A PCM16 mono frame of ``nbytes`` bytes, or None when no tone plays."""
        if self._clock() >= self._until:
            return None
        step = 2 * math.pi * self._hz / sample_rate
        count = nbytes // 2
        peak = _AMPLITUDE * 32767
        values = [round(peak * math.sin(self._phase + step * i)) for i in range(count)]
        self._phase = (self._phase + step * count) % (2 * math.pi)
        return struct.pack(f"<{count}h", *values)
