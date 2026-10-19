"""com0com virtual COM port pairs (Windows), through its setupc.exe tool.

``setupc list`` prints one line per port, e.g.::

    CNCA0 PortName=COM10
    CNCB0 PortName=COM#,RealPortName=COM11

Ports ``CNCAn``/``CNCBn`` with the same ``n`` form a pair. Installing a pair
needs administrator rights, so :func:`create_pair` asks Windows for them
(the UAC prompt) and waits for setupc to finish.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

__all__ = [
    "create_pair",
    "find_setupc",
    "list_pairs",
    "parse_setupc_list",
    "valid_port",
]

_LINE = re.compile(r"^\s*CNC([AB])(\d+)\s+(\S+)", re.MULTILINE)
_PORT = re.compile(r"^COM\d{1,3}$")


def valid_port(name: str) -> bool:
    return bool(_PORT.match(name))


def find_setupc() -> Path | None:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            candidate = Path(base) / "com0com" / "setupc.exe"
            if candidate.is_file():
                return candidate
    return None


def parse_setupc_list(output: str) -> list[dict[str, str]]:
    """Pairs ``[{a, b}]`` of the port names Windows uses (RealPortName first)."""
    sides: dict[str, dict[str, str]] = {}
    for side, number, params in _LINE.findall(output):
        values = dict(part.split("=", 1) for part in params.split(",") if "=" in part)
        name = values.get("RealPortName") or values.get("PortName") or ""
        if valid_port(name):
            sides.setdefault(number, {})[side.lower()] = name
    return [
        {"a": pair["a"], "b": pair["b"]}
        for _, pair in sorted(sides.items(), key=lambda item: int(item[0]))
        if "a" in pair and "b" in pair
    ]


async def _run(setupc: Path, *args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        str(setupc),
        *args,
        cwd=str(setupc.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    return output.decode(errors="replace")


async def list_pairs() -> list[dict[str, str]]:
    setupc = find_setupc()
    if setupc is None:
        return []
    return parse_setupc_list(await _run(setupc, "list"))


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
