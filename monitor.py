import time
import os
import fnmatch
import json
import hashlib
import logging
import requests
import socket
from dotenv import load_dotenv

# ===================== CONFIG =====================
BASE_DIR = "/opt/filemon"
CONFIG_FILE = f"{BASE_DIR}/checkedfile.conf"
HASH_DB = "/var/lib/filemon/file_hash.json"
LOG_FILE = "/var/log/filemon.log"
ENV_FILE = f"{BASE_DIR}/.env"

SCAN_INTERVAL = 60  # detik

load_dotenv(ENV_FILE)

# ===================== ENV =====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "").strip()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "").strip()
WHATSAPP_DEVICE_KEY = os.getenv("WHATSAPP_DEVICE_KEY", "device-1").strip()

NOTIF_CHANNEL = os.getenv("NOTIF_CHANNEL", "telegram").lower()
HOST_ALIAS = os.getenv("HOST_ALIAS") or socket.gethostname()

# ===================== LOG =====================
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def log(msg):
    print(msg)
    logging.info(msg)

# ===================== TELEGRAM =====================
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("[WARNING] Telegram not configured")
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=5
        )
    except Exception as e:
        log(f"[ERROR] Telegram failed: {e}")

# ===================== WHATSAPP =====================
def send_whatsapp(message):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN or not WHATSAPP_NUMBER:
        log("[WARNING] WhatsApp not configured")
        return

    try:
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "device_key": WHATSAPP_DEVICE_KEY,
            "to": WHATSAPP_NUMBER,
            "message": message
        }

        response = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        log(f"[DEBUG] WA Status: {response.status_code}")
        log(f"[DEBUG] WA Response: {response.text}")

    except Exception as e:
        log(f"[ERROR] WhatsApp failed: {e}")

# ===================== DISPATCH =====================
def send_batch(events):
    if not events:
        return

    message = f"🚨 {HOST_ALIAS}\n\n" + "\n\n".join(events)

    if NOTIF_CHANNEL == "telegram":
        send_telegram(message)

    elif NOTIF_CHANNEL == "whatsapp":
        send_whatsapp(message)

    elif NOTIF_CHANNEL == "both":
        send_telegram(message)
        send_whatsapp(message)

    else:
        log(f"[WARNING] Unknown NOTIF_CHANNEL: {NOTIF_CHANNEL}")

# ===================== FORMAT =====================
def format_event(event_type, path):
    if event_type == "CHANGE":
        return f"⚠️ CHANGE\n📄 {path}"

    elif event_type == "DELETE":
        return f"❌ DELETE\n📄 {path}"

    elif event_type == "CRITICAL":
        return f"🔥 CRITICAL\n📄 {path}"

    return f"{event_type}\n{path}"

# ===================== CONFIG =====================
patterns = []
watch_dirs = []
exclude_dirs = []
critical_files = []

def load_config():
    global patterns, watch_dirs, exclude_dirs, critical_files
    patterns, watch_dirs, exclude_dirs, critical_files = [], [], [], []

    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("@watch:"):
                watch_dirs.append(line.split(":",1)[1])

            elif line.startswith("!"):
                exclude_dirs.append(line[1:])

            elif line.startswith("@critical:"):
                critical_files.append(line.split(":",1)[1])

            else:
                patterns.append(line)

# ===================== HASH =====================
def get_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except:
        return None

def get_info(path):
    try:
        stat = os.stat(path)
        return {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "hash": get_hash(path)
        }
    except:
        return None

# ===================== DB =====================
def load_db():
    if os.path.exists(HASH_DB):
        with open(HASH_DB) as f:
            return json.load(f)
    return {}

def save_db(db):
    try:
        with open(HASH_DB, "w") as f:
            json.dump(db, f, indent=2)
    except Exception as e:
        log(f"[ERROR] save_db failed: {e}")

# ===================== FILTER =====================
def is_excluded(path):
    return any(d in path for d in exclude_dirs)

def is_match(path):
    return any(fnmatch.fnmatch(path, p) for p in patterns)

def is_critical(path):
    return any(path.endswith(c) for c in critical_files)

# ===================== SCAN =====================
def scan(db):
    current_files = {}
    events = []

    for base in watch_dirs:
        for root, dirs, files in os.walk(base):
            if is_excluded(root):
                continue

            for f in files:
                full = os.path.join(root, f)

                if not is_match(full):
                    continue

                info = get_info(full)
                if not info:
                    continue

                current_files[full] = info

                old = db.get(full)

                if old != info:
                    if is_critical(full):
                        events.append(format_event("CRITICAL", full))
                    else:
                        events.append(format_event("CHANGE", full))

    # DELETE detection
    for path in list(db.keys()):
        if path not in current_files:
            events.append(format_event("DELETE", path))

    return current_files, events

# ===================== MAIN =====================
if __name__ == "__main__":
    log("[START] File monitor (polling mode)")

    load_config()

    # pastikan directory ada
    os.makedirs(os.path.dirname(HASH_DB), exist_ok=True)

    db = load_db()

    while True:
        try:
            new_db, events = scan(db)

            if events:
                send_batch(events)

            db = new_db
            save_db(db)

        except Exception as e:
            log(f"[ERROR] {e}")

        time.sleep(SCAN_INTERVAL)
        
        