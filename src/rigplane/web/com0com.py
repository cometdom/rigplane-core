"""com0com virtual COM port pairs (Windows).

setupc.exe needs administrator rights for every command, ``list`` included,
so the pairs are read from the registry instead: ``HKLM\\HARDWARE\\DEVICEMAP\\
SERIALCOMM`` maps each present port device to its COM name, and com0com
names the two ports of pair ``n`` ``\\Device\\com0com1n`` and
``\\Device\\com0com2n``. Only :func:`create_pair` runs setupc, through the
Windows elevation prompt.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = [
    "create_pair",
    "find_setupc",
    "list_pairs",
    "pairs_from_serialcomm",
    "valid_port",
]

_PORT = re.compile(r"^COM\d{1,3}$")
_DEVICE = re.compile(r"^\\Device\\com0com([12])(\d+)$", re.IGNORECASE)


def valid_port(name: str) -> bool:
    return bool(_PORT.match(name))


def find_setupc() -> Path | None:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            candidate = Path(base) / "com0com" / "setupc.exe"
            if candidate.is_file():
                return candidate
    return None


def pairs_from_serialcomm(values: Mapping[str, str]) -> list[dict[str, str]]:
    """Pairs ``[{a, b}]`` from SERIALCOMM's device-name → COM-name values."""
    sides: dict[str, dict[str, str]] = {}
    for device, port in values.items():
        match = _DEVICE.match(device)
        if match and valid_port(port):
            side = "a" if match.group(1) == "1" else "b"
            sides.setdefault(match.group(2), {})[side] = port
    return [
        {"a": pair["a"], "b": pair["b"]}
        for _, pair in sorted(sides.items(), key=lambda item: int(item[0]))
        if "a" in pair and "b" in pair
    ]


def _read_serialcomm() -> dict[str, str]:
    import winreg

    reg: Any = winreg
    values: dict[str, str] = {}
    try:
        key = reg.OpenKey(reg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
    except OSError:
        return values
    with key:
        index = 0
        while True:
            try:
                name, value, _ = reg.EnumValue(key, index)
            except OSError:
                return values
            if isinstance(name, str) and isinstance(value, str):
                values[name] = value
            index += 1


async def list_pairs() -> list[dict[str, str]]:
    if sys.platform != "win32":
        return []
    try:
        return pairs_from_serialcomm(await asyncio.to_thread(_read_serialcomm))
    except OSError:
        return []


async def create_pair(a: str, b: str) -> int:
    """Install the pair ``a``/``b`` with administrator rights; setupc's exit code."""
    setupc = find_setupc()
    if setupc is None:
        raise FileNotFoundError("com0com setupc.exe not found")
    if not (valid_port(a) and valid_port(b)) or a == b:
        raise ValueError("expected two different names like COM10 and COM11")
    command = (
        f"$p = Start-Process -FilePath '{setupc}' -WorkingDirectory '{setupc.parent}' "
        # PortName=COM# puts both ports in the Windows "Ports" class, so
        # programs that enumerate COM ports (OmniRig, loggers) list them.
        f"-ArgumentList 'install','PortName=COM#,RealPortName={a}',"
        f"'PortName=COM#,RealPortName={b}' "
        "-Verb RunAs -Wait -PassThru -WindowStyle Hidden; exit $p.ExitCode"
    )
    process = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-NonInteractive", "-Command", command
    )
    return await process.wait()
