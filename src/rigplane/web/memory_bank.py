"""Local memory banks imported from Icom CSV exports (CS-9700 and siblings).

The channels live on this computer, not in the radio: recalling one tunes
the radio through the ordinary commands, and the radio's own memories are
never written. A bank is the channel list of one imported file.

CS-9700 exports ``;``-separated rows with decimal commas in a French
locale (``144,300000``) and ``,``-separated rows with decimal points
otherwise; frequency and offset are in MHz, tones like ``67,0Hz``.
"""

from __future__ import annotations

import csv
import io
import json
import threading
from pathlib import Path
from typing import Any

__all__ = ["MemoryBankStore", "default_store_path", "parse_icom_csv"]

_REQUIRED = ("CH No", "Frequency", "Mode")
_DUP = {"OFF": "off", "DUP-": "minus", "DUP+": "plus"}
_TONE = {"OFF": "off", "TONE": "tone", "TSQL": "tsql", "DTCS": "dtcs"}


def _number(text: str) -> float:
    return float(text.strip().replace(",", "."))


def _centihz(text: str) -> int | None:
    cleaned = text.strip().removesuffix("Hz").strip()
    if not cleaned:
        return None
    return round(_number(cleaned) * 100)


def parse_icom_csv(text: str) -> list[dict[str, Any]]:
    """Parse an Icom memory-channel CSV export into channel dicts.

    Rows without a frequency (empty channels) are skipped. Raises
    ``ValueError`` when the header lacks the Icom columns.
    """
    sample = text.lstrip("﻿")
    first = sample.splitlines()[0] if sample else ""
    delimiter = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(sample), delimiter=delimiter)
    fields = [name.strip() for name in reader.fieldnames or ()]
    if not all(name in fields for name in _REQUIRED):
        raise ValueError("not an Icom memory CSV (missing CH No / Frequency / Mode)")
    channels: list[dict[str, Any]] = []
    for raw in reader:
        row = {
            (k or "").strip(): (v or "").strip()
            for k, v in raw.items()
            if isinstance(v, str)
        }
        if not row.get("Frequency"):
            continue
        offset = row.get("Offset", "")
        filter_text = row.get("Filter", "")
        channels.append(
            {
                "ch": int(row["CH No"]),
                "name": row.get("Name", ""),
                "freqHz": round(_number(row["Frequency"]) * 1_000_000),
                "mode": row["Mode"].upper(),
                "data": row.get("DATA", "OFF").upper() == "ON",
                "filter": int(filter_text) if filter_text.isdigit() else None,
                "dup": _DUP.get(row.get("Dup", "OFF").upper(), "off"),
                "offsetHz": round(_number(offset) * 1_000_000) if offset else None,
                "tone": _TONE.get(row.get("TONE", "OFF").upper(), "off"),
                "toneCentiHz": _centihz(row.get("Repeater Tone", "")),
                "tsqlCentiHz": _centihz(row.get("TSQL Frequency", "")),
            }
        )
    return channels


def default_store_path() -> Path:
    import platformdirs

    return Path(platformdirs.user_data_path("rigplane")) / "memory-banks.json"


class MemoryBankStore:
    """The imported banks, as one JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        banks = data.get("banks") if isinstance(data, dict) else None
        return banks if isinstance(banks, list) else []

    def _write(self, banks: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"banks": banks}, ensure_ascii=False), "utf-8")
        tmp.replace(self._path)

    def save(self, name: str, channels: list[dict[str, Any]]) -> None:
        """Add the bank, or replace the bank with the same name."""
        with self._lock:
            banks = [b for b in self.load() if b.get("name") != name]
            banks.append({"name": name, "channels": channels})
            self._write(banks)

    def delete(self, name: str) -> bool:
        with self._lock:
            banks = self.load()
            kept = [b for b in banks if b.get("name") != name]
            if len(kept) == len(banks):
                return False
            self._write(kept)
            return True
