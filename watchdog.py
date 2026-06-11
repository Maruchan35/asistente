# -*- coding: utf-8 -*-
"""
watchdog.py — Supervisor de proceso de JARVIS.

Lanza main.py y lo vigila: si JARVIS crashea (exit code != 0), lo relanza
automáticamente con backoff exponencial y registra el crash en
logs/crashes.jsonl para que JARVIS pueda reportarlo al usuario al volver.

Salida limpia (exit code 0, ej. "apágate") NO se relanza.
Tras 5 crashes en 10 minutos, se rinde (algo está roto de verdad)
y deja el último error en pantalla.

Uso:  JARVIS_Watchdog.bat   (o)   python watchdog.py
"""
from __future__ import annotations
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
CRASH_LOG = BASE / "logs" / "crashes.jsonl"

MAX_CRASHES = 5
CRASH_WINDOW_S = 600   # 10 min


def log_crash(exit_code: int, uptime_s: float) -> None:
    try:
        CRASH_LOG.parent.mkdir(exist_ok=True)
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "exit_code": exit_code,
                "uptime_s": round(uptime_s, 1),
            }) + "\n")
    except Exception:
        pass


def main() -> int:
    venv_py = BASE / ".venv" / "Scripts" / "python.exe"
    python = str(venv_py) if venv_py.exists() else sys.executable
    main_py = str(BASE / "main.py")

    crash_times: list[float] = []
    backoff = 2.0

    print("[WATCHDOG] Supervisor de JARVIS activo.")
    while True:
        start = time.time()
        print(f"[WATCHDOG] Lanzando JARVIS ({datetime.now():%H:%M:%S})...")
        try:
            proc = subprocess.Popen([python, main_py], cwd=str(BASE))
            exit_code = proc.wait()
        except KeyboardInterrupt:
            print("[WATCHDOG] Interrumpido por el usuario. Adiós.")
            try:
                proc.terminate()
            except Exception:
                pass
            return 0
        uptime = time.time() - start

        if exit_code == 0:
            print("[WATCHDOG] JARVIS cerró limpiamente. Fin de la supervisión.")
            return 0

        # Crash
        log_crash(exit_code, uptime)
        now = time.time()
        crash_times = [t for t in crash_times if now - t < CRASH_WINDOW_S]
        crash_times.append(now)
        print(f"[WATCHDOG] !! JARVIS crasheó (exit={exit_code}, uptime={uptime:.0f}s) "
              f"— crash {len(crash_times)}/{MAX_CRASHES} en la ventana")

        if len(crash_times) >= MAX_CRASHES:
            print("[WATCHDOG] Demasiados crashes seguidos — algo está roto de verdad.")
            print("           Revisa logs/errors.jsonl y logs/crashes.jsonl")
            input("           Presiona Enter para salir...")
            return 1

        # Si aguantó > 5 min, resetear el backoff
        if uptime > 300:
            backoff = 2.0
        print(f"[WATCHDOG] Relanzando en {backoff:.0f}s...")
        time.sleep(backoff)
        backoff = min(60.0, backoff * 2)


if __name__ == "__main__":
    sys.exit(main())
