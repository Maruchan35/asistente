"""
core/offline_mode.py — Supervivencia sin internet.

Gemini Live ES la voz de JARVIS — si se cae el internet, JARVIS muere.
Este módulo provee un modo degradado local:
  • PENSAR  → Ollama local (ya soportado en config) si está corriendo
  • HABLAR  → pyttsx3 (offline, sin red) o edge-tts (requiere red, no sirve offline)
  • ESCUCHAR→ Vosk (ya instalado, offline)

Detecta la caída de internet con un ping ligero y avisa. No reemplaza el
loop de Gemini Live (eso lo maneja main.py); expone helpers para:
  - is_online(): chequeo rápido cacheado
  - speak_offline(texto): TTS local
  - think_offline(prompt): respuesta con Ollama local

Subset de acciones que funcionan sin internet (informativo para el prompt):
  open_app, computer_settings, file_controller, reminder, document_creator
  (local), system_monitor, screen_reader (OCR local), doc_search.
"""
from __future__ import annotations
import threading
import time

_last_check = 0.0
_last_result = True
_CHECK_TTL = 15.0    # cachear estado de red 15s


def is_online(force: bool = False) -> bool:
    """¿Hay internet? Cacheado para no pingar en cada llamada."""
    global _last_check, _last_result
    now = time.time()
    if not force and (now - _last_check) < _CHECK_TTL:
        return _last_result
    _last_check = now
    try:
        import socket
        # Conexión TCP a un DNS público — más fiable que ping en Windows
        s = socket.create_connection(("8.8.8.8", 53), timeout=3)
        s.close()
        _last_result = True
    except Exception:
        try:
            import socket
            s = socket.create_connection(("1.1.1.1", 53), timeout=3)
            s.close()
            _last_result = True
        except Exception:
            _last_result = False
    return _last_result


# ── TTS local ─────────────────────────────────────────────────────────────────

_tts_engine = None


def speak_offline(text: str) -> bool:
    """Hablar con pyttsx3 (offline puro). Devuelve True si pudo."""
    global _tts_engine
    if not text:
        return False
    try:
        if _tts_engine is None:
            import pyttsx3
            _tts_engine = pyttsx3.init()
            # Voz en español si está disponible
            try:
                for v in _tts_engine.getProperty("voices"):
                    if "spanish" in v.name.lower() or "español" in v.name.lower() or "helena" in v.name.lower():
                        _tts_engine.setProperty("voice", v.id)
                        break
            except Exception:
                pass
            _tts_engine.setProperty("rate", 180)
        _tts_engine.say(text)
        _tts_engine.runAndWait()
        return True
    except Exception:
        return False


# ── Pensar local (Ollama) ─────────────────────────────────────────────────────

def think_offline(prompt: str, max_tokens: int = 200) -> str:
    """Respuesta con Ollama local. '' si Ollama no está corriendo."""
    try:
        import json
        import urllib.request
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        try:
            from core.secure_config import read_config
            cfg = read_config()
        except Exception:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
        model = cfg.get("ollama_model", "gemma2:2b")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content":
                 "Eres JARVIS en modo offline local. Respuestas breves y útiles en español."},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.3, "num_predict": max_tokens},
            "stream": False,
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except Exception:
        return ""


def ollama_available() -> bool:
    """¿Está Ollama corriendo localmente?"""
    try:
        import json, urllib.request
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Monitor de conectividad ───────────────────────────────────────────────────

_monitor_thread = None
_monitor_stop = threading.Event()


def start_monitor(on_change=None, interval_s: int = 20):
    """Vigilar cambios de conectividad. on_change(online: bool) al cambiar."""
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _monitor_stop.clear()
    prev = {"online": is_online(force=True)}

    def _loop():
        while not _monitor_stop.is_set():
            cur = is_online(force=True)
            if cur != prev["online"]:
                prev["online"] = cur
                if on_change:
                    try: on_change(cur)
                    except Exception: pass
            _monitor_stop.wait(interval_s)

    _monitor_thread = threading.Thread(target=_loop, daemon=True, name="ConnMonitor")
    _monitor_thread.start()


def stop_monitor():
    _monitor_stop.set()


def status() -> dict:
    return {
        "online": is_online(),
        "ollama": ollama_available(),
    }
