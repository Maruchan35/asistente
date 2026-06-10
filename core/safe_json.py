"""safe_json.py — Atomic JSON read/write utilities.
All write operations use a temp file + rename to prevent corruption on crash."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any


def safe_read(path: str | Path, default: Any = None) -> Any:
    """Read a JSON file. Returns default if file doesn't exist or is corrupt."""
    p = Path(path)
    if not p.exists():
        return default
    try:
        text = p.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[safe_json] Corrupt JSON at {p}: {e}")
        # Try to restore from .bak
        bak = p.with_suffix(".bak")
        if bak.exists():
            try:
                text = bak.read_text(encoding="utf-8")
                data = json.loads(text)
                print(f"[safe_json] Restored from {bak}")
                return data
            except Exception:
                pass
        return default
    except Exception as e:
        print(f"[safe_json] Read error {p}: {e}")
        return default


def safe_write(path: str | Path, data: Any,
               indent: int = 2, ensure_ascii: bool = False) -> bool:
    """Write data to a JSON file atomically using temp file + rename.
    Creates a .bak of the previous version before overwriting.
    Returns True on success."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        content = json.dumps(data, indent=indent,
                             ensure_ascii=ensure_ascii, default=str)
    except Exception as e:
        print(f"[safe_json] Serialization error: {e}")
        return False

    # Write to temp file in same directory (for same-filesystem rename)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            os.unlink(tmp_path)
            print(f"[safe_json] Write error: {e}")
            return False

        # Backup current file
        if p.exists():
            try:
                bak = p.with_suffix(".bak")
                os.replace(str(p), str(bak))
            except Exception:
                pass  # Non-critical

        # Atomic rename
        os.replace(tmp_path, str(p))
        return True

    except Exception as e:
        print(f"[safe_json] Atomic write failed for {p}: {e}")
        return False


def safe_update(path: str | Path, key: str, value: Any,
                default_root: Any = None) -> bool:
    """Read a JSON dict, update one key, write back atomically."""
    data = safe_read(path, default=default_root if default_root is not None else {})
    if not isinstance(data, dict):
        data = {}
    data[key] = value
    return safe_write(path, data)


def safe_append(path: str | Path, item: Any,
                max_items: int | None = None) -> bool:
    """Read a JSON list, append an item, optionally cap length, write back."""
    data = safe_read(path, default=[])
    if not isinstance(data, list):
        data = []
    data.append(item)
    if max_items and len(data) > max_items:
        data = data[-max_items:]
    return safe_write(path, data)
