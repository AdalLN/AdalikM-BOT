import os

DB_PATH = os.environ.get("DB_PATH", "AdalikM.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # requerido
STORAGE_DIR = os.environ.get("STORAGE_DIR", "storage")
EXPIRY_HOURS = int(os.environ.get("EXPIRY_HOURS", "24"))
MAX_BYTES = int(os.environ.get("MAX_BYTES", 2_000_000))
MIN_INTERVAL = float(os.environ.get("MIN_INTERVAL", 1.0))
AUTO_PURGE_INTERVAL = int(os.environ.get("AUTO_PURGE_INTERVAL", 604800))

AUTH_FORWARDERS = {
    int(x)
    for x in os.environ.get("AUTH_FORWARDERS", "").split(",")
    if x.strip().isdigit()
}

ALLOWED_UPLOADERS = {
    int(x)
    for x in os.environ.get("ALLOWED_UPLOADERS", "").split(",")
    if x.strip().isdigit()
}
