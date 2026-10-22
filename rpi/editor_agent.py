#!/usr/bin/env python3
import os, time, json, signal, subprocess
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "light-the-night-2025"
SERVICE_ACCOUNT = "/home/pi/webswitch/serviceAccount.json"
APP_DIR = "/home/pi/webswitch"
FILE_PATH = os.path.join(APP_DIR, "engine.py")     # which file we expose
DOC_PATH = ("editor", "files", "engine.py")        # /editor/files/engine.py
CMDS_COL = ("editor", "commands")                  # /editor/commands

# ---- Firestore init ----
cred = credentials.Certificate(SERVICE_ACCOUNT)
firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
db = firestore.client()

def _now_iso(): return datetime.utcnow().isoformat() + "Z"

def read_local() -> str:
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        return f.read()

def write_local(content: str):
    tmp = FILE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, FILE_PATH)

def ensure_seed_doc():
    """If Firestore doc is missing, create it from local file as version 1."""
    doc_ref = db.document(*DOC_PATH)
    snap = doc_ref.get()
    if not snap.exists:
        content = read_local()
        doc_ref.set({
            "name": "engine.py",
            "content": content,
            "version": 1,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "updatedBy": "pi",
        })
        print("[agent] Seeded editor/files/engine.py (v1) from local")
    else:
        print("[agent] Doc already exists; leaving content as-is")

def restart_service():
    try:
        subprocess.run(["/usr/bin/sudo", "/bin/systemctl", "restart", "webswitch"], check=True)
        print("[agent] restarted webswitch service")
    except Exception as e:
        print("[agent] restart error:", e)

def main():
    ensure_seed_doc()

    # Subscribe to file doc: pull updates to disk when version increases
    last_version = None
    def on_file(snap, changes, read_time):
        nonlocal last_version
        for doc in snap:
            d = doc.to_dict() or {}
            v = int(d.get("version", 0))
            if last_version is None:
                last_version = v
                print(f"[agent] file watch attached (v{v})")
                continue
            if v > last_version:
                print(f"[agent] detected remote save v{v}; writing to disk")
                write_local(d.get("content", ""))
                last_version = v

    unsub_file = db.document(*DOC_PATH).on_snapshot(on_file)

    # Subscribe to command queue
    def on_cmds(col_snapshot, changes, read_time):
        for c in changes:
            if c.type.name != "ADDED": continue
            data = c.document.to_dict() or {}
            typ = (data.get("type") or "").lower()
            if typ == "restart":
                restart_service()

    unsub_cmds = db.collection(*CMDS_COL).order_by("createdAt", direction=firestore.Query.DESCENDING).limit(20).on_snapshot(on_cmds)

    # Push heartbeat every ~30s (optional, visible in doc)
    doc_ref = db.document(*DOC_PATH)
    try:
        while True:
            time.sleep(30)
            try:
                doc_ref.set({"piHeartbeat": _now_iso()}, merge=True)
            except Exception:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        unsub_file(); unsub_cmds()

if __name__ == "__main__":
    main()
