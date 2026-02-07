from pathlib import Path

# --- KONFIGURATION ---
TOKEN = "6768180501:AAEd22Mx55pILCHywr7Dv_Omk7NQ1jrecaU"
USER_VPLAN = 'vplan'
PASSWORD_VPLAN = 'vp@DKS01099'

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
COUNTER_FILE = BASE_DIR / "template_counter.txt"
STATE_FILE = BASE_DIR / "state.json"

# user_Klassen moved to data.json managed by storage.py
