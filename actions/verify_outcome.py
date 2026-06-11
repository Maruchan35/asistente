# -*- coding: utf-8 -*-
"""
verify_outcome.py — Verificar que una acción realmente ocurrió.

El eslabón que convierte "ejecuté la herramienta" en "el resultado EXISTE".
Gemini lo llama después de actuar para confirmar, y si la verificación falla,
reintenta por un camino alternativo (máximo 2 reintentos — regla en prompt).

Verificaciones disponibles (parámetro `check`):
  file_exists      → ¿existe el archivo/carpeta? (target = ruta)
  file_recent      → ¿existe Y fue modificado hace < max_age_s segundos?
  file_size_min    → ¿existe Y pesa al menos min_kb KB?
  process_running  → ¿hay un proceso cuyo nombre contiene target?
  window_open      → ¿hay una ventana cuyo título contiene target?
  url_reachable    → ¿la URL responde (HTTP < 500)?
  screen_contains  → ¿la pantalla muestra el texto target? (usa visión LLM)
"""
from __future__ import annotations
import os
from pathlib import Path


def _expand(p: str) -> Path:
    p = (p or "").strip().strip('"')
    p = os.path.expandvars(os.path.expanduser(p))
    return Path(p)


def verify_outcome(parameters: dict, player=None) -> str:
    check  = (parameters.get("check") or "").lower()
    target = parameters.get("target", "")

    try:
        if check == "file_exists":
            p = _expand(target)
            if p.exists():
                kind = "carpeta" if p.is_dir() else "archivo"
                return f"VERIFICADO: el {kind} existe — {p}"
            return f"FALLO LA VERIFICACIÓN: no existe {p}. Reintenta por otro camino o informa al usuario."

        if check == "file_recent":
            import time
            p = _expand(target)
            max_age = float(parameters.get("max_age_s", 300))
            if not p.exists():
                return f"FALLO: no existe {p}."
            age = time.time() - p.stat().st_mtime
            if age <= max_age:
                return f"VERIFICADO: {p.name} modificado hace {int(age)}s."
            return (f"FALLO: {p.name} existe pero fue modificado hace {int(age)}s "
                    f"(esperado < {int(max_age)}s) — probablemente es una versión vieja.")

        if check == "file_size_min":
            p = _expand(target)
            min_kb = float(parameters.get("min_kb", 1))
            if not p.exists():
                return f"FALLO: no existe {p}."
            kb = p.stat().st_size / 1024
            if kb >= min_kb:
                return f"VERIFICADO: {p.name} pesa {kb:.0f} KB (≥ {min_kb:.0f} KB)."
            return f"FALLO: {p.name} pesa solo {kb:.1f} KB — posiblemente vacío o corrupto."

        if check == "process_running":
            import psutil
            needle = target.lower().replace(".exe", "")
            hits = [pr.info["name"] for pr in psutil.process_iter(["name"])
                    if needle in (pr.info["name"] or "").lower()]
            if hits:
                return f"VERIFICADO: proceso corriendo — {hits[0]} ({len(hits)} instancia(s))."
            return f"FALLO: ningún proceso contiene '{target}'. La app no está corriendo."

        if check == "window_open":
            import pygetwindow as gw
            needle = target.lower()
            wins = [w.title for w in gw.getAllWindows()
                    if w.title and needle in w.title.lower()]
            if wins:
                return f"VERIFICADO: ventana abierta — '{wins[0][:60]}'."
            return f"FALLO: ninguna ventana contiene '{target}' en el título."

        if check == "url_reachable":
            import urllib.request
            req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0 JARVIS"})
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    return f"VERIFICADO: {target} responde (HTTP {resp.status})."
            except Exception as e:
                return f"FALLO: {target} no responde — {str(e)[:80]}."

        if check == "screen_contains":
            try:
                from actions.screen_vision import screen_vision
                r = screen_vision({
                    "action": "question",
                    "question": (
                        f"Responde SOLO 'SI' o 'NO': ¿la pantalla muestra "
                        f"actualmente '{target}' o algo claramente equivalente?"
                    ),
                }, player=player)
                if r and "si" in r.lower()[:20]:
                    return f"VERIFICADO: la pantalla muestra '{target}'."
                return f"FALLO: la pantalla NO muestra '{target}' (visión: {str(r)[:80]})."
            except Exception as e:
                return f"No se pudo verificar visualmente: {e}"

        return (f"Check '{check}' no reconocido. Disponibles: file_exists, file_recent, "
                "file_size_min, process_running, window_open, url_reachable, screen_contains.")
    except Exception as e:
        return f"Error en verificación: {e}"
