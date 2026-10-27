"""
Light The Night — Web-Switch Agent
Runs on a Raspberry Pi (full Linux, not MicroPython).
Watches the Firestore queue and either controls the relay OR sends OSC to QLab.

SETUP:
  pip install requests

CONFIGURE:
  1. Set RELAY_BASE_URL to your web-controlled power strip's local HTTP address.
     Example: "http://admin:1234@192.168.8.250"
  2. All other settings (QLab IP/port, OSC cues) are read from Firestore — change
     them in Mission Control without touching this file.
  3. On startup the agent detects its own LAN IP (WiFi or Ethernet — doesn't matter)
     and writes it to Firestore so Mission Control shows green and the correct IP.

RUN:
  python3 webswitch_agent_2025.py
  (or use the webswitch.service systemd unit to run at boot)
"""

import time
import json
import socket
import re
import threading
import requests
import ssl
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    import RPi.GPIO as _GPIO
    _GPIO.setmode(_GPIO.BCM)
    _GPIO_OK = True
    print("[gpio] RPi.GPIO ready (BCM mode)")
except Exception:
    _GPIO_OK = False
    print("[gpio] RPi.GPIO not available — GPIO commands will be skipped")

try:
    import serial as _serial
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

# ── Firebase config (matches web app) ──────────────────────────────────────────
FIREBASE_API_KEY = "AIzaSyBYsQCbHZ6r2KeqJ3-dgmFiR1mZ_IFZ-10"
FIREBASE_PROJECT = "light-the-night-2025"

# ── Your relay / web-controlled power strip ────────────────────────────────────
# Format depends on your device. Examples:
#   Digital Loggers:  http://admin:pass@192.168.1.100/outlet?1=ON
#   Generic HTTP:     http://192.168.1.100/outlet/1/on
RELAY_BASE_URL = "http://admin:1234@192.168.8.250"

# ── Arduino serial port ────────────────────────────────────────────────────────
# Set to the serial port the Arduino is connected to. Common values:
#   /dev/ttyS0    (RPi built-in UART after raspi-config)
#   /dev/ttyAMA0  (RPi built-in UART, older Pi or with BT disabled)
#   /dev/ttyUSB0  (USB-to-serial adapter)
ARDUINO_PORT     = "/dev/ttyS0"
ARDUINO_BAUDRATE = 9600
_arduino = None

def get_arduino():
    global _arduino
    if not _SERIAL_OK:
        return None
    if _arduino and _arduino.is_open:
        return _arduino
    try:
        _arduino = _serial.Serial(ARDUINO_PORT, ARDUINO_BAUDRATE, timeout=1)
        time.sleep(2)  # wait for Arduino reset after serial open
        print(f"[arduino] connected on {ARDUINO_PORT}")
    except Exception as e:
        print(f"[arduino] could not open {ARDUINO_PORT}: {e}")
        _arduino = None
    return _arduino

def send_arduino(pin, state, pulse_ms=500):
    ser = get_arduino()
    if not ser:
        print(f"[arduino] skipped — no connection (pin {pin} {state})")
        return
    if state == "PULSE":
        cmd = f"O{pin}PULSE{pulse_ms}\n"
    elif state == "HIGH":
        cmd = f"O{pin}ON\n"
    else:
        cmd = f"O{pin}OFF\n"
    try:
        ser.write(cmd.encode())
        print(f"[arduino] sent {cmd.strip()}")
    except Exception as e:
        print(f"[arduino] send error: {e}")
        _arduino = None  # force reconnect next time

# ── Poll interval ──────────────────────────────────────────────────────────────
POLL_INTERVAL_S       = 0.1   # check for new queue items every 100ms
RELAY_POLL_INTERVAL_S = 5     # poll relay for live state every 5 seconds
TOKEN_REFRESH_S       = 3000  # refresh Firebase token every ~50 min
HEARTBEAT_INTERVAL_S  = 30    # write online heartbeat to Firestore every 30 s
HEALTH_PORT           = 8080  # tiny HTTP health server port

# ── Firestore REST base ────────────────────────────────────────────────────────
FS_BASE = (f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}"
           f"/databases/(default)/documents")


# ── Anonymous Firebase auth ────────────────────────────────────────────────────
def sign_in():
    url = (f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
           f"?key={FIREBASE_API_KEY}")
    r = requests.post(url, json={"returnSecureToken": True}, timeout=10)
    r.raise_for_status()
    d = r.json()
    print(f"[auth] signed in as {d['localId'][:8]}…")
    return d["idToken"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Firestore helpers ──────────────────────────────────────────────────────────
def _fs_val(field_dict):
    """Extract a Python value from a Firestore field value dict."""
    if "stringValue"  in field_dict: return field_dict["stringValue"]
    if "integerValue" in field_dict: return int(field_dict["integerValue"])
    if "doubleValue"  in field_dict: return float(field_dict["doubleValue"])
    if "booleanValue" in field_dict: return bool(field_dict["booleanValue"])
    return None


def fs_list_unprocessed(token, col_path):
    """Query only documents where processed == false."""
    parent = f"{FS_BASE}/{col_path.rsplit('/', 1)[0]}"
    col_id = col_path.rsplit('/', 1)[-1]
    url = f"{parent}:runQuery?key={FIREBASE_API_KEY}"
    body = {
        "structuredQuery": {
            "from": [{"collectionId": col_id}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": "processed"},
                    "op": "EQUAL",
                    "value": {"booleanValue": False}
                }
            },
            "limit": 50
        }
    }
    r = requests.post(url, headers={**_headers(token), "Content-Type": "application/json"},
                      json=body, timeout=10)
    if r.status_code == 200:
        return [item["document"] for item in r.json() if "document" in item]
    return []


def fs_get(token, doc_path):
    url = f"{FS_BASE}/{doc_path}?key={FIREBASE_API_KEY}"
    r = requests.get(url, headers=_headers(token), timeout=10)
    if r.status_code == 200:
        return {k: _fs_val(v) for k, v in r.json().get("fields", {}).items()}
    return {}


def fs_patch(token, doc_path, py_fields):
    """Write fields to a Firestore doc (merge-style via field mask)."""
    fs_fields = {}
    for k, v in py_fields.items():
        if isinstance(v, bool):   fs_fields[k] = {"booleanValue": v}
        elif isinstance(v, int):  fs_fields[k] = {"integerValue": str(v)}
        elif isinstance(v, float):fs_fields[k] = {"doubleValue": v}
        else:                      fs_fields[k] = {"stringValue": str(v)}
    mask = "&".join(f"updateMask.fieldPaths={k}" for k in py_fields)
    url = f"{FS_BASE}/{doc_path}?key={FIREBASE_API_KEY}&{mask}"
    requests.patch(url, headers={**_headers(token), "Content-Type": "application/json"},
                   json={"fields": fs_fields}, timeout=10)


# ── GPIO control (Raspberry Pi BCM pins) ──────────────────────────────────────
_gpio_setup_pins = set()

def send_gpio(pin, state, pulse_ms=500):
    if not _GPIO_OK:
        print(f"[gpio] skipped — RPi.GPIO not available (pin {pin} {state})")
        return
    if pin not in _gpio_setup_pins:
        _GPIO.setup(pin, _GPIO.OUT, initial=_GPIO.LOW)
        _gpio_setup_pins.add(pin)
    if state == "PULSE":
        _GPIO.output(pin, _GPIO.HIGH)
        time.sleep(pulse_ms / 1000.0)
        _GPIO.output(pin, _GPIO.LOW)
        print(f"[gpio] pin {pin} pulsed for {pulse_ms}ms")
    elif state == "HIGH":
        _GPIO.output(pin, _GPIO.HIGH)
        print(f"[gpio] pin {pin} HIGH")
    else:
        _GPIO.output(pin, _GPIO.LOW)
        print(f"[gpio] pin {pin} LOW")


# ── OSC sender (no external library — hand-crafted minimal UDP packet) ─────────
def _osc_pad(b):
    """Null-terminate and pad bytes to 4-byte boundary."""
    b = b + b"\x00"
    while len(b) % 4:
        b += b"\x00"
    return b


def send_osc(host, port, address):
    """Send an OSC message with no arguments (e.g. /go to QLab)."""
    packet = _osc_pad(address.encode()) + _osc_pad(b",")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(packet, (host, int(port)))
    print(f"[osc] sent {address} → {host}:{port}")


# ── Outlet state cache (for writing back to Firestore) ────────────────────────
_outlet_states = {}  # {outlet_num: "on"|"off"}


# ── Relay control ──────────────────────────────────────────────────────────────
def control_outlet(outlet, state):
    try:
        if state == "toggle":
            actual = "off" if _outlet_states.get(outlet) == "on" else "on"
        else:
            actual = state
        url = f"{RELAY_BASE_URL}/outlet?{outlet}={actual.upper()}"
        r = requests.get(url, timeout=3)
        print(f"[relay] outlet {outlet} → {actual}  ({r.status_code})")
        if r.status_code == 200:
            _outlet_states[outlet] = actual
    except Exception as e:
        print(f"[relay] error: {e}")


def push_state(token):
    """Write current outlet states to Firestore so the web UI LEDs update."""
    if not _outlet_states:
        return
    url = (f"{FS_BASE}/webswitch/state"
           f"?key={FIREBASE_API_KEY}&updateMask.fieldPaths=states")
    requests.patch(url,
                   headers={**_headers(token), "Content-Type": "application/json"},
                   json={"fields": {"states": {"mapValue": {"fields": {str(k): {"stringValue": v} for k, v in _outlet_states.items()}}}}},
                   timeout=5)


def poll_relay_state(token):
    """Poll the relay's status page and push any state changes to Firestore."""
    try:
        r = requests.get(f"{RELAY_BASE_URL}/index.htm", timeout=5)
        if r.status_code != 200:
            return
        # outlet?N=ON in href means outlet N is currently OFF (button offers to turn ON)
        # outlet?N=OFF in href means outlet N is currently ON
        found = re.findall(r'outlet\?(\d+)=(ON|OFF)', r.text)
        changed = False
        for outlet_str, action in found:
            current = "off" if action == "ON" else "on"
            if _outlet_states.get(int(outlet_str)) != current:
                _outlet_states[int(outlet_str)] = current
                changed = True
        if changed:
            push_state(token)
            print(f"[relay] state sync: { {k: v for k, v in _outlet_states.items()} }")
    except Exception as e:
        print(f"[relay] poll error: {e}")


# ── Config (QLab IP/port from Firestore) ───────────────────────────────────────
_qlab_cache = {"ip": "127.0.0.1", "port": 53000, "fetched": 0}


def get_qlab_config(token):
    if time.time() - _qlab_cache["fetched"] > 60:
        cfg = fs_get(token, "webswitch/config")
        if cfg.get("qlabIp"):  _qlab_cache["ip"]   = cfg["qlabIp"]
        if cfg.get("qlabPort"):_qlab_cache["port"] = int(cfg["qlabPort"])
        _qlab_cache["fetched"] = time.time()
    return _qlab_cache["ip"], _qlab_cache["port"]


# ── Startup flush — discard queued commands that piled up while offline ────────
def flush_stale_queue(token):
    """Mark all currently unprocessed queue items as processed without running them.
    Called once on startup so a backlog of offline commands is silently dropped."""
    docs = fs_list_unprocessed(token, "webswitch/queueRoot/queue")
    if not docs:
        return
    print(f"[queue] flushing {len(docs)} stale item(s) from offline backlog — not executing")
    for doc in docs:
        doc_name = doc["name"].split("/documents/")[-1]
        try:
            fs_patch(token, doc_name, {"processed": True})
        except Exception as e:
            print(f"[queue] flush error on {doc_name}: {e}")


# ── Queue processor ────────────────────────────────────────────────────────────
def process_queue(token):
    docs = fs_list_unprocessed(token, "webswitch/queueRoot/queue")
    for doc in docs:
        fields = {k: _fs_val(v) for k, v in doc.get("fields", {}).items()}

        if fields.get("processed"):
            continue

        doc_name = doc["name"].split("/documents/")[-1]
        step_type = str(fields.get("type", "power"))

        if step_type == "osc":
            address = str(fields.get("address", "/go"))
            default_ip, default_port = get_qlab_config(token)
            qlab_ip   = str(fields["qlabIp"])   if fields.get("qlabIp")   else default_ip
            qlab_port = int(fields["qlabPort"])  if fields.get("qlabPort") else default_port
            try:
                send_osc(qlab_ip, qlab_port, address)
            except Exception as e:
                print(f"[osc] send error: {e}")

        elif step_type in ("gpio", "arduino"):
            pin      = int(fields.get("pin", 2))
            state    = str(fields.get("state", "PULSE")).upper()
            pulse_ms = int(fields.get("pulseMs", 500))
            send_gpio(pin, state, pulse_ms)

        elif step_type == "air":
            outlet  = fields.get("outlet")
            state   = str(fields.get("state", "pulse")).lower()
            pulse_ms = int(fields.get("pulseMs", 500))
            if outlet is not None:
                if state == "pulse":
                    control_outlet(int(outlet), "on")
                    time.sleep(pulse_ms / 1000.0)
                    control_outlet(int(outlet), "off")
                    print(f"[air] outlet {outlet} pulsed for {pulse_ms}ms")
                elif state in ("on", "off"):
                    control_outlet(int(outlet), state)

        else:  # "power" (default)
            outlet = fields.get("outlet")
            state  = str(fields.get("state", "")).lower()
            if outlet is not None and state in ("on", "off", "toggle"):
                control_outlet(int(outlet), state)
                push_state(token)

        fs_patch(token, doc_name, {"processed": True})


# ── Local IP detection ────────────────────────────────────────────────────────
def get_local_ip():
    """Return the Pi's current LAN IP (works on WiFi or Ethernet)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ── SSL cert (self-signed, generated once on first run) ───────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CERT_PATH  = os.path.join(_SCRIPT_DIR, "cert.pem")
_KEY_PATH   = os.path.join(_SCRIPT_DIR, "key.pem")

def ensure_ssl_cert():
    if not (os.path.exists(_CERT_PATH) and os.path.exists(_KEY_PATH)):
        print("[ssl] Generating self-signed certificate…")
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", _KEY_PATH, "-out", _CERT_PATH,
            "-days", "3650", "-nodes", "-subj", "/CN=ltn-pi"
        ], check=True, capture_output=True)
        print(f"[ssl] Certificate written to {_CERT_PATH}")
    else:
        print(f"[ssl] Using existing certificate at {_CERT_PATH}")
    return True


# ── HTTP command server (health + direct OSC/GPIO from tablets) ───────────────
class _HealthHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # Serve cert so tablets can download and trust it
        if self.path == "/cert.pem":
            try:
                with open(_CERT_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-pem-file")
                self.send_header("Content-Disposition", 'attachment; filename="ltn-pi.pem"')
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            return

        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            cmd_type = body.get("type", "osc")

            if cmd_type == "osc":
                send_osc(
                    str(body.get("qlabIp", "127.0.0.1")),
                    int(body.get("qlabPort", 53000)),
                    str(body.get("address", "/go"))
                )
            elif cmd_type == "gpio":
                send_gpio(
                    int(body.get("pin", 2)),
                    str(body.get("state", "PULSE")).upper(),
                    int(body.get("pulseMs", 500))
                )
            elif cmd_type == "power":
                control_outlet(int(body.get("outlet", 1)), str(body.get("state", "on")).lower())

            resp = b'{"ok":true}'
            self.send_response(200)
        except Exception as e:
            print(f"[http] error: {e}")
            resp = json.dumps({"ok": False, "error": str(e)}).encode()
            self.send_response(500)

        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self._cors()
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *_):
        pass  # suppress access logs

_using_https = False

def start_health_server():
    global _using_https
    srv = HTTPServer(("0.0.0.0", HEALTH_PORT), _HealthHandler)
    try:
        ensure_ssl_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(_CERT_PATH, _KEY_PATH)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        _using_https = True
        print(f"[http] HTTPS command server listening on :{HEALTH_PORT}")
    except Exception as e:
        _using_https = False
        print(f"[http] SSL setup failed ({e}) — falling back to HTTP")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


# ── Heartbeat + self-announce ─────────────────────────────────────────────────
def write_heartbeat(token, my_url):
    """Write online status and IP to Firestore so Mission Control shows green."""
    import datetime
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
    # agentHeartbeat doc
    fs_patch(token, "webswitch/agentHeartbeat", {"online": True, "ts": now_iso, "ip": my_url})
    # also write baseUrl into config so Mission Control ping works
    fs_patch(token, "webswitch/config", {"baseUrl": my_url})


# ── Self-update (checks GitHub every 5 min, restarts via systemd if changed) ──
GITHUB_RAW = ("https://raw.githubusercontent.com/KChristman25/"
              "Light-the-Night/2026/rpi/webswitch_agent_2025.py")
UPDATE_INTERVAL_S = 300  # check every 5 minutes

def _file_md5(path):
    import hashlib
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return None

def self_update_loop():
    import sys
    while True:
        time.sleep(UPDATE_INTERVAL_S)
        try:
            r = requests.get(GITHUB_RAW, timeout=15)
            if r.status_code != 200:
                continue
            new_content = r.content
            import hashlib
            new_hash = hashlib.md5(new_content).hexdigest()
            old_hash = _file_md5(os.path.abspath(__file__))
            if new_hash != old_hash:
                print("[update] New version detected — applying and restarting…")
                with open(os.path.abspath(__file__), "wb") as f:
                    f.write(new_content)
                # systemd Restart=always will bring it back up
                sys.exit(0)
            else:
                print("[update] Up to date.")
        except Exception as e:
            print(f"[update] check failed: {e}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=== LTN Web-Switch Agent ===")
    # Start self-update checker in background
    t = threading.Thread(target=self_update_loop, daemon=True)
    t.start()
    start_health_server()
    my_ip  = get_local_ip()
    scheme = "https" if _using_https else "http"
    my_url = f"{scheme}://{my_ip}:{HEALTH_PORT}"
    print(f"[agent] LAN address: {my_url}")

    token = sign_in()
    last_refresh   = time.time()
    last_relay_poll = 0
    last_heartbeat  = 0

    # Announce immediately on startup
    try:
        write_heartbeat(token, my_url)
        print(f"[agent] announced baseUrl={my_url} to Firestore")
    except Exception as e:
        print(f"[agent] initial heartbeat failed: {e}")

    # Drop any commands that queued up while the Pi was offline
    try:
        flush_stale_queue(token)
    except Exception as e:
        print(f"[queue] startup flush failed: {e}")

    while True:
        if time.time() - last_refresh > TOKEN_REFRESH_S:
            try:
                token = sign_in()
                last_refresh = time.time()
            except Exception as e:
                print(f"[auth] refresh failed: {e}")

        try:
            process_queue(token)
        except Exception as e:
            print(f"[queue] error: {e}")

        if time.time() - last_relay_poll >= RELAY_POLL_INTERVAL_S:
            poll_relay_state(token)
            last_relay_poll = time.time()

        if time.time() - last_heartbeat >= HEARTBEAT_INTERVAL_S:
            try:
                # Re-detect IP in case network changed (WiFi → Ethernet handoff)
                new_ip  = get_local_ip()
                new_url = f"{'https' if _using_https else 'http'}://{new_ip}:{HEALTH_PORT}"
                if new_url != my_url:
                    my_url = new_url
                    print(f"[agent] IP changed → {my_url}")
                write_heartbeat(token, my_url)
            except Exception as e:
                print(f"[heartbeat] error: {e}")
            last_heartbeat = time.time()

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
