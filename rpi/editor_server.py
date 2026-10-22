#!/usr/bin/env python3
import os, subprocess, json, secrets
from flask import Flask, request, jsonify, make_response

# ---- settings ----
APP_DIR = "/home/pi/webswitch"
ALLOWED = {"engine.py": os.path.join(APP_DIR, "engine.py")}
TOKEN_FILE = os.path.join(APP_DIR, "editor_token.txt")
SERVICE_NAME = "webswitch"  # systemd unit name

app = Flask(__name__)

def _token():
    # Create a token on first run if absent
    if not os.path.exists(TOKEN_FILE):
        t = secrets.token_hex(16)
        with open(TOKEN_FILE, "w") as f: f.write(t)
        os.chmod(TOKEN_FILE, 0o600)
        return t
    return open(TOKEN_FILE).read().strip()

AUTH_TOKEN = None  # will lazy-load

def require_auth():
    global AUTH_TOKEN
    if AUTH_TOKEN is None: AUTH_TOKEN = _token()
    sent = request.headers.get("X-Auth") or request.args.get("token","")
    if sent != AUTH_TOKEN:
        return make_response(("Forbidden", 403))
    return None

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Auth"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.route("/health")
def health():
    return jsonify({"ok": True})

@app.route("/list")
def list_files():
    if (r := require_auth()): return r
    return jsonify({"files": list(ALLOWED.keys())})

@app.route("/file", methods=["GET","POST","OPTIONS"])
def file_io():
    if request.method == "OPTIONS":
        return ("", 204)
    if (r := require_auth()): return r
    name = request.args.get("path") if request.method=="GET" else (request.json or {}).get("path")
    if name not in ALLOWED: return make_response(("Bad path", 400))
    path = ALLOWED[name]
    if request.method == "GET":
        with open(path, "r", encoding="utf-8") as f:
            return jsonify({"path": name, "content": f.read()})
    data = request.json or {}
    with open(path, "w", encoding="utf-8") as f:
        f.write(data.get("content",""))
    return jsonify({"saved": True})

@app.route("/service/status")
def svc_status():
    if (r := require_auth()): return r
    try:
        state = subprocess.run(["/bin/systemctl","is-active",SERVICE_NAME], capture_output=True, text=True, check=False).stdout.strip()
    except Exception as e:
        return jsonify({"status":"error","error":str(e)}), 500
    return jsonify({"status": state})

@app.route("/service/restart", methods=["POST"])
def svc_restart():
    if (r := require_auth()): return r
    try:
        # sudoers entry lets 'pi' restart without password (see installer below)
        subprocess.run(["/usr/bin/sudo","/bin/systemctl","restart",SERVICE_NAME], check=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    # Bind on all interfaces, port 8080
    app.run(host="0.0.0.0", port=8080)
