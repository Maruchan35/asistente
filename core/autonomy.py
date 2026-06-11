"""
core/autonomy.py — Núcleo del sistema de autonomía de JARVIS.

Tres piezas:
  1. NIVEL DE AUTONOMÍA (perilla de confianza, persistida en config):
       1 = MANUAL    → pregunta antes de toda acción con efectos
       2 = ASISTIDO  → ejecuta SAFE/MEDIUM solo; pregunta HIGH y CRITICAL
       3 = AUTÓNOMO  → ejecuta hasta HIGH solo; CRITICAL siempre pregunta
     (CRITICAL NUNCA se auto-ejecuta, sin importar el nivel.)

  2. KILL SWITCH: "JARVIS, detente" congela TODA actividad autónoma al
     instante (daemon, self-healing, reparaciones). Se reactiva explícito.

  3. AUDITORÍA: toda acción autónoma queda en logs/autonomy.jsonl con
     timestamp, acción, motivo, resultado. Consultable por voz:
     "¿qué hiciste mientras no estaba?"
"""
from __future__ import annotations
import json
import threading
import time
from datetime import datetime
from pathlib import Path

_BASE       = Path(__file__).resolve().parent.parent
_CFG_PATH   = _BASE / "config" / "autonomy.json"
_AUDIT_PATH = _BASE / "logs" / "autonomy.jsonl"

_lock = threading.Lock()
_kill_switch = threading.Event()      # activado = TODO congelado

LEVEL_NAMES = {1: "MANUAL", 2: "ASISTIDO", 3: "AUTÓNOMO"}

# Qué riesgos puede auto-ejecutar cada nivel (sandbox: SAFE/MEDIUM/HIGH/CRITICAL)
_ALLOWED_BY_LEVEL = {
    1: set(),                          # nada automático
    2: {"SAFE", "MEDIUM"},
    3: {"SAFE", "MEDIUM", "HIGH"},
}


# ── Configuración persistida ──────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        return json.loads(_CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"level": 1}


def _save_cfg(cfg: dict) -> None:
    try:
        from core.safe_json import safe_write
        safe_write(_CFG_PATH, cfg)
    except Exception:
        try:
            _CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass


def get_level() -> int:
    with _lock:
        lvl = int(_load_cfg().get("level", 1))
        return lvl if lvl in (1, 2, 3) else 1


def set_level(level: int) -> int:
    level = max(1, min(3, int(level)))
    with _lock:
        cfg = _load_cfg()
        cfg["level"] = level
        cfg["changed_at"] = datetime.now().isoformat(timespec="seconds")
        _save_cfg(cfg)
    audit("set_level", f"Nivel de autonomía → {level} ({LEVEL_NAMES[level]})", "ok")
    return level


# ── Kill switch ───────────────────────────────────────────────────────────────

def kill() -> None:
    """Congelar toda actividad autónoma INMEDIATAMENTE."""
    _kill_switch.set()
    audit("kill_switch", "Actividad autónoma DETENIDA por el usuario", "ok")


def resume() -> None:
    _kill_switch.clear()
    audit("kill_switch", "Actividad autónoma reanudada", "ok")


def is_killed() -> bool:
    return _kill_switch.is_set()


# ── Decisión central ──────────────────────────────────────────────────────────

def is_allowed(risk: str, context: str = "") -> bool:
    """¿Puede ejecutarse automáticamente una acción de este riesgo AHORA?
    CRITICAL nunca pasa. Kill switch bloquea todo."""
    if _kill_switch.is_set():
        return False
    risk = (risk or "SAFE").upper()
    if risk == "CRITICAL":
        return False
    return risk in _ALLOWED_BY_LEVEL.get(get_level(), set())


def status() -> dict:
    lvl = get_level()
    return {
        "level":      lvl,
        "level_name": LEVEL_NAMES[lvl],
        "killed":     is_killed(),
        "allows":     sorted(_ALLOWED_BY_LEVEL[lvl]),
    }


# ── Auditoría ─────────────────────────────────────────────────────────────────

def audit(action: str, detail: str, result: str = "", **extra) -> None:
    """Registrar una acción autónoma. SIEMPRE llamar al actuar sin orden directa."""
    entry = {
        "ts":     datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "detail": detail[:300],
        "result": str(result)[:300],
        "level":  get_level(),
        **extra,
    }
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def audit_report(hours: int = 24, max_entries: int = 25) -> str:
    """Resumen legible de lo que JARVIS hizo solo en las últimas N horas."""
    if not _AUDIT_PATH.exists():
        return "Sin actividad autónoma registrada."
    cutoff = time.time() - hours * 3600
    entries = []
    try:
        with open(_AUDIT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    ts = datetime.fromisoformat(e.get("ts", "1970-01-01")).timestamp()
                    if ts >= cutoff:
                        entries.append(e)
                except Exception:
                    pass
    except Exception:
        return "No se pudo leer el registro de autonomía."

    if not entries:
        return f"Sin actividad autónoma en las últimas {hours} horas."

    entries = entries[-max_entries:]
    lines = [f"Actividad autónoma (últimas {hours}h — {len(entries)} acciones):"]
    for e in entries:
        t = e.get("ts", "")[11:16]
        res = f" → {e['result']}" if e.get("result") else ""
        lines.append(f"  [{t}] {e.get('action','?')}: {e.get('detail','')}{res}")
    return "\n".join(lines)
