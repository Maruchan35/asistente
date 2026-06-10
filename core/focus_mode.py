"""
core/focus_mode.py — Modo "no molestar" / concentración.

Cuando se activa:
  • vision_guardian suspende reportes de eventos visuales (Discord/WhatsApp popups)
  • morning_brief no se dispara
  • Proactive engine se silencia
  • Solo cosas marcadas como CRÍTICAS llegan a interrumpir (correos con "urgente",
    llamadas, alarmas activas)

Uso desde voz: "modo concentración 1 hora" / "modo focus" / "no me molestes"
Desde código:
    from core.focus_mode import enable, disable, is_active, status
    enable(duration_minutes=60)
"""
from __future__ import annotations
import threading
import time

_lock = threading.Lock()
_until: float = 0.0          # epoch hasta cuando dura el focus mode (0 = inactivo)
_reason: str = ""


def enable(duration_minutes: int = 60, reason: str = "") -> dict:
    """Activar modo focus. Devuelve estado actual."""
    global _until, _reason
    with _lock:
        _until = time.time() + max(1, duration_minutes) * 60
        _reason = reason or "concentración"
    try:
        from core.jarvis_logger import log_info
        log_info(f"Focus mode ON ({duration_minutes}min): {reason}", category="system")
    except Exception:
        pass
    return status()


def disable() -> dict:
    """Desactivar manualmente."""
    global _until, _reason
    with _lock:
        _until = 0.0
        _reason = ""
    try:
        from core.jarvis_logger import log_info
        log_info("Focus mode OFF", category="system")
    except Exception:
        pass
    return status()


def is_active() -> bool:
    """True si el modo focus está vigente."""
    with _lock:
        if _until == 0.0:
            return False
        if time.time() >= _until:
            return False
        return True


def status() -> dict:
    """Snapshot del estado."""
    with _lock:
        now = time.time()
        if _until == 0.0 or now >= _until:
            return {"active": False, "remaining_s": 0, "reason": ""}
        return {
            "active": True,
            "remaining_s": int(_until - now),
            "remaining_min": int((_until - now) / 60),
            "reason": _reason,
        }


# Helper para módulos como vision_guardian / proactive_engine
def should_suppress(severity: str = "normal") -> bool:
    """
    Decide si una notificación debe suprimirse.
    severity: "low" | "normal" | "high" | "critical"
    Solo "critical" pasa siempre. Otros se suprimen si focus está activo.
    """
    if severity == "critical":
        return False
    return is_active()
