import os
import json
from pathlib import Path

PROTOCOLS_FILE = Path(__file__).parent.parent / "config" / "protocols.json"

def load_protocols() -> dict:
    if not PROTOCOLS_FILE.exists():
        return {}
    try:
        with open(PROTOCOLS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Protocols] Error loading protocols: {e}")
        return {}

def save_protocols(data: dict):
    try:
        PROTOCOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROTOCOLS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Protocols] Error saving protocols: {e}")
        return False

def add_protocol(name: str, instructions: str):
    data = load_protocols()
    data[name.lower()] = instructions
    save_protocols(data)

def delete_protocol(name: str):
    data = load_protocols()
    key = name.lower()
    if key in data:
        del data[key]
        save_protocols(data)

def get_protocol(name: str) -> str:
    data = load_protocols()
    return data.get(name.lower(), None)
