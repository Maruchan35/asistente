"""
core/audio_ducking.py — Baja el volumen de otras apps mientras JARVIS habla.

Usa pycaw (ya en requirements) para tocar los volúmenes POR SESIÓN del mixer
de Windows: cuando JARVIS empieza a hablar, las demás apps (Spotify, Chrome,
juegos...) bajan al 30% de su volumen actual; al terminar, se restauran
exactamente a su nivel previo.

El proceso propio (python) NUNCA se baja — JARVIS debe oírse claro.

Uso desde main.py:
    from core.audio_ducking import duck, unduck
    duck()    # al empezar a hablar
    unduck()  # al terminar

Fail-safe: si pycaw no está o el mixer falla, no hace nada (sin excepciones).
"""
from __future__ import annotations
import os
import threading

_DUCK_FACTOR = 0.30          # volumen relativo durante el habla (30%)
_lock = threading.Lock()
_saved_volumes: dict[int, float] = {}   # pid → volumen original
_ducked = False

# Procesos que nunca se bajan (JARVIS mismo)
_SELF_PID = os.getpid()


def _get_sessions():
    """Sesiones de audio activas del mixer de Windows."""
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetAllSessions()


def duck() -> None:
    """Bajar el volumen de todas las apps (excepto la propia)."""
    global _ducked
    with _lock:
        if _ducked:
            return
        try:
            sessions = _get_sessions()
        except Exception:
            return
        saved = {}
        for s in sessions:
            try:
                if s.Process is None:
                    continue
                pid = s.Process.pid
                if pid == _SELF_PID:
                    continue
                vol_iface = s.SimpleAudioVolume
                current = vol_iface.GetMasterVolume()
                if current <= 0.01:
                    continue   # ya está silenciado — no tocar
                saved[pid] = current
                vol_iface.SetMasterVolume(max(0.05, current * _DUCK_FACTOR), None)
            except Exception:
                continue
        if saved:
            _saved_volumes.clear()
            _saved_volumes.update(saved)
            _ducked = True


def unduck() -> None:
    """Restaurar los volúmenes originales."""
    global _ducked
    with _lock:
        if not _ducked:
            return
        try:
            sessions = _get_sessions()
        except Exception:
            _saved_volumes.clear()
            _ducked = False
            return
        for s in sessions:
            try:
                if s.Process is None:
                    continue
                pid = s.Process.pid
                if pid in _saved_volumes:
                    s.SimpleAudioVolume.SetMasterVolume(_saved_volumes[pid], None)
            except Exception:
                continue
        _saved_volumes.clear()
        _ducked = False


def is_enabled() -> bool:
    """Leer config: audio_ducking on/off (default on)."""
    try:
        import json
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return bool(cfg.get("audio_ducking", True))
    except Exception:
        return True
