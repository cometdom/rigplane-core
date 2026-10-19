"""RemoteMyRig: rigplane in its own Windows window.

The window (pywebview / WebView2) shows the rigplane web UI. rigplane runs as
a child process of this same executable (``--server``), started with the
radio settings saved on first run; the radio password lives in the Windows
Credential Manager (keyring), never in a file. Closing the window asks the
server to stop through the same path as Ctrl+C (POST /api/v1/app/shutdown).

A foot switch that sends a key (Insert by default) is captured globally and
forwarded as the RC-28 TRANSMIT key (POST /api/v1/rc28/transmit), so it
keys through the on-screen PTT gate without the window having focus.
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

APP = "RemoteMyRig"
SETTINGS_PATH = (
    Path(os.environ.get("APPDATA", str(Path.home()))) / APP / "settings.json"
)
DEFAULTS: dict[str, Any] = {
    "model": "IC-9700",
    "host": "",
    "user": "",
    "port": 8080,
    "listen": "127.0.0.1",
    "footswitch_key": "Insert",
    "extra_args": [],
}
# Virtual-key codes for the keys a foot switch is usually set to send.
FOOTSWITCH_KEYS = {
    "Insert": 0x2D,
    "Pause": 0x13,
    "ScrollLock": 0x91,
    **{f"F{n}": 0x70 + n - 1 for n in range(13, 25)},
}
STARTUP_TIMEOUT_S = 60.0
SHUTDOWN_TIMEOUT_S = 20.0


# ── settings ────────────────────────────────────────────────────────────


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def save_settings(settings: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: settings[k] for k in DEFAULTS if k in settings}
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")


def needs_setup(settings: dict[str, Any]) -> bool:
    return not settings["host"] or not settings["model"]


def _credential_name(settings: dict[str, Any]) -> str:
    return f"{settings['host']}:{settings['user']}"


def get_password(settings: dict[str, Any]) -> str:
    import keyring

    return keyring.get_password(APP, _credential_name(settings)) or ""


def set_password(settings: dict[str, Any], password: str) -> None:
    import keyring

    keyring.set_password(APP, _credential_name(settings), password)


# ── rigplane child process ──────────────────────────────────────────────


def server_command(settings: dict[str, Any]) -> list[str]:
    """The rigplane CLI arguments for the child (after ``--server``)."""
    return [
        "--model",
        str(settings["model"]),
        *[str(arg) for arg in settings["extra_args"]],
        "web",
        "--listen",
        str(settings["listen"]),
        "--port",
        str(settings["port"]),
    ]


def server_environment(settings: dict[str, Any], password: str) -> dict[str, str]:
    env = dict(os.environ)
    env["RIGPLANE_APP_SHUTDOWN"] = "1"
    if settings["host"]:
        env["ICOM_HOST"] = str(settings["host"])
    if settings["user"]:
        env["ICOM_USER"] = str(settings["user"])
    if password:
        env["ICOM_PASS"] = password
    return env


def run_server(argv: list[str]) -> None:
    """Child entry: run the rigplane CLI with ``argv``."""
    if sys.stdout is None or sys.stderr is None:  # windowed executable
        devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    from rigplane.cli import main  # noqa: TID251 - same entry as the rigplane script

    sys.argv = ["rigplane", *argv]
    main()


def start_server(settings: dict[str, Any]) -> subprocess.Popen[bytes]:
    if getattr(sys, "frozen", False):
        base = [sys.executable, "--server"]
    else:
        base = [sys.executable, os.path.abspath(__file__), "--server"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [*base, *server_command(settings)],
        env=server_environment(settings, get_password(settings)),
        creationflags=flags,
    )


def local_url(settings: dict[str, Any], path: str = "/") -> str:
    return f"http://127.0.0.1:{settings['port']}{path}"


def wait_until_ready(
    settings: dict[str, Any], process: subprocess.Popen[bytes]
) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(local_url(settings, "/api/v1/info"), timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def post_json(settings: dict[str, Any], path: str, body: dict[str, Any]) -> None:
    request = urllib.request.Request(
        local_url(settings, path),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3):
            pass
    except (urllib.error.URLError, OSError):
        pass


def stop_server(settings: dict[str, Any], process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    post_json(settings, "/api/v1/app/shutdown", {})
    try:
        process.wait(SHUTDOWN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()


# ── foot switch (global hotkey) ─────────────────────────────────────────


class FootSwitch:
    """Register one global hotkey; each press is a TRANSMIT key edge.

    RegisterHotKey reports presses only, so this suits the RC-28 TRANSMIT
    toggle mode (press = key, next press = unkey). The key is consumed while
    RemoteMyRig runs, as the AutoHotkey script did.
    """

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_NOREPEAT = 0x4000

    def __init__(self, settings: dict[str, Any]) -> None:
        self._settings = settings
        self._thread_id = 0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        vk = FOOTSWITCH_KEYS.get(str(self._settings["footswitch_key"]))
        if vk is None or sys.platform != "win32":
            return
        self._thread = threading.Thread(target=self._run, args=(vk,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)

    def _run(self, vk: int) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, self.MOD_NOREPEAT, vk):
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == self.WM_HOTKEY:
                    for pressed in (True, False):
                        post_json(
                            self._settings,
                            "/api/v1/rc28/transmit",
                            {"pressed": pressed},
                        )
        finally:
            user32.UnregisterHotKey(None, 1)


# ── window ──────────────────────────────────────────────────────────────

PAGE_STYLE = """
<style>
 body{background:#0b0f17;color:#d8e1ee;font:15px system-ui,sans-serif;
      display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
 .box{width:420px} h1{font-size:20px;margin:0 0 16px}
 label{display:block;margin:10px 0 4px;color:#9fb0c6}
 input,select{width:100%;padding:8px;background:#141b27;color:#e8eef7;
      border:1px solid #2a3547;border-radius:4px;box-sizing:border-box}
 button{margin-top:18px;padding:10px 16px;background:#1f6feb;color:#fff;border:0;
      border-radius:4px;font-size:15px;cursor:pointer}
 .err{color:#ff7b72;margin-top:12px;white-space:pre-wrap}
</style>"""


def message_page(text: str) -> str:
    return f"<html><head>{PAGE_STYLE}</head><body><div class='box'><h1>{APP}</h1><p>{text}</p></div></body></html>"


def setup_page(settings: dict[str, Any]) -> str:
    def opt(value: str) -> str:
        sel = " selected" if settings["model"] == value else ""
        return f"<option{sel}>{value}</option>"

    def val(key: str) -> str:
        return html.escape(str(settings[key]), quote=True)

    return f"""<html><head>{PAGE_STYLE}</head><body><div class='box'>
<h1>{APP} — réglages de la radio</h1>
<label>Modèle</label><select id='model'>{opt("IC-9700")}{opt("IC-7300")}</select>
<label>Adresse IP de la radio</label><input id='host' value='{val("host")}'>
<label>Utilisateur réseau</label><input id='user' value='{val("user")}'>
<label>Mot de passe réseau (laisser vide pour garder l'actuel)</label><input id='pass' type='password'>
<label>Touche de la pédale (Insert, F13…F24, Pause, ScrollLock ; vide = aucune)</label>
<input id='key' value='{val("footswitch_key")}'>
<button onclick="const v=(id)=>document.getElementById(id).value;
 pywebview.api.save({{model:v('model'),host:v('host'),user:v('user'),
 password:v('pass'),footswitch_key:v('key')}})">Enregistrer et se connecter</button>
<div class='err' id='err'></div></div></body></html>"""


class SetupApi:
    """The only object the page can call (pywebview js_api)."""

    def __init__(self, app: App) -> None:
        self._app = app

    def save(self, form: dict[str, str]) -> None:
        self._app.save(form)


class App:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.process: subprocess.Popen[bytes] | None = None
        self.footswitch: FootSwitch | None = None
        self.window: Any = None

    def save(self, form: dict[str, str]) -> None:
        for key in ("model", "host", "user", "footswitch_key"):
            self.settings[key] = str(form.get(key, "")).strip()
        save_settings(self.settings)
        if form.get("password"):
            set_password(self.settings, str(form["password"]))
        threading.Thread(target=self.launch, daemon=True).start()

    def launch(self) -> None:
        self.window.load_html(
            message_page("Démarrage de rigplane et connexion à la radio…")
        )
        self.process = start_server(self.settings)
        if not wait_until_ready(self.settings, self.process):
            log = (
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "rigplane/rigplane/Cache/logs/rigplane.log"
            )
            self.window.load_html(
                message_page(
                    "rigplane n'a pas démarré. Vérifiez qu'il ne tourne pas déjà "
                    f"dans une autre fenêtre (port {self.settings['port']}).<br>"
                    f"Journal : {log}"
                )
            )
            return
        self.footswitch = FootSwitch(self.settings)
        self.footswitch.start()
        self.window.load_url(local_url(self.settings))

    def on_closed(self) -> None:
        if self.footswitch is not None:
            self.footswitch.stop()
        if self.process is not None:
            stop_server(self.settings, self.process)


def main() -> None:
    # Keep the UI timers running at full rate when the window is hidden or
    # minimised (RC-28 wheel, meters); WebView2 throttles background pages.
    os.environ.setdefault(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--disable-background-timer-throttling --disable-renderer-backgrounding "
        "--disable-backgrounding-occluded-windows",
    )
    import webview

    app = App()
    setup = "--setup" in sys.argv or needs_setup(app.settings)
    first_page = setup_page(app.settings) if setup else message_page("Démarrage…")
    app.window = webview.create_window(
        APP,
        html=first_page,
        js_api=SetupApi(app),
        width=1920,
        height=1080,
        maximized=True,
    )
    app.window.events.closed += app.on_closed
    webview.start(None if setup else app.launch)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        run_server(sys.argv[2:])
    else:
        main()
