"""
core/quota_manager.py — Detecta agotamiento de cuota de Gemini y cae a fallback.

Cuando Gemini Live agota la cuota (HTTP 429 / "RESOURCE_EXHAUSTED"), JARVIS
hoy se cae con error. Este módulo:
  • Detecta el patrón de error de cuota en cualquier excepción
  • Marca el proveedor como "agotado" hasta una hora estimada de recuperación
  • Recomienda al motor cuál proveedor usar (gemini → deepseek → openrouter → ollama)
  • Notifica al usuario con voz/holograma cuando se cambia

Esto NO reemplaza al motor de voz Gemini Live (que es bidireccional). Sirve para:
  - Llamadas a herramientas que usan Gemini bajo el capó (analysis, summaries)
  - Detectar el evento y mostrar mensaje claro en lugar de crashear

Uso:
    from core.quota_manager import is_quota_error, get_current_provider, mark_exhausted
    try:
        ...llamada a Gemini...
    except Exception as e:
        if is_quota_error(e):
            mark_exhausted("gemini")
            provider = get_current_provider()    # "deepseek" / "openrouter" / "ollama"
            # usar el fallback ↑
"""
from __future__ import annotations
import re
import threading
import time
from pathlib import Path

try:
    from core.jarvis_logger import log_quota, log_warn
except Exception:
    def log_quota(*a, **k): pass
    def log_warn(*a, **k): pass

# Orden de preferencia de proveedores
_PROVIDER_ORDER = ["gemini", "deepseek", "openrouter", "ollama"]

# Tiempo de "cooldown" por defecto cuando se agota una cuota (1h)
_DEFAULT_COOLDOWN_S = 3600

# Estado en memoria: provider -> timestamp en el que vuelve a estar disponible
_exhausted_until: dict[str, float] = {}
_lock = threading.Lock()


# ── Detección de errores de cuota ─────────────────────────────────────────────

_QUOTA_PATTERNS = [
    r"RESOURCE_EXHAUSTED",
    r"quota.*exceeded",
    r"rate.?limit",
    r"429",
    r"too many requests",
    r"daily limit",
    r"out of (?:credits|quota|tokens)",
    r"insufficient.*credit",
    r"billing",
    r"payment required",
]
_QUOTA_RE = re.compile("|".join(_QUOTA_PATTERNS), re.IGNORECASE)


def is_quota_error(exc: BaseException | str) -> bool:
    """Determina si una excepción/mensaje corresponde a una cuota agotada."""
    msg = str(exc) if not isinstance(exc, str) else exc
    return bool(_QUOTA_RE.search(msg))


# ── Estado de proveedores ─────────────────────────────────────────────────────

def mark_exhausted(provider: str, cooldown_s: int = _DEFAULT_COOLDOWN_S) -> None:
    """Marca un proveedor como agotado por `cooldown_s` segundos."""
    with _lock:
        _exhausted_until[provider.lower()] = time.time() + cooldown_s
    log_quota(provider, "exhausted", cooldown_s=cooldown_s)


def mark_recovered(provider: str) -> None:
    """Marca explícitamente un proveedor como disponible de nuevo."""
    with _lock:
        _exhausted_until.pop(provider.lower(), None)
    log_quota(provider, "recovered")


def is_exhausted(provider: str) -> bool:
    """¿Está el proveedor en periodo de cooldown?"""
    with _lock:
        until = _exhausted_until.get(provider.lower(), 0)
        if until == 0:
            return False
        if time.time() >= until:
            del _exhausted_until[provider.lower()]
            log_quota(provider, "cooldown_expired")
            return False
        return True


def get_current_provider(preferred: str = "gemini") -> str:
    """
    Devuelve el primer proveedor disponible en orden de preferencia.
    Si `preferred` está disponible, lo devuelve. Si no, cae al siguiente.
    """
    # Reordenar: preferred primero
    order = [preferred] + [p for p in _PROVIDER_ORDER if p != preferred]
    for p in order:
        if not is_exhausted(p):
            return p
    # Todos agotados — devolver preferred igual (al menos intentará)
    log_warn(f"Todos los proveedores agotados, usando {preferred} de todas formas",
             category="quota")
    return preferred


def get_status() -> dict:
    """Snapshot del estado para diagnóstico/UI."""
    now = time.time()
    out = {}
    with _lock:
        for p in _PROVIDER_ORDER:
            until = _exhausted_until.get(p, 0)
            if until > now:
                out[p] = {
                    "status": "exhausted",
                    "recovers_in_s": int(until - now),
                }
            else:
                out[p] = {"status": "available"}
    return out


# ── Wrapper conveniencia ──────────────────────────────────────────────────────

def call_with_fallback(call_chain: list[tuple[str, callable]], *args, **kwargs):
    """
    Recibe lista de (provider_name, function). Intenta cada una hasta éxito.
    Si una falla por cuota, marca el proveedor y prueba la siguiente.
    Si falla por otra cosa, propaga la excepción.

    Ejemplo:
        result = call_with_fallback([
            ("gemini",     lambda: gemini_chat(prompt)),
            ("deepseek",   lambda: deepseek_chat(prompt)),
            ("openrouter", lambda: openrouter_chat(prompt)),
        ])
    """
    last_exc = None
    for name, fn in call_chain:
        if is_exhausted(name):
            continue
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if is_quota_error(e):
                mark_exhausted(name)
                last_exc = e
                continue
            raise   # error no relacionado con cuota → propagar
    # Todos fallaron por cuota
    raise RuntimeError(f"Todos los proveedores agotados. Último error: {last_exc}")
