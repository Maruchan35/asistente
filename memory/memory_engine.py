"""
memory/memory_engine.py — JARVIS Persistent Memory Engine v2.0

Three memory layers:
  1. Long-term facts   → memory/long_term.json      (explicit saves + auto-extracted)
  2. Session journal   → memory/sessions/YYYY-MM-DD.jsonl  (every turn, per day)
  3. Recent turns      → memory/recent_turns.json   (circular buffer, last 20 turns)

Used for rich context injection at every Gemini session reconnect.
"""
from __future__ import annotations
import json
import os
import re
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE   = Path(__file__).resolve().parent.parent
_MEM    = _BASE / "memory"
_SESS   = _MEM / "sessions"
_LT     = _MEM / "long_term.json"
_RT     = _MEM / "recent_turns.json"

# ── Limits ─────────────────────────────────────────────────────────────────────
MAX_RECENT_TURNS    = 20    # turns kept in recent_turns.json
MAX_TURNS_INJECT    = 5     # turns shown in system prompt
MAX_SESSION_DAYS    = 7     # days of session summaries shown
MAX_SUMMARY_PER_DAY = 300   # chars per day summary
MAX_LT_CHARS        = 8000  # long-term memory char budget
MAX_VALUE_LEN       = 400   # single memory value max chars

_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _now_ts() -> int:
    return int(time.time())

def _today() -> str:
    return date.today().isoformat()   # "2026-06-07"

def _date_label(iso: str) -> str:
    """Turn '2026-06-07' into 'Hoy', 'Ayer', 'Lun 02-Jun', etc."""
    try:
        d = date.fromisoformat(iso)
        today = date.today()
        delta = (today - d).days
        if delta == 0:  return "Hoy"
        if delta == 1:  return "Ayer"
        days_es = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
        months_es = ["","Ene","Feb","Mar","Abr","May","Jun",
                     "Jul","Ago","Sep","Oct","Nov","Dic"]
        return f"{days_es[d.weekday()]} {d.day:02d}-{months_es[d.month]}"
    except Exception:
        return iso

def _load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _save_json(path: Path, data) -> None:
    try:
        from core.safe_json import safe_write
        safe_write(path, data)
    except ImportError:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except Exception as e:
            print(f"[Memory] save error {path}: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  LONG-TERM MEMORY  (enhanced from memory_manager.py)
# ══════════════════════════════════════════════════════════════════════════════

def _empty_lt() -> dict:
    return {"notes": {}, "habits": {}, "preferences": {}, "context": {}, "facts": {}}

def load_long_term() -> dict:
    with _lock:
        data = _load_json(_LT, _empty_lt())
        # Ensure all sections exist
        for k in ("notes","habits","preferences","context","facts"):
            data.setdefault(k, {})
        return data

def save_long_term(mem: dict) -> None:
    with _lock:
        _save_json(_LT, mem)

def remember(category: str, key: str, value: str, source: str = "manual") -> None:
    """Store a single fact in long-term memory with timestamp."""
    with _lock:
        mem = _load_json(_LT, _empty_lt())
        for k in ("notes","habits","preferences","context","facts"):
            mem.setdefault(k, {})
        cat = mem.setdefault(category, {})
        val_str = str(value)[:MAX_VALUE_LEN]
        cat[key] = {
            "value":   val_str,
            "ts":      _now_ts(),
            "source":  source,
        }
        # Smart trim: keep most recent entries when over budget
        _smart_trim(mem)
        _save_json(_LT, mem)

def forget(category: str, key: str) -> bool:
    with _lock:
        mem = _load_json(_LT, _empty_lt())
        if category in mem and key in mem[category]:
            del mem[category][key]
            _save_json(_LT, mem)
            return True
    return False

def _smart_trim(mem: dict) -> None:
    """Remove entries over budget, prioritizing oldest and 'context' category."""
    all_entries = []
    for cat, items in mem.items():
        if not isinstance(items, dict):
            continue
        for key, val in items.items():
            ts = val.get("ts", 0) if isinstance(val, dict) else 0
            text = val.get("value", str(val)) if isinstance(val, dict) else str(val)
            priority = 0 if cat == "context" else 1   # context lowest priority
            all_entries.append((ts, priority, cat, key, len(text)))

    total = sum(e[4] for e in all_entries)
    if total <= MAX_LT_CHARS:
        return

    # Sort: remove oldest context first, then oldest of any category
    all_entries.sort(key=lambda e: (e[1], e[0]))   # priority ASC, ts ASC
    while total > MAX_LT_CHARS and all_entries:
        _, _, cat, key, size = all_entries.pop(0)
        if cat in mem and key in mem[cat]:
            del mem[cat][key]
            total -= size

def _format_lt_for_prompt(mem: dict) -> str:
    lines = []
    for cat in ("preferences", "facts", "notes", "context"):
        items = mem.get(cat, {})
        if not items:
            continue
        lines.append(f"  [{cat.upper()}]")
        for key, val in items.items():
            v = val.get("value", str(val)) if isinstance(val, dict) else str(val)
            lines.append(f"    • {key}: {v}")
    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
#  AUTO FACT EXTRACTION  (regex-based, zero cost)
# ══════════════════════════════════════════════════════════════════════════════

# (pattern, category, key_template, value_group_index)
_FACT_PATTERNS: list[tuple] = [
    # Name
    (r"\b(?:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})", "preferences", "nombre_usuario", 1),
    # Location — stop at comma, period, "y", or end of clause
    (r"\b(?:vivo en|estoy en|mi ciudad es|mi colonia es)\s+([A-Za-záéíóúÁÉÍÓÚñÑ\s]{3,35}?)(?:\s+y\s|\.|,|$)", "preferences", "ubicacion", 1),
    # Pets
    (r"\bmi (?:perro|perra|gato|gata|mascota)\s+(?:se llama|es)\s+(\w+)", "facts", "mascota", 1),
    # Email
    (r"\bmi (?:correo|email)\s+(?:es|:)\s+([\w.+-]+@[\w.]+\.\w+)", "preferences", "email", 1),
    # Phone
    (r"\bmi (?:tel[eé]fono|cel(?:ular)?|n[uú]mero)\s+(?:es|:)\s+([\d\s\-+()]{7,15})", "preferences", "telefono", 1),
    # Preferences: "me gusta / prefiero / me encanta X"
    (r"\b(?:me gusta|me encanta|prefiero|me fascina)\s+(.{4,60}?)(?:\.|,|$)", "preferences", "gusto", 1),
    # Work
    (r"\b(?:trabajo en|mi trabajo es|mi empresa es)\s+(.{3,50}?)(?:\.|,|$)", "facts", "trabajo", 1),
    # Schedule
    (r"\btodos los (?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados|domingos)\s+(.{4,60}?)(?:\.|,|$)", "facts", "rutina_semanal", 1),
    # Important reminders explicitly said
    (r"\b(?:recuerda que|no olvides que|guarda que|anota que)\s+(.{5,120}?)(?:\.|$)", "notes", "nota_auto", 1),
    # Netflix / Spotify preferences
    (r"\b(?:mi pel[ií]cula favorita|mi serie favorita)\s+(?:es|:)\s+(.{3,60}?)(?:\.|,|$)", "preferences", "favorito_entretenimiento", 1),
    (r"\bmi (?:m[uú]sica|artista|banda) favorit[ao]\s+(?:es|:)\s+(.{3,40}?)(?:\.|,|$)", "preferences", "favorito_musica", 1),
]

def auto_extract_facts(user_text: str, jarvis_text: str) -> list[tuple[str,str,str]]:
    """
    Scan user + JARVIS text for auto-saveable facts.
    Returns list of (category, key, value) tuples.
    """
    combined = f"{user_text} {jarvis_text}".lower()
    original = f"{user_text} {jarvis_text}"   # keep case for values
    found = []
    seen_keys: set[str] = set()

    for pattern, cat, key_tpl, grp in _FACT_PATTERNS:
        for m in re.finditer(pattern, original, re.IGNORECASE):
            try:
                val = m.group(grp).strip().rstrip(".,")
                if len(val) < 3:
                    continue
                # Make key unique if duplicate (e.g. two "gusto" entries)
                key = key_tpl
                if key in seen_keys:
                    key = f"{key_tpl}_{len(seen_keys)}"
                seen_keys.add(key)
                found.append((cat, key, val))
            except Exception:
                pass

    return found

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION JOURNAL  (per-day JSONL file)
# ══════════════════════════════════════════════════════════════════════════════

def _session_path(day: str | None = None) -> Path:
    return _SESS / f"{day or _today()}.jsonl"

def _append_turn_to_session(entry: dict) -> None:
    """Append a single turn entry to today's JSONL session file."""
    path = _session_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Memory] session write error: {e}")

def _read_session(day: str) -> list[dict]:
    path = _session_path(day)
    turns = []
    if not path.exists():
        return turns
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        turns.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return turns

def _summarize_session(turns: list[dict]) -> str:
    """
    Build a compact summary of a session's turns.
    "Pediste X, JARVIS hizo Y. Usaste: open_app, spotify_control"
    """
    if not turns:
        return ""
    topics  = []
    tools_used: set[str] = set()
    for t in turns:
        user = t.get("user","")[:60]
        tools = t.get("tools", [])
        if user:
            topics.append(user)
        tools_used.update(tools)

    # Keep first 5 topics for brevity
    sample = "; ".join(topics[:5])
    if len(topics) > 5:
        sample += f" (+{len(topics)-5} más)"
    tools_str = ", ".join(sorted(tools_used)) if tools_used else "ninguna"
    summary = f"{sample} [herramientas: {tools_str}]"
    return summary[:MAX_SUMMARY_PER_DAY]

# ══════════════════════════════════════════════════════════════════════════════
#  RECENT TURNS  (circular buffer)
# ══════════════════════════════════════════════════════════════════════════════

def _load_recent_turns() -> list[dict]:
    return _load_json(_RT, [])

def _save_recent_turns(turns: list[dict]) -> None:
    _save_json(_RT, turns[-MAX_RECENT_TURNS:])

# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def record_turn(user_text: str, jarvis_text: str, tools_used: list[str] | None = None) -> None:
    """
    Called after every completed exchange.
    • Saves to today's session JSONL
    • Updates recent_turns circular buffer
    • Auto-extracts and saves facts
    """
    if not user_text.strip() and not jarvis_text.strip():
        return

    tools_used = tools_used or []
    entry = {
        "ts":     _now_ts(),
        "user":   user_text.strip()[:300],
        "jarvis": jarvis_text.strip()[:500],
        "tools":  tools_used,
    }

    # 1. Session journal
    _append_turn_to_session(entry)

    # 2. Recent turns buffer
    with _lock:
        rt = _load_recent_turns()
        rt.append(entry)
        _save_recent_turns(rt)

    # 3. Auto-extract facts
    facts = auto_extract_facts(user_text, jarvis_text)
    for cat, key, val in facts:
        remember(cat, key, val, source="auto")
        try:
            print(f"[Memory] Auto-saved: {cat}/{key} = {val[:50]}")
        except UnicodeEncodeError:
            pass


def get_context_block() -> str:
    """
    Build the full memory context block for injection into system_instruction.
    Called by _build_config() at every session (re)connect.

    Returns a structured string:
      [MEMORIA A LARGO PLAZO]   ← facts, preferences, notes
      [HISTORIAL DE SESIONES]   ← last 7 days summaries
      [CONVERSACIÓN RECIENTE]   ← last 5 turns of this session
    """
    sections: list[str] = []

    # ── 1. Long-term memory ────────────────────────────────────────────────────
    lt = load_long_term()
    lt_text = _format_lt_for_prompt(lt)
    if lt_text:
        sections.append(f"[MEMORIA A LARGO PLAZO]\n{lt_text}")

    # ── 2. Session history (last 7 days, excluding today) ─────────────────────
    history_lines: list[str] = []
    today_str = _today()
    _SESS.mkdir(parents=True, exist_ok=True)
    for delta in range(1, MAX_SESSION_DAYS + 1):
        day_str = (date.today() - timedelta(days=delta)).isoformat()
        turns   = _read_session(day_str)
        if not turns:
            continue
        summary = _summarize_session(turns)
        if summary:
            label = _date_label(day_str)
            history_lines.append(f"  {label}: {summary}")

    if history_lines:
        sections.append("[HISTORIAL DE SESIONES (últimos días)]\n" +
                        "\n".join(history_lines))

    # ── 3. Today's session so far ──────────────────────────────────────────────
    today_turns = _read_session(today_str)
    if today_turns:
        today_summary = _summarize_session(today_turns)
        if today_summary:
            sections.append(f"[SESIÓN DE HOY (resumen)]\n  {today_summary}")

    # ── 4. Recent turns (last N exchanges — conversational context) ────────────
    rt = _load_recent_turns()
    # Only use turns from the last 2 hours for conversational context
    cutoff = _now_ts() - 7200   # 2 hours
    fresh  = [t for t in rt if t.get("ts", 0) >= cutoff]
    recent = fresh[-MAX_TURNS_INJECT:] if fresh else rt[-MAX_TURNS_INJECT:]

    if recent:
        turn_lines: list[str] = []
        for t in recent:
            user_short   = t.get("user","")[:120]
            jarvis_short = t.get("jarvis","")[:200]
            if user_short:
                turn_lines.append(f"  Tú: {user_short}")
            if jarvis_short:
                turn_lines.append(f"  JARVIS: {jarvis_short}")
            turn_lines.append("")   # blank separator
        if turn_lines:
            sections.append("[CONVERSACIÓN RECIENTE]\n" + "\n".join(turn_lines).rstrip())

    if not sections:
        return ""

    return (
        "══════════════════════════════════════════════════\n"
        "MEMORIA PERSISTENTE DE JARVIS\n"
        "══════════════════════════════════════════════════\n"
        + "\n\n".join(sections) +
        "\n══════════════════════════════════════════════════\n"
    )


def clear_recent_turns() -> None:
    """Call this at session start so the 'recent turns' only reflect the new session."""
    _save_json(_RT, [])


def get_stats() -> dict:
    """Return memory statistics for debugging/UI display."""
    lt = load_long_term()
    lt_entries = sum(len(v) for v in lt.values() if isinstance(v, dict))
    rt = _load_recent_turns()
    _SESS.mkdir(parents=True, exist_ok=True)
    session_files = list(_SESS.glob("*.jsonl"))
    total_turns = sum(
        len(_read_session(f.stem)) for f in session_files
    )
    return {
        "long_term_entries":  lt_entries,
        "recent_turns":       len(rt),
        "session_days":       len(session_files),
        "total_turns_logged": total_turns,
    }
