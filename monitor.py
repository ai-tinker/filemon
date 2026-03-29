import time
import hashlib
import json
import os
import fnmatch
import logging
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# ===================== PATH =====================
BASE_DIR = "/opt/filemon"
CONFIG_FILE = f"{BASE_DIR}/checkedfile.conf"
HASH_DB = "/var/lib/filemon/file_hash.json"
LOG_FILE = "/var/log/filemon.log"
ENV_FILE = f"{BASE_DIR}/.env"

# ===================== LOAD ENV =====================
load_dotenv(ENV_FILE)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")

NOTIF_CHANNEL = os.getenv("NOTIF_CHANNEL", "telegram").lower()

# ===================== GLOBAL =====================
patterns = []
exclude_dirs = []
critical_files = []
watch_dirs = []
file_hashes = {}
last_mtime = 0

# ===================== LOGGING =====================
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
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }, timeout=5)
    except Exception as e:
        log(f"[ERROR] Telegram failed: {e}")

# ===================== WHATSAPP =====================
def send_whatsapp(message):
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        log("[WARNING] WhatsApp not configured")
        return

    try:
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        payload = {
            "device_key": os.getenv("WHATSAPP_DEVICE_KEY", "device-1"),
            "to": WHATSAPP_NUMBER,
            "message": message
        }

        response = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            log(f"[ERROR] WhatsApp API {response.status_code}: {response.text}")

    except Exception as e:
        log(f"[ERROR] WhatsApp failed: {e}")

# ===================== DISPATCH =====================
def send_notif(message):
    if NOTIF_CHANNEL == "telegram":
        send_telegram(message)

    elif NOTIF_CHANNEL == "whatsapp":
        send_whatsapp(message)

    elif NOTIF_CHANNEL == "both":
        send_telegram(message)
        send_whatsapp(message)

    else:
        log(f"[WARNING] Unknown NOTIF_CHANNEL: {NOTIF_CHANNEL}")

# ===================== CONFIG =====================
def load_config():
    global patterns, exclude_dirs, critical_files, watch_dirs

    patterns = []
    exclude_dirs = []
    critical_files = []
    watch_dirs = []

    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("!"):
                exclude_dirs.append(line[1:])

            elif line.startswith("@critical:"):
                critical_files.append(line.split(":",1)[1])

            elif line.startswith("@watch:"):
                watch_dirs.append(line.split(":",1)[1])

            else:
                patterns.append(line)

def reload_config_if_needed():
    global last_mtime
    mtime = os.path.getmtime(CONFIG_FILE)

    if mtime != last_mtime:
        log("[INFO] Reload config")
        load_config()
        last_mtime = mtime

# ===================== HASH =====================
def load_hash():
    global file_hashes
    if os.path.exists(HASH_DB):
        with open(HASH_DB, "r") as f:
            file_hashes = json.load(f)

def save_hash():
    with open(HASH_DB, "w") as f:
        json.dump(file_hashes, f, indent=2)

def get_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except:
        return None

# ===================== FILTER =====================
def is_excluded(path):
    for d in exclude_dirs:
        if d in path:
            return True
    return False

def is_monitored(path):
    for p in patterns:
        if fnmatch.fnmatch(path, p):
            return True
    return False

def is_critical(path):
    for c in critical_files:
        if path.endswith(c):
            return True
    return False

# ===================== HANDLER =====================
class MonitorHandler(FileSystemEventHandler):

    def process(self, path, event_type):
        if not os.path.isfile(path):
            return

        if is_excluded(path):
            return

        if not is_monitored(path):
            return

        new_hash = get_hash(path)
        old_hash = file_hashes.get(path)

        if event_type == "deleted":
            msg = f"[DELETE] {path}"
            log(msg)
            send_notif(msg)
            file_hashes.pop(path, None)

        elif old_hash != new_hash:
            if is_critical(path):
                msg = f"[CRITICAL] {path}"
            else:
                msg = f"[CHANGE] {path}"

            log(msg)
            send_notif(msg)
            file_hashes[path] = new_hash

        save_hash()

    def on_modified(self, event):
        self.process(event.src_path, "modified")

    def on_created(self, event):
        self.process(event.src_path, "created")

    def on_deleted(self, event):
        self.process(event.src_path, "deleted")

# ===================== OBSERVER =====================
def start_observer():
    observer = Observer()

    for path in watch_dirs:
        if os.path.exists(path):
            observer.schedule(MonitorHandler(), path, recursive=True)
            log(f"[WATCHING] {path}")
        else:
            log(f"[WARNING] Path not found: {path}")

    observer.start()
    return observer

# ===================== MAIN =====================
if __name__ == "__main__":
    log("[START] File Monitor running")

    load_config()
    load_hash()

    observer = start_observer()

    try:
        while True:
            reload_config_if_needed()
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()