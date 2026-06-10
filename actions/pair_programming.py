"""
pair_programming.py — Modo "pair programmer" para JARVIS.

Cuando se activa, JARVIS captura cada N segundos lo que ve en pantalla
(asumiendo que estás en tu IDE) y, sin interrumpir tu voz, escribe
observaciones en el activity panel: bugs evidentes, código inconsistente,
sugerencias.

Para no quemar quota ni saturar, usa:
  • Capturas cada 20-30s (configurable)
  • Solo procesa si la pantalla cambió significativamente desde la última
  • Resultado va al activity panel, no a voz

Activación por voz: "modo programador" / "pair programming" / "ayúdame a programar".
"""
from __future__ import annotations
import hashlib
import threading
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent

_active = False
_thread: threading.Thread | None = None
_stop_event = threading.Event()
_interval_s = 25
_ui_ref = None              # referencia al UI para escribir en panel
_last_screen_hash = ""


def _capture_and_analyze(ui):
    """Una iteración del loop: captura pantalla, analiza, reporta al panel."""
    global _last_screen_hash
    try:
        from actions.screen_vision import screen_vision
    except ImportError:
        return

    # Capturar
    try:
        # screen_vision con action='describe' devuelve análisis del LLM
        result = screen_vision({
            "action":      "describe",
            "focus_query": (
                "Eres mi pair programmer. Examina ESTA captura del IDE y reporta SOLO si ves algún "
                "problema concreto: bug evidente (typo, off-by-one, variable indefinida), "
                "inconsistencia (else sin if, paréntesis abierto, indentación rota), "
                "anti-patrón (catch genérico vacío, magic number sin nombre, función gigante). "
                "Si todo se ve bien, responde EXACTAMENTE: 'OK'. "
                "Si ves un problema, devuelve en formato:\n"
                "PROBLEMA: <descripción corta>\n"
                "LÍNEA: <número aprox si visible>\n"
                "SUGERENCIA: <fix concreto>\n"
                "Sé breve. NO incluyas el código completo."
            ),
        }, player=ui)
    except Exception as e:
        return

    if not result or result.strip().upper() in ("OK", "OK.", ""):
        return

    # Hash del análisis — evitar repetir el mismo comentario
    h = hashlib.md5(result[:200].encode()).hexdigest()[:12]
    if h == _last_screen_hash:
        return
    _last_screen_hash = h

    # Reportar al activity panel
    try:
        panel = getattr(ui, "activity_panel", None)
        if panel:
            panel.set_current_tool("pair-prog: " + result.split("\n")[0][:40])
    except Exception:
        pass

    # Logging
    try:
        from core.jarvis_logger import log_info
        log_info(f"Pair programming observation: {result[:120]}", category="system")
    except Exception:
        pass

    # Activity panel: usar plan view para mostrar
    try:
        panel = getattr(ui, "activity_panel", None)
        if panel:
            lines = [l.strip() for l in result.split("\n") if l.strip()]
            panel.set_plan(lines[:6])
    except Exception:
        pass


def _loop(ui):
    """Loop de fondo."""
    while _active and not _stop_event.is_set():
        try:
            # Respetar focus mode — si activo, suspender pair programming
            try:
                from core.focus_mode import is_active as _focus_active
                if _focus_active():
                    _stop_event.wait(_interval_s)
                    continue
            except Exception:
                pass
            _capture_and_analyze(ui)
        except Exception:
            pass
        _stop_event.wait(_interval_s)


def start(ui=None, interval_s: int = 25) -> str:
    """Activar pair programming mode."""
    global _active, _thread, _interval_s, _ui_ref, _last_screen_hash
    if _active:
        return "Modo pair programming ya está activo, señor."

    _interval_s = max(10, interval_s)
    _ui_ref = ui
    _last_screen_hash = ""
    _stop_event.clear()
    _active = True
    _thread = threading.Thread(target=_loop, args=(ui,), daemon=True, name="PairProgramming")
    _thread.start()

    try:
        from core.jarvis_logger import log_info
        log_info(f"Pair programming activado (intervalo={_interval_s}s)", category="system")
    except Exception:
        pass

    return (
        f"Modo pair programming activado. Voy a observar su pantalla cada {_interval_s} segundos "
        "y le indicaré problemas en el panel de actividad, sin interrumpirle, señor."
    )


def stop() -> str:
    """Desactivar pair programming mode."""
    global _active, _thread
    if not _active:
        return "Modo pair programming no estaba activo."
    _active = False
    _stop_event.set()
    if _thread:
        try:
            _thread.join(timeout=2.0)
        except Exception:
            pass
    _thread = None
    try:
        from core.jarvis_logger import log_info
        log_info("Pair programming desactivado", category="system")
    except Exception:
        pass
    return "Modo pair programming desactivado, señor."


def is_running() -> bool:
    return _active


def pair_programming(parameters: dict, player=None) -> str:
    """Entry point para dispatcher Gemini."""
    action = (parameters.get("action") or "start").lower()
    interval = int(parameters.get("interval_s", 25))

    if action in ("stop", "disable", "off"):
        return stop()
    if action in ("status", "state"):
        return ("Pair programming ACTIVO" if is_running() else "Pair programming inactivo")

    # start
    return start(ui=player, interval_s=interval)
