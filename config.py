import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- KONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_VPLAN = os.getenv("USER_VPLAN", "vplan")
PASSWORD_VPLAN = os.getenv("PASSWORD_VPLAN")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
COUNTER_FILE = BASE_DIR / "template_counter.txt"
STATE_FILE = BASE_DIR / "state.json"

# user_Klassen moved to data.json managed by storage.py
