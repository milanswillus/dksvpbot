import json
import hashlib
from config import STATE_FILE

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Fehler beim Laden der State-Datei: {e}")
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern der State-Datei: {e}")

def calculate_hash(content):
    """Gibt den SHA256 Hash eines Strings oder Bytes zurück."""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()
