"""
core/jarvis_logger.py — Logger estructurado JSON Lines para JARVIS.

Separa logs por categoría (errores, herramientas, audio, sistema) en archivos
distintos JSONL. Cada línea es un objeto JSON parseable, facilitando análisis
y debugging. Mantiene un archivo `jarvis.log` legible humano para compatibilidad.

Uso:
    from core.jarvis_logger import log_info, log_error, log_tool, log_audio
    log_info("Sistema iniciado", category="system")
    log_tool("document_creator", args={"title": "X"}, result_preview="...")
    log_error("Conexión perdida", exc=e)
"""
from __future__ import annotations
import json
import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────────────
_BASE  = Path(__file__).resolve().parent.parent
_LOGS  = _BASE / "logs"
_LOGS.mkdir(exist_ok=True)

_FILES = {
    "system":    _LOGS / "system.jsonl",
    "tool":      _LOGS / "tools.jsonl",
    "audio":     _LOGS / "audio.jsonl",
    "error":     _LOGS / "errors.jsonl",
    "quota":     _LOGS / "quota.jsonl",
    "session":   _LOGS / "sessions.jsonl",
}
_HUMAN = _BASE / "jarvis.log"

_lock = threading.Lock()

# Rotación simple: si un archivo supera N bytes, se rota a .1
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB por archivo


def _rotate(path: Path) -> None:
    """Si el log es muy grande, mover a .1 (sobrescribe el anterior)."""
    try:
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            backup = path.with_suffix(path.suffix + ".1")
            if backup.exists():
                backup.unlink()
            path.rename(backup)
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_jsonl(category: str, entry: dict) -> None:
    """Append entry a JSONL del category. Atomico via lock."""
    path = _FILES.get(category, _FILES["system"])
    with _lock:
        try:
            _rotate(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass


def _write_human(line: str) -> None:
    """Append línea legible al log humano (jarvis.log) — compatibilidad."""
    with _lock:
        try:
            _rotate(_HUMAN)
            with open(_HUMAN, "a", encoding="utf-8") as f:
                f.write(line.rstrip("\n") + "\n")
        except Exception:
            pass


# ── API pública ───────────────────────────────────────────────────────────────

def log_info(message: str, category: str = "system", **extra) -> None:
    entry = {"ts": _now_iso(), "level": "INFO", "msg": message, **extra}
    _write_jsonl(category, entry)
    _write_human(f"[{entry['ts']}] [INFO] {message}")


def log_warn(message: str, category: str = "system", **extra) -> None:
    entry = {"ts": _now_iso(), "level": "WARN", "msg": message, **extra}
    _write_jsonl(category, entry)
    _write_human(f"[{entry['ts']}] [WARN] {message}")


def log_error(message: str, exc: BaseException | None = None,
              category: str = "error", **extra) -> None:
    entry = {
        "ts":    _now_iso(),
        "level": "ERROR",
        "msg":   message,
        **extra,
    }
    if exc is not None:
        entry["exc_type"] = type(exc).__name__
        entry["exc_msg"]  = str(exc)
        entry["trace"]    = traceback.format_exc()
    _write_jsonl(category, entry)
    _write_jsonl("error", entry)   # también en errors.jsonl global
    _write_human(f"[{entry['ts']}] [ERROR] {message}"
                 + (f" — {type(exc).__name__}: {exc}" if exc else ""))


def log_tool(tool_name: str, args: dict | None = None,
             result_preview: str | None = None,
             duration_ms: int | None = None,
             success: bool = True) -> None:
    """Log uso de herramienta. Trunca args y resultado para no inflar."""
    entry = {
        "ts":       _now_iso(),
        "level":    "TOOL",
        "tool":     tool_name,
        "args":     _truncate_args(args or {}),
        "success":  success,
    }
    if result_preview is not None:
        entry["result"] = result_preview[:300]
    if duration_ms is not None:
        entry["dur_ms"] = duration_ms
    _write_jsonl("tool", entry)
    status = "✓" if success else "✗"
    _write_human(f"[{entry['ts']}] [TOOL] {status} {tool_name}"
                 + (f"  ({duration_ms}ms)" if duration_ms is not None else ""))


def log_audio(event: str, **extra) -> None:
    """Log evento de audio: mic_start, mic_stop, vad_open, vad_close, rms, etc."""
    entry = {"ts": _now_iso(), "level": "AUDIO", "event": event, **extra}
    _write_jsonl("audio", entry)


def log_quota(provider: str, status: str, **extra) -> None:
    """Log evento de quota: hit_limit, fallback_to, recovered."""
    entry = {
        "ts": _now_iso(), "level": "QUOTA",
        "provider": provider, "status": status, **extra,
    }
    _write_jsonl("quota", entry)
    _write_human(f"[{entry['ts']}] [QUOTA] {provider}: {status}")


def log_session(event: str, **extra) -> None:
    """Log evento de sesión Gemini: connect, disconnect, reconnect."""
    entry = {"ts": _now_iso(), "level": "SESSION", "event": event, **extra}
    _write_jsonl("session", entry)
    _write_human(f"[{entry['ts']}] [SESSION] {event}")


def _truncate_args(args: dict, max_val_len: int = 200) -> dict:
    """Trunca strings largos en los argumentos de las herramientas."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > max_val_len:
            out[k] = v[:max_val_len] + f"...(+{len(v)-max_val_len})"
        elif isinstance(v, (list, dict)) and len(str(v)) > max_val_len:
            out[k] = str(v)[:max_val_len] + "...(truncated)"
        else:
            out[k] = v
    return out


# ── Lectura para debugging / panel ────────────────────────────────────────────

def tail(category: str = "system", n: int = 50) -> list[dict]:
    """Devolver las últimas N entradas de un log JSONL."""
    path = _FILES.get(category, _FILES["system"])
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out
    except Exception:
        return []


def get_stats() -> dict:
    """Estadísticas de tamaño de cada log."""
    return {
        cat: {"path": str(p), "size_kb": p.stat().st_size // 1024 if p.exists() else 0}
        for cat, p in _FILES.items()
    }
