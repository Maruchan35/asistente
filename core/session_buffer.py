"""
core/session_buffer.py — Buffer volátil de la conversación actual.

Cuando Gemini Live se desconecta (1011, timeout, red, etc.), el estado
de la conversación actual se pierde — JARVIS reconecta "ciego" al contexto
de los últimos minutos. Este módulo guarda en RAM los últimos N turnos
para inyectarlos en el system_instruction al reconectar.

Diferente de memory_engine.recent_turns (que es persistente, ventana 2h,
incluye sesiones anteriores) — esto es solo el contexto activo del momento.
"""
from __future__ import annotations
import threading
import time
from collections import deque

_MAX_TURNS = 6                  # últimos 6 turnos (usuario+JARVIS)
_TTL_S    = 600                 # 10 min — si pasó más, ya no es "contexto activo"

_lock = threading.Lock()
_buffer: deque = deque(maxlen=_MAX_TURNS)


def push(user_text: str, jarvis_text: str) -> None:
    """Agrega un turno al buffer volátil."""
    with _lock:
        _buffer.append({
            "ts":     time.time(),
            "user":   (user_text or "")[:300],
            "jarvis": (jarvis_text or "")[:500],
        })


def snapshot() -> list[dict]:
    """Devuelve copia de los turnos vigentes (sin los expirados)."""
    now = time.time()
    with _lock:
        return [t for t in _buffer if (now - t["ts"]) <= _TTL_S]


def clear() -> None:
    """Limpiar buffer (al inicio de sesión nueva intencional)."""
    with _lock:
        _buffer.clear()


def format_for_reinjection() -> str:
    """Formato listo para inyectar tras una desconexión."""
    turns = snapshot()
    if not turns:
        return ""
    lines = ["[CONTEXTO INMEDIATO PREVIO A LA RECONEXIÓN]"]
    for t in turns:
        if t["user"]:
            lines.append(f"  Tú: {t['user']}")
        if t["jarvis"]:
            lines.append(f"  JARVIS: {t['jarvis']}")
    lines.append(
        "[continúa la conversación desde aquí — el usuario NO sabe que hubo una reconexión]"
    )
    return "\n".join(lines)


def is_recent_reconnect_context() -> bool:
    """¿Hay turnos vigentes? — usado por _build_config para decidir si inyectar."""
    return len(snapshot()) > 0
