from pathlib import Path

# --- KONFIGURATION ---
TOKEN = "PLACEHOLDER_TOKEN"
USER_VPLAN = 'vplan'
PASSWORD_VPLAN = 'PLACEHOLDER_PASSWORD'

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
COUNTER_FILE = BASE_DIR / "template_counter.txt"
STATE_FILE = BASE_DIR / "state.json"

# user_Klassen moved to data.json managed by storage.py
