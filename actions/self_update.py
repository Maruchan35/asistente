# -*- coding: utf-8 -*-
"""
self_update.py — "JARVIS, actualízate": trae la última versión del repo.

Flujo:
  1. `git fetch` + comparar HEAD local vs origin/main
  2. Si hay cambios: `git pull --ff-only` (NUNCA pisa cambios locales —
     si hay conflicto, aborta y reporta)
  3. Si requirements.txt cambió: `pip install -r requirements.txt`
  4. Ofrece reiniciar JARVIS para aplicar (action='restart')

Acciones:
  check    → ¿hay actualización disponible? (no toca nada)
  update   → fetch + pull + pip si hace falta
  restart  → reinicia el proceso de JARVIS (aplica la actualización)
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent


def _run_git(*args, timeout: int = 60) -> tuple[int, str]:
    """Ejecutar git en el repo. Devuelve (returncode, salida)."""
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(_BASE),
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out.strip()
    except FileNotFoundError:
        return 127, "git no está instalado o no está en el PATH."
    except subprocess.TimeoutExpired:
        return 124, "git tardó demasiado (timeout)."
    except Exception as e:
        return 1, str(e)


def _check_updates() -> tuple[bool, str]:
    """Fetch y comparar. Devuelve (hay_updates, detalle)."""
    code, out = _run_git("fetch", "origin", timeout=90)
    if code != 0:
        return False, f"No se pudo consultar el repositorio: {out[:200]}"

    code, local = _run_git("rev-parse", "HEAD")
    if code != 0:
        return False, f"Error leyendo versión local: {local[:150]}"
    code, remote = _run_git("rev-parse", "origin/main")
    if code != 0:
        return False, f"Error leyendo versión remota: {remote[:150]}"

    if local.strip() == remote.strip():
        return False, "JARVIS ya está en la última versión."

    # ¿Cuántos commits de diferencia y cuáles?
    _, log = _run_git("log", "--oneline", "HEAD..origin/main", "--no-merges")
    n = len([l for l in log.split("\n") if l.strip()])
    return True, f"{n} actualización(es) disponible(s):\n{log[:600]}"


def _requirements_changed() -> bool:
    """¿El último pull tocó requirements.txt?"""
    code, out = _run_git("diff", "--name-only", "HEAD@{1}", "HEAD")
    if code != 0:
        return False
    return "requirements.txt" in out


def _do_update() -> str:
    has, detail = _check_updates()
    if not has:
        return detail

    # ¿Hay cambios locales sin commitear que el pull pisaría?
    code, status = _run_git("status", "--porcelain")
    dirty = [l for l in status.split("\n") if l.strip() and not l.startswith("??")]

    if dirty:
        # Stash automático para no perder nada
        code, out = _run_git("stash", "push", "-m", "jarvis-autoupdate")
        if code != 0:
            return (f"Hay cambios locales sin guardar y no pude apartarlos: {out[:200]}. "
                    "Actualización cancelada por seguridad.")
        stashed = True
    else:
        stashed = False

    code, out = _run_git("pull", "--ff-only", "origin", "main", timeout=180)
    if code != 0:
        if stashed:
            _run_git("stash", "pop")
        return f"El pull falló: {out[:300]}. Nada fue modificado."

    pip_msg = ""
    if _requirements_changed():
        try:
            venv_python = str(_BASE / ".venv" / "Scripts" / "python.exe")
            if not os.path.exists(venv_python):
                venv_python = sys.executable
            p = subprocess.run(
                [venv_python, "-m", "pip", "install", "-r",
                 str(_BASE / "requirements.txt"), "-q"],
                capture_output=True, text=True, timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            pip_msg = (" Dependencias actualizadas." if p.returncode == 0
                       else f" AVISO: pip reportó errores: {(p.stderr or '')[:150]}")
        except Exception as e:
            pip_msg = f" AVISO: no se pudieron actualizar dependencias: {e}"

    if stashed:
        code, out = _run_git("stash", "pop")
        if code != 0:
            pip_msg += (" AVISO: tus cambios locales quedaron en 'git stash' "
                        "(hubo conflicto al restaurarlos).")

    _, newlog = _run_git("log", "--oneline", "-1")
    return (f"Actualización aplicada — ahora en: {newlog}.{pip_msg} "
            "Reinicie JARVIS para aplicar los cambios "
            "(puede pedirlo con 'reinicia jarvis').")


def _do_restart() -> str:
    """Reiniciar el proceso de JARVIS (re-exec del intérprete)."""
    try:
        main_py = str(_BASE / "main.py")
        python = sys.executable
        # Lanzar el nuevo proceso desacoplado y salir del actual
        subprocess.Popen(
            [python, main_py],
            cwd=str(_BASE),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                          | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        # Salir tras 1.5s — da tiempo a que la respuesta de voz llegue al UI
        import threading, time
        def _exit_soon():
            time.sleep(1.5)
            os._exit(0)
        threading.Thread(target=_exit_soon, daemon=True).start()
        return "Reiniciando sistemas. Vuelvo en unos segundos, señor."
    except Exception as e:
        return f"No se pudo reiniciar automáticamente: {e}. Reinicie manualmente."


def self_update(parameters: dict, player=None) -> str:
    """Entry point para el dispatcher."""
    action = (parameters.get("action") or "check").lower()

    if player:
        try:
            player.write_log(f"🔄 self_update: {action}")
        except Exception:
            pass

    if action == "check":
        has, detail = _check_updates()
        if has:
            return (f"{detail}\n¿Desea que aplique la actualización, señor? "
                    "(puede decir 'sí, actualízate')")
        return detail

    if action == "update":
        return _do_update()

    if action == "restart":
        return _do_restart()

    return f"Acción '{action}' no reconocida. Use: check | update | restart."
