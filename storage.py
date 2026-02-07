import json
import os
from typing import Dict, List, Union

DATA_FILE = "data.json"

def load_data() -> Dict[str, List[str]]:
    """Loads the data from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {}
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If file is corrupted or empty, return empty dict
        return {}

def save_data(data: Dict[str, List[str]]) -> None:
    """Saves the data to the JSON file."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving data: {e}")

def get_student_classes(chat_id: Union[str, int]) -> List[str]:
    """Returns the list of classes for a given chat_id."""
    data = load_data()
    return data.get(str(chat_id), [])

def add_class(chat_id: Union[str, int], class_name: str) -> bool:
    """Adds a class to the student's list. Returns True if added, False if already exists."""
    data = load_data()
    chat_id_str = str(chat_id)
    
    if chat_id_str not in data:
        data[chat_id_str] = []
    
    if class_name in data[chat_id_str]:
        return False
    
    data[chat_id_str].append(class_name)
    save_data(data)
    return True

def remove_class(chat_id: Union[str, int], class_name: str) -> bool:
    """Removes a class from the student's list. Returns True if removed, False if not found."""
    data = load_data()
    chat_id_str = str(chat_id)
    
    if chat_id_str not in data:
        return False
    
    if class_name in data[chat_id_str]:
        data[chat_id_str].remove(class_name)
        # Clean up empty lists if desired, or keep them empty
        # if len(data[chat_id_str]) == 0:
        #     del data[chat_id_str]
        save_data(data)
        return True
    
    return False
