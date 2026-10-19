"""RemoteMyRig: rigplane in its own Windows window.

The window (pywebview / WebView2) shows the rigplane web UI. rigplane runs as
a child process of this same executable (``--server``), started with the
radio chosen at start (several can be configured, over the network or USB);
a network password lives in the Windows Credential Manager (keyring), never
in a file. Closing the window asks the
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
MODELS = ("IC-9700", "IC-7300", "IC-7300MK2", "IC-705", "IC-7610")
BAUD_RATES = (115200, 57600, 38400, 19200, 9600, 4800)
RADIO_DEFAULTS: dict[str, Any] = {
    "name": "",
    "model": "IC-9700",
    "connection": "lan",  # "lan" (network) or "usb" (serial CI-V + USB audio)
    "host": "",
    "user": "",
    "serial_port": "",
    "serial_baud": 115200,
    "rx_device": "",  # empty: rigplane picks the radio's USB audio itself
    "tx_device": "",
    "extra_args": [],
}
DEFAULTS: dict[str, Any] = {
    "port": 8080,
    "listen": "127.0.0.1",
    "footswitch_key": "Insert",
    "last_radio": "",
    "radios": [],
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


def normalize_radio(raw: dict[str, Any]) -> dict[str, Any]:
    radio = {**RADIO_DEFAULTS, **{k: v for k, v in raw.items() if k in RADIO_DEFAULTS}}
    if radio["connection"] not in ("lan", "usb"):
        radio["connection"] = "lan"
    try:
        radio["serial_baud"] = int(radio["serial_baud"])
    except (TypeError, ValueError):
        radio["serial_baud"] = RADIO_DEFAULTS["serial_baud"]
    if not isinstance(radio["extra_args"], list):
        radio["extra_args"] = []
    radio["name"] = str(radio["name"]).strip() or str(radio["model"])
    return radio


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    settings = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    radios = stored.get("radios")
    if isinstance(radios, list):
        settings["radios"] = [normalize_radio(r) for r in radios if isinstance(r, dict)]
    elif stored.get("host"):
        # Settings written before several radios were supported: one LAN radio.
        settings["radios"] = [normalize_radio({**stored, "connection": "lan"})]
    else:
        settings["radios"] = []
    return settings


def save_settings(settings: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: settings[k] for k in DEFAULTS if k in settings}
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")


def radio_ready(radio: dict[str, Any]) -> bool:
    if radio["connection"] == "usb":
        return bool(radio["serial_port"])
    return bool(radio["host"])


def find_radio(settings: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((r for r in settings["radios"] if r["name"] == name), None)


def start_choice(settings: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """What the window opens on: ``setup``, ``choose`` or ``launch`` a radio."""
    ready = [r for r in settings["radios"] if radio_ready(r)]
    if not ready:
        return "setup", None
    if len(ready) == 1:
        return "launch", ready[0]
    return "choose", None


def _credential_name(radio: dict[str, Any]) -> str:
    return f"{radio['host']}:{radio['user']}"


def get_password(radio: dict[str, Any]) -> str:
    if radio["connection"] != "lan":
        return ""
    import keyring

    return keyring.get_password(APP, _credential_name(radio)) or ""


def set_password(radio: dict[str, Any], password: str) -> None:
    import keyring

    keyring.set_password(APP, _credential_name(radio), password)


def unique_names(names: list[str]) -> list[str]:
    """Names that appear exactly once, in their first order.

    Windows lists one audio device per driver (MME, WASAPI, …) under the same
    name; rigplane refuses such a name as ambiguous, so only the automatic
    choice can pick one of those.
    """
    return [name for name in dict.fromkeys(names) if names.count(name) == 1]


def list_devices() -> dict[str, list[dict[str, str]]]:
    """COM ports and audio devices for the setup page (empty when unavailable)."""
    ports: list[dict[str, str]] = []
    inputs: list[dict[str, str]] = []
    outputs: list[dict[str, str]] = []
    try:
        from serial.tools import list_ports

        ports = [
            {"value": p.device, "label": f"{p.device} — {p.description}"}
            for p in sorted(list_ports.comports(), key=lambda p: p.device)
        ]
    except Exception:  # noqa: BLE001 - the page then offers free text only
        pass
    try:
        import sounddevice

        devices = list(sounddevice.query_devices())
        ins = [str(d["name"]) for d in devices if d["max_input_channels"] > 0]
        outs = [str(d["name"]) for d in devices if d["max_output_channels"] > 0]
        inputs = [{"value": n, "label": n} for n in unique_names(ins)]
        outputs = [{"value": n, "label": n} for n in unique_names(outs)]
    except Exception:  # noqa: BLE001
        pass
    return {"ports": ports, "inputs": inputs, "outputs": outputs}


# ── rigplane child process ──────────────────────────────────────────────


def server_command(settings: dict[str, Any], radio: dict[str, Any]) -> list[str]:
    """The rigplane CLI arguments for the child (after ``--server``)."""
    args = ["--model", str(radio["model"])]
    if radio["connection"] == "usb":
        args += [
            "--backend",
            "serial",
            "--serial-port",
            str(radio["serial_port"]),
            "--serial-baud",
            str(radio["serial_baud"]),
        ]
        if radio["rx_device"]:
            args += ["--rx-device", str(radio["rx_device"])]
        if radio["tx_device"]:
            args += ["--tx-device", str(radio["tx_device"])]
    return [
        *args,
        *[str(arg) for arg in radio["extra_args"]],
        "web",
        "--listen",
        str(settings["listen"]),
        "--port",
        str(settings["port"]),
    ]


def server_environment(radio: dict[str, Any], password: str) -> dict[str, str]:
    env = dict(os.environ)
    env["RIGPLANE_APP_SHUTDOWN"] = "1"
    for name in ("ICOM_HOST", "ICOM_USER", "ICOM_PASS"):
        env.pop(name, None)
    if radio["connection"] == "lan":
        if radio["host"]:
            env["ICOM_HOST"] = str(radio["host"])
        if radio["user"]:
            env["ICOM_USER"] = str(radio["user"])
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


def start_server(
    settings: dict[str, Any], radio: dict[str, Any]
) -> subprocess.Popen[bytes]:
    if getattr(sys, "frozen", False):
        base = [sys.executable, "--server"]
    else:
        base = [sys.executable, os.path.abspath(__file__), "--server"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [*base, *server_command(settings, radio)],
        env=server_environment(radio, get_password(radio)),
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
 body{background:#0b0f17;color:#d8e1ee;font:15px system-ui,sans-serif;margin:0;
      display:flex;align-items:center;justify-content:center;min-height:100vh}
 .box{width:480px;padding:24px 0} h1{font-size:20px;margin:0 0 16px}
 h2{font-size:14px;margin:22px 0 6px;color:#9fb0c6;text-transform:uppercase;letter-spacing:.06em}
 label{display:block;margin:10px 0 4px;color:#9fb0c6}
 input,select{width:100%;padding:8px;background:#141b27;color:#e8eef7;
      border:1px solid #2a3547;border-radius:4px;box-sizing:border-box;font:inherit}
 .choice{display:flex;gap:16px;margin-top:6px} .choice label{display:flex;gap:6px;margin:0;color:#e8eef7}
 .choice input{width:auto}
 button{margin-top:18px;padding:10px 16px;background:#1f6feb;color:#fff;border:0;
      border-radius:4px;font-size:15px;cursor:pointer}
 button.secondary{background:#253046} button.danger{background:#5c1d24}
 .radio{display:flex;align-items:center;gap:10px;margin-top:10px}
 .radio button{margin:0} .radio .go{flex:1;text-align:left}
 .hint{color:#7d8ba1;font-size:13px;margin-top:4px}
 .err{color:#ff7b72;margin-top:12px;white-space:pre-wrap}
</style>"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _js(value: object) -> str:
    """A JSON literal safe inside an HTML attribute or a <script> block."""
    return _esc(json.dumps(value).replace("</", "<\\/"))


def message_page(text: str) -> str:
    return (
        f"<html><head>{PAGE_STYLE}</head><body><div class='box'><h1>{APP}</h1>"
        f"<p>{text}</p></div></body></html>"
    )


def choose_page(settings: dict[str, Any]) -> str:
    rows = "".join(
        f"""<div class='radio'>
<button class='go' onclick='pywebview.api.start({_js(r["name"])})'>{_esc(r["name"])}
 <span class='hint'>— {_esc(r["model"])}, {"USB " + _esc(r["serial_port"]) if r["connection"] == "usb" else _esc(r["host"])}</span></button>
<button class='secondary' onclick='pywebview.api.edit({_js(r["name"])})'>Modifier</button></div>"""
        for r in settings["radios"]
        if radio_ready(r)
    )
    return f"""<html><head>{PAGE_STYLE}</head><body><div class='box'>
<h1>{APP} — quelle radio ?</h1>{rows}
<button class='secondary' onclick='pywebview.api.edit("")'>Ajouter une radio</button>
</div></body></html>"""


def setup_page(settings: dict[str, Any], radio: dict[str, Any] | None = None) -> str:
    editing = radio is not None
    r = radio or normalize_radio({"name": ""})
    model_options = "".join(
        f"<option{' selected' if r['model'] == m else ''}>{m}</option>" for m in MODELS
    )
    baud_options = "".join(
        f"<option{' selected' if r['serial_baud'] == b else ''}>{b}</option>"
        for b in BAUD_RATES
    )
    lan = r["connection"] == "lan"
    current = json.dumps(
        {"port": r["serial_port"], "rx": r["rx_device"], "tx": r["tx_device"]}
    ).replace("</", "<\\/")
    original = json.dumps(r["name"] if editing else "").replace("</", "<\\/")
    others = any(x["name"] != r["name"] for x in settings["radios"] if radio_ready(x))
    return f"""<html><head>{PAGE_STYLE}</head><body><div class='box'>
<h1>{APP} — {"modifier la radio" if editing else "nouvelle radio"}</h1>
<label>Nom</label><input id='name' value='{_esc(r["name"])}' placeholder='ex. IC-7300 USB'>
<label>Modèle</label><select id='model'>{model_options}</select>
<label>Connexion</label>
<div class='choice'>
 <label><input type='radio' name='conn' value='lan' {"checked" if lan else ""} onchange='toggle()'>Réseau (LAN)</label>
 <label><input type='radio' name='conn' value='usb' {"" if lan else "checked"} onchange='toggle()'>USB</label>
</div>
<div id='lan'>
 <label>Adresse IP de la radio</label><input id='host' value='{_esc(r["host"])}'>
 <label>Utilisateur réseau</label><input id='user' value='{_esc(r["user"])}'>
 <label>Mot de passe réseau (vide = garder l'actuel)</label><input id='pass' type='password'>
</div>
<div id='usb'>
 <label>Port COM de la radio</label><select id='port'></select>
 <div class='hint'>Le port « Silicon Labs CP210x » de la radio, dans le Gestionnaire de périphériques.</div>
 <label>Vitesse (MENU &gt; SET &gt; Connectors &gt; CI-V &gt; CI-V USB Baud Rate)</label>
 <select id='baud'>{baud_options}</select>
 <label>Carte son — réception</label><select id='rx'></select>
 <div class='hint'>« Automatique » trouve la carte son USB de la radio ; c'est le bon choix
 dans presque tous les cas.</div>
 <label>Carte son — émission</label><select id='tx'></select>
</div>
<h2>Commun à toutes les radios</h2>
<label>Touche de la pédale (Insert, F13…F24, Pause, ScrollLock ; vide = aucune)</label>
<input id='key' value='{_esc(settings["footswitch_key"])}'>
<button onclick='save()'>Enregistrer et se connecter</button>
{"<button class='danger' onclick='pywebview.api.remove(" + _esc(original) + ")'>Supprimer cette radio</button>" if editing else ""}
{"<button class='secondary' onclick='pywebview.api.choose()'>Retour à la liste</button>" if others else ""}
<div class='err' id='err'></div></div>
<script>
const current = {current};
const $ = (id) => document.getElementById(id);
function conn() {{ return document.querySelector("input[name=conn]:checked").value; }}
function toggle() {{
  $('lan').style.display = conn() === 'lan' ? '' : 'none';
  $('usb').style.display = conn() === 'usb' ? '' : 'none';
}}
function fill(select, items, value, auto) {{
  select.innerHTML = '';
  if (auto) select.add(new Option(auto, ''));
  for (const item of items) select.add(new Option(item.label, item.value));
  if (value && ![...select.options].some((o) => o.value === value)) select.add(new Option(value, value));
  select.value = value || '';
}}
function save() {{
  pywebview.api.save({original}, {{
    name: $('name').value, model: $('model').value, connection: conn(),
    host: $('host').value, user: $('user').value, password: $('pass').value,
    serial_port: $('port').value, serial_baud: $('baud').value,
    rx_device: $('rx').value, tx_device: $('tx').value, footswitch_key: $('key').value,
  }}).then((error) => {{ if (error) $('err').textContent = error; }});
}}
toggle();
window.addEventListener('pywebviewready', () => pywebview.api.devices().then((d) => {{
  fill($('port'), d.ports, current.port, null);
  fill($('rx'), d.inputs, current.rx, 'Automatique (recommandé)');
  fill($('tx'), d.outputs, current.tx, 'Automatique (recommandé)');
}}));
</script></body></html>"""


class SetupApi:
    """The only object the page can call (pywebview js_api)."""

    def __init__(self, app: App) -> None:
        self._app = app

    def devices(self) -> dict[str, list[dict[str, str]]]:
        return list_devices()

    def save(self, original: str, form: dict[str, str]) -> str:
        return self._app.save(original, form)

    def start(self, name: str) -> None:
        radio = find_radio(self._app.settings, name)
        if radio is not None:
            threading.Thread(
                target=self._app.launch, args=(radio,), daemon=True
            ).start()

    def edit(self, name: str) -> None:
        self._app.window.load_html(
            setup_page(self._app.settings, find_radio(self._app.settings, name))
        )

    def remove(self, name: str) -> None:
        self._app.settings["radios"] = [
            r for r in self._app.settings["radios"] if r["name"] != name
        ]
        save_settings(self._app.settings)
        self.choose()

    def choose(self) -> None:
        page, _ = start_choice(self._app.settings)
        self._app.window.load_html(
            choose_page(self._app.settings)
            if page != "setup"
            else setup_page(self._app.settings)
        )


def apply_form(
    settings: dict[str, Any], original: str, form: dict[str, str]
) -> tuple[dict[str, Any] | None, str]:
    """Merge the setup form into ``settings``; (the saved radio, error text)."""
    radio = normalize_radio(
        {key: str(form.get(key, "")).strip() for key in RADIO_DEFAULTS if key in form}
    )
    if not radio_ready(radio):
        return None, (
            "Indiquez le port COM de la radio."
            if radio["connection"] == "usb"
            else "Indiquez l'adresse IP de la radio."
        )
    if any(
        r["name"] == radio["name"] and r["name"] != original for r in settings["radios"]
    ):
        return None, "Une autre radio porte déjà ce nom."
    old = find_radio(settings, original) if original else None
    if old is not None:
        radio["extra_args"] = old["extra_args"]
    settings["radios"] = [r for r in settings["radios"] if r["name"] != original]
    settings["radios"].append(radio)
    settings["footswitch_key"] = str(form.get("footswitch_key", "")).strip()
    return radio, ""


class App:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.process: subprocess.Popen[bytes] | None = None
        self.footswitch: FootSwitch | None = None
        self.window: Any = None

    def save(self, original: str, form: dict[str, str]) -> str:
        radio, error = apply_form(self.settings, original, form)
        if radio is None:
            return error
        save_settings(self.settings)
        if radio["connection"] == "lan" and form.get("password"):
            set_password(radio, str(form["password"]))
        threading.Thread(target=self.launch, args=(radio,), daemon=True).start()
        return ""

    def launch(self, radio: dict[str, Any]) -> None:
        self.settings["last_radio"] = radio["name"]
        save_settings(self.settings)
        self.window.set_title(f"{APP} — {radio['name']}")
        self.window.load_html(
            message_page(f"Démarrage de rigplane et connexion à {_esc(radio['name'])}…")
        )
        self.process = start_server(self.settings, radio)
        if not wait_until_ready(self.settings, self.process):
            log = (
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "rigplane/rigplane/Cache/logs/rigplane.log"
            )
            self.window.load_html(
                message_page(
                    "rigplane n'a pas démarré. Vérifiez qu'il ne tourne pas déjà "
                    f"dans une autre fenêtre (port {self.settings['port']}) et, en "
                    "USB, que le port COM est le bon.<br>"
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
        "--disable-backgrounding-occluded-windows "
        # RX audio starts in LIVE at launch, before any click in the window.
        "--autoplay-policy=no-user-gesture-required",
    )
    import webview

    app = App()
    page, radio = start_choice(app.settings)
    if "--setup" in sys.argv:
        page = "choose" if page != "setup" else "setup"
    first_page = {
        "setup": lambda: setup_page(app.settings),
        "choose": lambda: choose_page(app.settings),
        "launch": lambda: message_page("Démarrage…"),
    }[page]()
    app.window = webview.create_window(
        APP,
        html=first_page,
        js_api=SetupApi(app),
        width=1920,
        height=1080,
        maximized=True,
    )
    app.window.events.closed += app.on_closed
    # pywebview opens a private session by default, which forgets the UI's
    # saved choices (layout, tuning step, selected memory bank) on every
    # launch; keep them in a profile folder instead.
    webview.start(
        (lambda: app.launch(radio)) if page == "launch" and radio else None,
        private_mode=False,
        storage_path=str(SETTINGS_PATH.parent / "webview"),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        run_server(sys.argv[2:])
    else:
        main()
