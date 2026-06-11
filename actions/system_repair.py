# -*- coding: utf-8 -*-
"""
system_repair.py — Playbook de reparaciones del sistema.

Mapa síntoma → acción para problemas comunes, ejecutables por JARVIS
solo o bajo orden. Cada reparación se clasifica por riesgo y respeta
el nivel de autonomía (core/autonomy.is_allowed).

Reparaciones:
  wifi_reconnect   → desconectar/reconectar el adaptador WiFi (MEDIUM)
  restart_app      → matar y relanzar una app congelada (MEDIUM)
  flush_dns        → limpiar caché DNS cuando internet "anda raro" (SAFE)
  restart_audio    → reiniciar el servicio de audio de Windows (HIGH)
  disk_report      → qué está comiendo el disco — solo informa (SAFE)
  network_report   → diagnóstico de red — solo informa (SAFE)
"""
from __future__ import annotations
import subprocess
import time

_NOWIN = {"creationflags": __import__("subprocess").CREATE_NO_WINDOW} if hasattr(__import__("subprocess"), "CREATE_NO_WINDOW") else {}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, **_NOWIN)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as e:
        return 1, str(e)


_RISK = {
    "wifi_reconnect": "MEDIUM",
    "restart_app":    "MEDIUM",
    "flush_dns":      "SAFE",
    "restart_audio":  "HIGH",
    "disk_report":    "SAFE",
    "network_report": "SAFE",
}


def system_repair(parameters: dict, player=None) -> str:
    from core.autonomy import is_allowed, audit, get_level

    repair = (parameters.get("repair") or "").lower()
    target = parameters.get("target", "")
    confirmed = parameters.get("confirmed", False)
    if isinstance(confirmed, str):
        confirmed = confirmed.lower() in ("true", "1", "yes", "sí", "si")

    if repair not in _RISK:
        return ("Reparación no reconocida. Disponibles: wifi_reconnect, restart_app, "
                "flush_dns, restart_audio, disk_report, network_report.")

    risk = _RISK[repair]
    # Los reports son SOLO LECTURA (sin efectos) — no pasan por el gate.
    _read_only = repair in ("disk_report", "network_report")
    # Confirmación del usuario salta el gate; si no, decide el nivel de autonomía
    if not _read_only and not confirmed and not is_allowed(risk):
        return (f"La reparación '{repair}' es riesgo {risk} y el nivel de autonomía "
                f"actual ({get_level()}) no la permite automáticamente. "
                "Pida confirmación al usuario y re-llame con confirmed=true.")

    def _log(m):
        if player:
            try: player.write_log(m)
            except Exception: pass

    # ── WIFI RECONNECT ────────────────────────────────────────────────────────
    if repair == "wifi_reconnect":
        _log("📶 Reconectando WiFi...")
        code1, out1 = _run(["netsh", "interface", "set", "interface",
                            "Wi-Fi", "disable"], timeout=20)
        time.sleep(2)
        code2, out2 = _run(["netsh", "interface", "set", "interface",
                            "Wi-Fi", "enable"], timeout=20)
        time.sleep(4)
        # Verificar
        code3, out3 = _run(["ping", "-n", "2", "-w", "2000", "8.8.8.8"], timeout=15)
        ok = code3 == 0
        result = ("WiFi reconectado y con internet." if ok
                  else f"WiFi reciclado pero sin respuesta de internet aún. ({out2[:80]})")
        audit("system_repair", "wifi_reconnect", result)
        return result

    # ── RESTART APP ───────────────────────────────────────────────────────────
    if repair == "restart_app":
        if not target:
            return "Falta 'target': nombre del proceso a reiniciar (ej: spotify)."
        name = target.lower().replace(".exe", "")
        _log(f"🔄 Reiniciando {name}...")
        # Localizar el exe antes de matarlo (para relanzarlo)
        exe_path = ""
        try:
            import psutil
            for pr in psutil.process_iter(["name", "exe"]):
                if name in (pr.info["name"] or "").lower():
                    exe_path = pr.info.get("exe") or ""
                    break
        except Exception:
            pass
        code, out = _run(["taskkill", "/IM", f"{name}.exe", "/F"], timeout=15)
        time.sleep(1.5)
        relaunched = False
        if exe_path:
            try:
                subprocess.Popen([exe_path], **_NOWIN)
                relaunched = True
            except Exception:
                pass
        if not relaunched:
            # Plan B: por nombre con el shell de apps
            try:
                from actions.open_app import open_app
                r = open_app({"app_name": target})
                relaunched = "abr" in str(r).lower() or "open" in str(r).lower()
            except Exception:
                pass
        result = (f"{target} reiniciada." if relaunched
                  else f"{target} cerrada pero no pude relanzarla automáticamente.")
        audit("system_repair", f"restart_app {target}", result)
        return result

    # ── FLUSH DNS ─────────────────────────────────────────────────────────────
    if repair == "flush_dns":
        code, out = _run(["ipconfig", "/flushdns"], timeout=15)
        result = "Caché DNS limpiada." if code == 0 else f"Error: {out[:100]}"
        audit("system_repair", "flush_dns", result)
        return result

    # ── RESTART AUDIO SERVICE ─────────────────────────────────────────────────
    if repair == "restart_audio":
        _log("🔊 Reiniciando servicio de audio...")
        _run(["net", "stop", "Audiosrv"], timeout=30)
        time.sleep(1)
        code, out = _run(["net", "start", "Audiosrv"], timeout=30)
        result = ("Servicio de audio reiniciado." if code == 0
                  else f"No se pudo reiniciar (¿requiere admin?): {out[:100]}")
        audit("system_repair", "restart_audio", result)
        return result

    # ── DISK REPORT ───────────────────────────────────────────────────────────
    if repair == "disk_report":
        import shutil as _sh
        from pathlib import Path
        usage = _sh.disk_usage("C:\\")
        free_gb  = usage.free / 1e9
        total_gb = usage.total / 1e9
        # Top carpetas pesadas del usuario (rápido: solo primer nivel)
        import os
        home = Path(os.path.expanduser("~"))
        sizes = []
        for sub in ("Downloads", "Documents", "Desktop", "Videos", "Pictures"):
            p = home / sub
            if p.is_dir():
                try:
                    total = sum(f.stat().st_size for f in p.rglob("*")
                                if f.is_file())
                    sizes.append((total, sub))
                except Exception:
                    pass
        sizes.sort(reverse=True)
        tops = ", ".join(f"{s}: {b/1e9:.1f}GB" for b, s in sizes[:3])
        return (f"Disco C: {free_gb:.0f} GB libres de {total_gb:.0f} GB "
                f"({usage.free/usage.total:.0%}). Carpetas más pesadas: {tops}.")

    # ── NETWORK REPORT ────────────────────────────────────────────────────────
    if repair == "network_report":
        code1, _ = _run(["ping", "-n", "2", "-w", "2000", "8.8.8.8"], timeout=15)
        code2, _ = _run(["ping", "-n", "2", "-w", "2000", "google.com"], timeout=15)
        if code1 == 0 and code2 == 0:
            return "Red OK: internet y DNS funcionando."
        if code1 == 0 and code2 != 0:
            return ("Hay internet pero el DNS falla — puedo ejecutar flush_dns "
                    "para intentar arreglarlo.")
        return ("Sin respuesta de internet — puedo ejecutar wifi_reconnect "
                "si me lo autoriza.")

    return "Reparación no implementada."
