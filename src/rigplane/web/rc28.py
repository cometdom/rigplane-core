"""ICOM RC-28 remote encoder over USB HID.

The RC-28 is a vendor-defined HID device (VID 0C26, PID 001E) whose
descriptor declares 32-byte input and output reports and no report ID.

Input report, as captured from a real unit (tests/test_rc28.py):
``[0]`` is always 0x01, ``[1]`` the wheel ticks since the previous report,
``[3]`` the direction (1 clockwise, 2 counter-clockwise), ``[5]`` the keys,
active-low: bit 0 TRANSMIT, bit 1 F1, bit 2 F2.

Output report: ``0x01`` then an active-low LED mask: bit 0 TX, bit 1 F1,
bit 2 F2, bit 3 LINK.

:class:`Rc28Bridge` owns the device on one thread (hidapi handles are not
shared across threads), publishes decoded events to asyncio subscribers and
writes the LED mask the web client asks for.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "RC28_PRODUCT_ID",
    "RC28_VENDOR_ID",
    "Rc28Bridge",
    "Rc28Decoder",
    "Rc28Key",
    "Rc28Rotate",
    "led_report",
]

logger = logging.getLogger(__name__)

RC28_VENDOR_ID = 0x0C26
RC28_PRODUCT_ID = 0x001E
_REPORT_SIZE = 32
_KEY_BITS = {"transmit": 0x01, "f1": 0x02, "f2": 0x04}
_LED_BITS = {"tx": 0x01, "f1": 0x02, "f2": 0x04, "link": 0x08}
_ALL_KEYS_UP = 0x07
_RETRY_SECONDS = 2.0


@dataclass(frozen=True)
class Rc28Rotate:
    """Wheel movement; positive ticks are clockwise."""

    ticks: int


@dataclass(frozen=True)
class Rc28Key:
    key: str
    pressed: bool


Rc28Event = Rc28Rotate | Rc28Key


class Rc28Decoder:
    """Turn RC-28 input reports into wheel and key-edge events."""

    def __init__(self) -> None:
        self._keys = _ALL_KEYS_UP

    def feed(self, report: Sequence[int]) -> list[Rc28Event]:
        if len(report) < 6 or report[0] != 0x01:
            return []
        events: list[Rc28Event] = []
        ticks, direction = report[1], report[3]
        if ticks and direction in (1, 2):
            events.append(Rc28Rotate(ticks if direction == 1 else -ticks))
        keys = report[5] & _ALL_KEYS_UP
        changed = keys ^ self._keys
        for name, bit in _KEY_BITS.items():
            if changed & bit:
                events.append(Rc28Key(name, pressed=not keys & bit))
        self._keys = keys
        return events


def led_report(
    *, tx: bool = False, f1: bool = False, f2: bool = False, link: bool = False
) -> list[int]:
    """Build the output report (report ID byte 0x00, then 32 bytes)."""
    mask = 0x0F
    for lit, name in ((tx, "tx"), (f1, "f1"), (f2, "f2"), (link, "link")):
        if lit:
            mask &= ~_LED_BITS[name]
    return [0x00, 0x01, mask] + [0x00] * (_REPORT_SIZE - 2)


def _event_message(event: Rc28Event) -> dict[str, Any]:
    if isinstance(event, Rc28Rotate):
        return {"type": "rotate", "ticks": event.ticks}
    return {"type": "key", "key": event.key, "pressed": event.pressed}


_AUTO: Any = object()


def _import_hid() -> Any:
    try:
        import hid  # type: ignore[import-not-found]
    except ImportError:
        return None
    return hid


class Rc28Bridge:
    """Read the RC-28 on a worker thread and fan its events out to asyncio."""

    def __init__(self, hid_module: Any = _AUTO, *, poll_timeout_ms: int = 100) -> None:
        self._hid = _import_hid() if hid_module is _AUTO else hid_module
        self._poll_timeout_ms = poll_timeout_ms
        self._subscribers: list[
            tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]
        ] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._leds = led_report()
        self._leds_dirty = True

    def status(self) -> dict[str, Any]:
        return {
            "type": "status",
            "connected": self._connected,
            "available": self._hid is not None,
        }

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._subscribers.append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers = [
                (lp, q) for lp, q in self._subscribers if q is not queue
            ]
            empty = not self._subscribers
        if empty:
            self.set_leds()

    def set_leds(
        self,
        *,
        tx: bool = False,
        f1: bool = False,
        f2: bool = False,
        link: bool = False,
    ) -> None:
        report = led_report(tx=tx, f1=f1, f2=f2, link=link)
        with self._lock:
            if report != self._leds:
                self._leds = report
                self._leds_dirty = True

    def press_transmit(self, pressed: bool) -> None:
        """Inject a TRANSMIT key edge from another local input (foot switch)."""
        self._publish(_event_message(Rc28Key("transmit", pressed=pressed)))

    def start(self) -> None:
        if self._hid is None or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rc28", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        await asyncio.to_thread(thread.join, 2.0)
        self._thread = None

    def _publish(self, message: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:
                pass  # subscriber loop already closed

    def _set_connected(self, connected: bool) -> None:
        if connected != self._connected:
            self._connected = connected
            logger.info("rc28: %s", "connected" if connected else "disconnected")
            self._publish(self.status())

    def _open(self) -> Any:
        found = self._hid.enumerate(RC28_VENDOR_ID, RC28_PRODUCT_ID)
        if not found:
            return None
        device = self._hid.device()
        device.open_path(found[0]["path"])
        with self._lock:
            self._leds_dirty = True
        return device

    def _write_leds(self, device: Any) -> None:
        with self._lock:
            if not self._leds_dirty:
                return
            report = list(self._leds)
            self._leds_dirty = False
        device.write(report)

    def _run(self) -> None:
        device: Any = None
        decoder = Rc28Decoder()
        while not self._stop.is_set():
            if device is None:
                try:
                    device = self._open()
                except Exception as exc:  # noqa: BLE001 - keep retrying
                    logger.debug("rc28: open failed: %s", exc)
                    device = None
                if device is None:
                    self._stop.wait(_RETRY_SECONDS)
                    continue
                decoder = Rc28Decoder()
                self._set_connected(True)
            try:
                self._write_leds(device)
                report = device.read(_REPORT_SIZE, self._poll_timeout_ms)
            except Exception as exc:  # noqa: BLE001 - unplugged device
                logger.info("rc28: device lost: %s", exc)
                self._close(device, turn_off=False)
                device = None
                self._set_connected(False)
                continue
            for event in decoder.feed(report or []):
                self._publish(_event_message(event))
        if device is not None:
            self._close(device, turn_off=True)
            self._set_connected(False)

    @staticmethod
    def _close(device: Any, *, turn_off: bool) -> None:
        try:
            if turn_off:
                device.write(led_report())
        except Exception:  # noqa: BLE001
            pass
        try:
            device.close()
        except Exception:  # noqa: BLE001
            pass
