"""
core/autonomy_daemon.py — El trabajador de fondo de JARVIS.

Loop cada N minutos que, respetando nivel de autonomía + kill switch + focus:
  1. Detecta si el usuario está IDLE (sin teclado/mouse > 15 min, vía Win32)
  2. Si está idle y nivel ≥ 2, ejecuta TAREAS DE MANTENIMIENTO:
       • Reindexar documentos (doc_search) si el índice tiene > 12h
       • Verificar actualizaciones del repo (solo check, no aplica)
       • Escanear fallas repetidas (self_heal scan; en nivel 3 intenta fix)
       • Limpiar tareas viejas de la cola
  3. Revisa OBJETIVOS PERSISTENTES (actions/goals.py) y reporta pendientes
  4. TODO queda en la auditoría (logs/autonomy.jsonl)

Al volver el usuario (fin del idle), si hubo trabajo, JARVIS lo menciona
una sola vez mediante el callback `on_summary`.
"""
from __future__ import annotations
import threading
import time
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent

_IDLE_THRESHOLD_S   = 15 * 60     # 15 min sin input = usuario ausente
_CHECK_INTERVAL_S   = 10 * 60     # revisar cada 10 min
_REINDEX_AGE_S      = 12 * 3600   # reindexar documentos si índice > 12h

_thread: threading.Thread | None = None
_stop = threading.Event()
_work_log: list[str] = []         # trabajo hecho durante el idle actual
_was_idle = False


def _get_idle_seconds() -> float:
    """Segundos desde el último input del usuario (Win32 GetLastInputInfo)."""
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
    except Exception:
        pass
    return 0.0


def _maintenance_pass() -> list[str]:
    """Una pasada de mantenimiento. Devuelve lista de cosas hechas."""
    from core.autonomy import is_allowed, audit
    done: list[str] = []

    # ── Reindexar documentos si el índice está viejo ─────────────────────────
    try:
        if is_allowed("SAFE"):
            import json as _json
            idx_path = _BASE / "config" / "doc_index.json"
            built_at = 0
            if idx_path.exists():
                try:
                    built_at = _json.loads(idx_path.read_text(encoding="utf-8")).get("built_at", 0)
                except Exception:
                    pass
            if (time.time() - built_at) > _REINDEX_AGE_S:
                from actions.doc_search import _refresh_index
                idx = _refresh_index(force=False)
                n = len(idx.get("files", {}))
                audit("idle_maintenance", f"Índice de documentos refrescado ({n} docs)", "ok")
                done.append(f"reindexé sus documentos ({n})")
    except Exception:
        pass

    # ── Check de actualizaciones (solo check — nunca aplica solo) ────────────
    try:
        if is_allowed("SAFE"):
            from actions.self_update import _check_updates
            has, detail = _check_updates()
            if has:
                audit("idle_maintenance", "Actualización disponible detectada",
                      detail[:120])
                done.append("detecté una actualización disponible del sistema")
    except Exception:
        pass

    # ── Self-healing scan (fix automático solo en nivel 3) ───────────────────
    try:
        from core.autonomy import get_level
        from actions.self_heal import _scan, _diagnose, _apply_fix
        patterns = _scan()
        if patterns:
            sig, n, example = patterns[0]
            audit("idle_maintenance", f"Falla repetida detectada ({n}×): {sig[:80]}", "")
            if get_level() >= 3 and is_allowed("HIGH"):
                diag = _diagnose(sig, example)
                if diag.get("ok"):
                    result = _apply_fix(diag)
                    done.append(f"reparé una falla en {diag['file']}")
                    audit("idle_self_heal", diag.get("diagnosis", "")[:120], result[:120])
                else:
                    done.append(f"detecté una falla repetida ({sig[:40]}) que requiere su atención")
            else:
                done.append(f"detecté {len(patterns)} falla(s) repetida(s) — pendientes de su autorización")
    except Exception:
        pass

    # ── Limpiar tareas viejas ─────────────────────────────────────────────────
    try:
        from core.task_queue import cleanup_old
        removed = cleanup_old(max_age_s=6 * 3600)
        if removed:
            done.append(f"limpié {removed} tareas terminadas")
    except Exception:
        pass

    # ── Objetivos persistentes pendientes ────────────────────────────────────
    try:
        import json as _json
        goals_path = _BASE / "config" / "goals.json"
        if goals_path.exists():
            goals = _json.loads(goals_path.read_text(encoding="utf-8"))
            items = goals if isinstance(goals, list) else goals.get("goals", [])
            active = [g for g in items
                      if isinstance(g, dict) and g.get("status", "active") == "active"]
            if active:
                from core.autonomy import audit as _audit
                _audit("goals_review", f"{len(active)} objetivo(s) activos revisados", "ok")
    except Exception:
        pass

    return done


def _loop(on_summary=None):
    global _was_idle
    while not _stop.is_set():
        try:
            from core.autonomy import is_killed, get_level
            from core.focus_mode import is_active as focus_active

            if is_killed() or get_level() < 2 or focus_active():
                _stop.wait(_CHECK_INTERVAL_S)
                continue

            idle_s = _get_idle_seconds()
            if idle_s >= _IDLE_THRESHOLD_S:
                # Usuario ausente → trabajar
                if not _was_idle:
                    from core.autonomy import audit
                    audit("idle_start", f"Usuario ausente ({int(idle_s/60)} min) — iniciando mantenimiento", "")
                _was_idle = True
                done = _maintenance_pass()
                _work_log.extend(done)
            else:
                # Usuario presente
                if _was_idle and _work_log and on_summary:
                    # Acaba de volver — resumir UNA vez
                    summary = "; ".join(dict.fromkeys(_work_log))[:400]
                    try:
                        on_summary(summary)
                    except Exception:
                        pass
                    _work_log.clear()
                _was_idle = False
        except Exception:
            pass
        _stop.wait(_CHECK_INTERVAL_S)


def start(on_summary=None) -> None:
    """Arrancar el daemon. `on_summary(texto)` se llama cuando el usuario
    regresa y hubo trabajo hecho durante su ausencia."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(on_summary,),
                               daemon=True, name="AutonomyDaemon")
    _thread.start()


def stop() -> None:
    _stop.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
