import json
import os
from typing import Dict, List, Union


DATA_FILE = "data.json"

def load_data():
    """Loads the data from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {}
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_data(data):
    """Saves the data to the JSON file."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving data: {e}")

def _get_user_entry(data, chat_id_str):
    """Helper to get user entry, migrating list to dict if necessary."""
    if chat_id_str not in data:
        return {"classes": [], "version": 0}
    
    entry = data[chat_id_str]
    if isinstance(entry, list):
        # Migration: convert list to dict
        return {"classes": entry, "version": 0}
    return entry

def get_student_classes(chat_id: Union[str, int]) -> List[str]:
    """Returns the list of classes for a given chat_id."""
    data = load_data()
    entry = _get_user_entry(data, str(chat_id))
    return entry["classes"]

def get_reset_version(chat_id: Union[str, int]) -> int:
    """Returns the reset version for a given chat_id."""
    data = load_data()
    entry = _get_user_entry(data, str(chat_id))
    return entry.get("version", 0)

def increment_reset_version(chat_id: Union[str, int]) -> int:
    """Increments the reset version for a user."""
    data = load_data()
    chat_id_str = str(chat_id)
    entry = _get_user_entry(data, chat_id_str)
    
    entry["version"] = entry.get("version", 0) + 1
    data[chat_id_str] = entry
    save_data(data)
    return entry["version"]

def add_class(chat_id: Union[str, int], class_name: str) -> bool:
    """Adds a class to the student's list."""
    data = load_data()
    chat_id_str = str(chat_id)
    entry = _get_user_entry(data, chat_id_str)
    
    if class_name in entry["classes"]:
        return False
    
    entry["classes"].append(class_name)
    data[chat_id_str] = entry
    save_data(data)
    return True

def remove_class(chat_id: Union[str, int], class_name: str) -> bool:
    """Removes a class from the student's list."""
    data = load_data()
    chat_id_str = str(chat_id)
    entry = _get_user_entry(data, chat_id_str)
    
    if class_name in entry["classes"]:
        entry["classes"].remove(class_name)
        data[chat_id_str] = entry
        save_data(data)
        return True
    
    return False
