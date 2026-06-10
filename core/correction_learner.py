"""
core/correction_learner.py — Detecta cuando el usuario corrige a JARVIS
y guarda la corrección en memoria long-term como `feedback`.

Patrones que detectamos en el texto del usuario:
  • "no, así no" / "no es así" / "está mal"
  • "siempre [hazlo de esta forma]" / "nunca [hagas X]"
  • "la próxima vez [Y]" / "para siempre [Z]"
  • "te dije que [X]"

Cuando detectamos uno, guardamos:
  category=feedback, key=correction_<n>, value=<la corrección>

Estas correcciones se inyectan al system_instruction en futuras sesiones,
y JARVIS las consulta antes de actuar.
"""
from __future__ import annotations
import re
import time

# Patrones de corrección. Cada uno extrae el "qué hacer" o "qué NO hacer".
_PATTERNS = [
    (r"no[,\s]+as[ií]\s+no[,.\s]+(.{8,200})", "no_hacer"),
    (r"no[,\s]+est[áa]\s+mal[,.\s]+(.{8,200})", "correccion"),
    (r"siempre\s+(.{8,200}?)[\.,]", "regla_siempre"),
    (r"nunca\s+(.{8,200}?)[\.,]", "regla_nunca"),
    (r"la pr[oó]xima vez\s+(.{8,200}?)[\.,]", "proxima_vez"),
    (r"para siempre\s+(.{8,200}?)[\.,]", "permanente"),
    (r"te dije que\s+(.{8,200}?)[\.,]", "ya_lo_dije"),
    (r"recuerda que (?:nunca|jam[áa]s)\s+(.{8,200}?)[\.,]", "regla_nunca"),
    (r"corr[íi]gete[:,]?\s+(.{8,200})", "correccion_directa"),
    (r"as[íi] no es[,.\s]+(.{8,200})", "correccion"),
]


def detect_correction(user_text: str) -> tuple[str, str] | None:
    """
    Si el texto del usuario contiene una corrección, devuelve (tipo, contenido).
    Si no, None.
    """
    if not user_text or len(user_text) < 10:
        return None

    text = user_text.lower().strip()

    for pat, ctype in _PATTERNS:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            content = m.group(1).strip().rstrip(".,;:")
            if 5 < len(content) < 250:
                return (ctype, content)
    return None


def maybe_save_correction(user_text: str, jarvis_text_previous: str = "") -> bool:
    """
    Analizar el turno del usuario. Si corrige a JARVIS, guardar en memory.
    Devuelve True si guardó algo.
    """
    found = detect_correction(user_text)
    if not found:
        return False

    ctype, content = found
    try:
        from memory.memory_engine import remember
        ts = int(time.time())
        key = f"{ctype}_{ts}"
        # Incluir contexto de la respuesta anterior de JARVIS para dar pista
        value = content
        if jarvis_text_previous:
            value += f"  [contexto previo: {jarvis_text_previous[:80]}]"
        remember("feedback", key, value, source="correction_learner")
        try:
            from core.jarvis_logger import log_info
            log_info(f"Corrección aprendida: {ctype} → {content[:60]}",
                     category="system")
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            from core.jarvis_logger import log_error
            log_error("Fallo guardando corrección", exc=e)
        except Exception:
            pass
        return False


def format_corrections_for_prompt(limit: int = 8) -> str:
    """
    Listar las últimas N correcciones para incluir en el system_instruction.
    """
    try:
        from memory.memory_engine import load_long_term
        mem = load_long_term()
        fb = mem.get("feedback", {})
        if not fb:
            return ""
        # Ordenar por ts (más reciente primero)
        items = []
        for key, val in fb.items():
            ts = val.get("ts", 0) if isinstance(val, dict) else 0
            v = val.get("value", str(val)) if isinstance(val, dict) else str(val)
            items.append((ts, key, v))
        items.sort(reverse=True)
        items = items[:limit]
        if not items:
            return ""

        lines = ["[CORRECCIONES Y REGLAS APRENDIDAS DEL USUARIO]"]
        for _, key, v in items:
            lines.append(f"  • {v}")
        lines.append(
            "  → Aplica estas reglas antes de actuar. Si dudas, pregunta."
        )
        return "\n".join(lines)
    except Exception:
        return ""
