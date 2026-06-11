# -*- coding: utf-8 -*-
"""
autonomy_control.py — Control por voz del sistema de autonomía.

Acciones:
  set_level (1|2|3)  → cambiar la perilla de confianza
  status             → nivel actual + kill switch
  kill               → "JARVIS detente" — congelar TODO lo autónomo
  resume             → reanudar actividad autónoma
  report             → "¿qué hiciste mientras no estaba?" — auditoría
"""
from __future__ import annotations


def autonomy_control(parameters: dict, player=None) -> str:
    from core.autonomy import (
        get_level, set_level, kill, resume, is_killed,
        status, audit_report, LEVEL_NAMES,
    )

    action = (parameters.get("action") or "status").lower()

    if action == "set_level":
        try:
            level = int(parameters.get("level", 1))
        except (TypeError, ValueError):
            return "Error: nivel inválido. Use 1 (manual), 2 (asistido) o 3 (autónomo)."
        new = set_level(level)
        desc = {
            1: "Preguntaré antes de cualquier acción con efectos.",
            2: "Ejecutaré acciones seguras por mi cuenta; las riesgosas las consulto.",
            3: "Operaré con autonomía completa salvo acciones críticas, que siempre consulto.",
        }[new]
        return f"Nivel de autonomía {new} ({LEVEL_NAMES[new]}) activado. {desc}"

    if action in ("kill", "stop", "detente"):
        kill()
        return ("Toda actividad autónoma DETENIDA, señor. Solo responderé a sus "
                "órdenes directas. Diga 'reanuda la autonomía' para reactivar.")

    if action in ("resume", "reanudar"):
        resume()
        st = status()
        return (f"Actividad autónoma reanudada en nivel {st['level']} "
                f"({st['level_name']}).")

    if action == "report":
        hours = int(parameters.get("hours", 24))
        return audit_report(hours=hours)

    # status (default)
    st = status()
    killed = " — DETENIDA por kill switch" if st["killed"] else ""
    allows = ", ".join(st["allows"]) if st["allows"] else "nada automático"
    return (f"Autonomía nivel {st['level']} ({st['level_name']}){killed}. "
            f"Puedo auto-ejecutar: {allows}.")
