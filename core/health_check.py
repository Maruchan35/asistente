"""
core/health_check.py — Chequeo de salud al arrancar JARVIS.

Verifica en ~1 segundo:
  • API key de Gemini presente y no-placeholder
  • Micrófono(s) de entrada disponibles + el configurado existe
  • Salida de audio disponible
  • Espacio en disco
  • Errores recientes en logs/errors.jsonl (últimas 24h)
  • Modelo Vosk presente (wake word offline)

Devuelve un reporte estructurado + resumen de una línea para la consola.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent


def run_health_check() -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "", warn: bool = False):
        checks.append({"name": name, "ok": ok, "warn": warn, "detail": detail})

    # ── API key ───────────────────────────────────────────────────────────────
    try:
        try:
            from core.secure_config import read_config
            cfg = read_config()
        except Exception:
            cfg = json.loads((_BASE / "config" / "api_keys.json").read_text(encoding="utf-8"))
        key = cfg.get("gemini_api_key", "").strip()
        if not key or key.upper().startswith("YOUR_") or "AQUI" in key.upper():
            add("gemini_api_key", False, "falta o es placeholder")
        else:
            add("gemini_api_key", True)
        if not cfg.get("openrouter_api_key", "").strip() and not cfg.get("deepseek_api_key", "").strip():
            add("llm_fallback", True, "sin OpenRouter/DeepSeek — deep_research no disponible", warn=True)
        else:
            add("llm_fallback", True)
    except Exception as e:
        add("config", False, f"api_keys.json ilegible: {e}")
        cfg = {}

    # ── Audio ─────────────────────────────────────────────────────────────────
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs  = [d for d in devices if d.get("max_input_channels", 0) > 0]
        outputs = [d for d in devices if d.get("max_output_channels", 0) > 0]
        add("microfono", bool(inputs), f"{len(inputs)} dispositivos de entrada")
        add("altavoz",   bool(outputs), f"{len(outputs)} dispositivos de salida")
        mic_dev = cfg.get("mic_device", None)
        if isinstance(mic_dev, int) and mic_dev >= 0:
            if mic_dev >= len(devices) or devices[mic_dev].get("max_input_channels", 0) == 0:
                add("mic_configurado", False,
                    f"mic_device={mic_dev} no existe/no es entrada — se usará el default", warn=True)
            else:
                add("mic_configurado", True, devices[mic_dev]["name"][:40])
    except Exception as e:
        add("audio", False, f"sounddevice falló: {e}")

    # ── Disco ─────────────────────────────────────────────────────────────────
    try:
        import shutil
        free_gb = shutil.disk_usage(str(_BASE)).free / (1024 ** 3)
        add("disco", free_gb > 2, f"{free_gb:.1f} GB libres",
            warn=(2 < free_gb < 10))
    except Exception:
        pass

    # ── Errores recientes ─────────────────────────────────────────────────────
    try:
        err_path = _BASE / "logs" / "errors.jsonl"
        recent = 0
        if err_path.exists():
            cutoff = time.time() - 86400
            from datetime import datetime
            with open(err_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        ts = datetime.fromisoformat(e.get("ts", "1970-01-01")).timestamp()
                        if ts >= cutoff:
                            recent += 1
                    except Exception:
                        pass
        add("errores_24h", recent < 10, f"{recent} errores en 24h", warn=(0 < recent < 10))
    except Exception:
        pass

    # ── Vosk (wake word offline) ──────────────────────────────────────────────
    _vosk_ok = (_BASE / "config" / "vosk_model").is_dir()
    add("vosk_model", True,
        "wake word offline OK" if _vosk_ok
        else "no descargado — wake word usará fallback online (python download_vosk.py)",
        warn=not _vosk_ok)

    # ── Resumen ───────────────────────────────────────────────────────────────
    fails = [c for c in checks if not c["ok"]]
    warns = [c for c in checks if c["ok"] and c.get("warn")]
    if fails:
        summary = ("Problemas: "
                   + "; ".join(f"{c['name']} ({c['detail']})" for c in fails))
    elif warns:
        summary = ("Operativo con avisos: "
                   + "; ".join(f"{c['name']}: {c['detail']}" for c in warns))
    else:
        summary = "Todos los sistemas operativos."

    return {"ok": not fails, "summary": summary, "checks": checks}


def print_health_report() -> dict:
    """Correr y mostrar en consola. Devuelve el reporte."""
    report = run_health_check()
    icon = "OK " if report["ok"] else "!! "
    print(f"[HEALTH] {icon}{report['summary']}")
    for c in report["checks"]:
        if not c["ok"] or c.get("warn"):
            mark = "x" if not c["ok"] else "!"
            print(f"[HEALTH]   [{mark}] {c['name']}: {c['detail']}")
    return report
