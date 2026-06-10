"""
core/global_hotkey.py — Hotkey global del sistema para JARVIS.

Atajo Ctrl+Alt+J que despierta a JARVIS inmediatamente, sin esperar wake word.
Útil cuando hay ruido en el ambiente, audífonos, o el usuario quiere garantizar
que JARVIS escuche.

Usa la librería `keyboard` (cross-platform). Si no está disponible, no falla,
simplemente loguea y sigue. El proyecto ya la usa para el panic-hotkey.

Uso:
    from core.global_hotkey import register_attention_hotkey
    register_attention_hotkey(callback=on_attention_requested)
"""
from __future__ import annotations
import threading

try:
    from core.jarvis_logger import log_info, log_warn, log_error
except Exception:
    def log_info(*a, **k): pass
    def log_warn(*a, **k): pass
    def log_error(*a, **k): pass


_active_callbacks: list = []


def register_attention_hotkey(callback, combo: str = "ctrl+alt+j") -> bool:
    """
    Registra el hotkey global de atención. Devuelve True si se registró correctamente.
    El callback se invoca en un hilo separado.
    """
    try:
        import keyboard
    except ImportError:
        log_warn("Librería 'keyboard' no disponible — hotkey global desactivado")
        return False

    def _wrapped():
        # Disparar en hilo nuevo para no bloquear el hook del teclado
        threading.Thread(target=_safe_invoke, args=(callback,), daemon=True).start()

    try:
        keyboard.add_hotkey(combo, _wrapped)
        _active_callbacks.append((combo, _wrapped))
        log_info(f"Hotkey global registrado: {combo}", category="system")
        return True
    except Exception as e:
        log_error("No se pudo registrar hotkey global", exc=e)
        return False


def _safe_invoke(cb):
    try:
        cb()
    except Exception as e:
        log_error("Hotkey callback failed", exc=e)


def unregister_all():
    """Limpiar todos los hotkeys (al cerrar JARVIS)."""
    try:
        import keyboard
        for combo, _ in _active_callbacks:
            try:
                keyboard.remove_hotkey(combo)
            except Exception:
                pass
        _active_callbacks.clear()
    except ImportError:
        pass
