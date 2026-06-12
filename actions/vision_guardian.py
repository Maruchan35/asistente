# -*- coding: utf-8 -*-
"""
vision_guardian.py — Premium active screen monitoring and contextual suggestion agent for JARVIS.
"""
import os
import json
import time
import base64
import threading
import traceback
import urllib.request
import urllib.error
from pathlib import Path
from mss import mss
from PIL import Image
import io

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
STATE_FILE = CONFIG_DIR / "vision_guardian_state.json"
API_FILE = CONFIG_DIR / "api_keys.json"

_inject_fn = None
_speaking_fn = None
_loop_thread = None
_running = False

def _load_config() -> dict:
    if not API_FILE.exists():
        return {}
    try:
        from core.secure_config import read_config
        return read_config()
    except Exception:
        try:
            return json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

def _load_state() -> dict:
    if not STATE_FILE.exists():
        # Default state: disabled by default, check every 45s
        return {"enabled": False, "interval": 45}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "interval": 45}

def _save_state(state: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")

def _capture_screen_base64() -> str:
    """Capture main screen, compress it to 720p JPEG, and return as base64."""
    with mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        # Resize to save bandwidth
        max_size = (1280, 720)
        img.thumbnail(max_size, Image.Resampling.BILINEAR)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=65)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def _perform_vision_analysis() -> str:
    """Takes screenshot and queries Gemini, OpenRouter or Ollama Local for proactive alerts."""
    cfg = _load_config()
    provider = cfg.get("ai_provider", "gemini").lower().strip()
    gemini_key = cfg.get("gemini_api_key", "").strip()
    openrouter_key = cfg.get("openrouter_api_key", "").strip()
    
    # Si no hay ninguna configuración válida, salir silenciosamente
    if provider == "gemini" and not gemini_key:
        # Intentar fallback si otra clave está configurada
        if openrouter_key: provider = "openrouter"
    elif provider == "openrouter" and not openrouter_key:
        if gemini_key: provider = "gemini"
    
    try:
        b64_image = _capture_screen_base64()
    except Exception as e:
        print(f"[Guardian] Error capturing screen: {e}")
        return "NORMAL"

    query = (
        "Eres el Guardián de Visión de JARVIS. Analiza esta captura de pantalla del usuario. "
        "Si encuentras un error crítico en una terminal, un aviso importante, un mensaje urgente de chat "
        "o si el usuario está claramente atascado o necesita ayuda contextual inmediata en lo que está haciendo, "
        "genera una sugerencia o aviso súper conciso, directo e inteligente en español de MÁXIMO 12 palabras. "
        "Si todo está normal, no hay errores, alertas urgentes ni oportunidades de ayuda contextual inmediata, "
        "responde ÚNICAMENTE con la palabra 'NORMAL' y nada más. Sé sumamente selectivo."
    )

    # --- Método 1: Ollama Local ---
    if provider == "ollama":
        ollama_url = cfg.get("ollama_url", "http://127.0.0.1:11434").strip().rstrip("/")
        ollama_model = cfg.get("ollama_model", "phi3").strip()
        
        url = f"{ollama_url}/api/chat"
        payload = {
            "model": ollama_model,
            "messages": [
                {
                    "role": "user",
                    "content": query,
                    "images": [b64_image]
                }
            ],
            "options": {
                "temperature": 0.1,
                "num_predict": 30
            },
            "stream": False
        }
        
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode("utf-8"), 
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if "message" in resp_data and "content" in resp_data["message"]:
                    return resp_data["message"]["content"].strip()
        except Exception as e:
            print(f"[Guardian] Local Ollama Guardian check failed: {e}")

    # --- Método 2: Google Gemini SDK Nativo ---
    elif provider == "gemini" and gemini_key:
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=gemini_key)
            raw_bytes = base64.b64decode(b64_image)
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(parts=[
                        types.Part(text=query),
                        types.Part(
                            inline_data=types.Blob(data=raw_bytes, mime_type="image/jpeg")
                        )
                    ])
                ]
            )
            res_text = response.text
            if res_text and res_text.strip():
                return res_text.strip()
        except Exception as e:
            print(f"[Guardian] Native Gemini API failed: {e}. Trying OpenRouter fallback...")

    # --- Método 3: Fallback a OpenRouter ---
    if openrouter_key and (provider == "openrouter" or gemini_key):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "HTTP-Referer": "https://github.com/jarvis-beta",
            "X-Title": "JARVIS Proactive Vision Guardian",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "google/gemini-2.5-flash",
            "max_tokens": 150,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": query
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}"
                            }
                        }
                    ]
                }
            ]
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if "choices" in resp_data and len(resp_data["choices"]) > 0:
                    return resp_data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[Guardian] OpenRouter API Request failed: {e}")

    return "NORMAL"

def _guardian_loop():
    global _running, _inject_fn, _speaking_fn
    print("[Guardian] Thread loop started successfully.")
    
    while _running:
        try:
            state = _load_state()
            enabled = state.get("enabled", False)
            interval = int(state.get("interval", 45))
            if interval < 10: interval = 10
            
            # Simple sleep intervals
            for _ in range(interval):
                if not _running:
                    return
                time.sleep(1.0)

            if enabled and _inject_fn and _speaking_fn:
                # Avoid injecting text if JARVIS is already talking
                is_speaking = False
                try:
                    is_speaking = _speaking_fn()
                except Exception:
                    pass

                if not is_speaking:
                    print("[Guardian] Performing proactive screen check...")
                    result = _perform_vision_analysis()
                    
                    # Clean response
                    res_clean = result.replace("'", "").replace('"', '').strip()
                    if res_clean and "normal" not in res_clean.lower() and len(res_clean) > 3:
                        print(f"[Guardian] Sugerencia proactiva detectada: {res_clean}")
                        try:
                            # Thread-safe text injection into the live stream
                            _inject_fn(f"[ALERTA PROACTIVA DE TU PANTALLA]: {res_clean}")
                        except Exception as ie:
                            print(f"[Guardian] Error injecting suggestion: {ie}")
                            
        except Exception as ex:
            print(f"[Guardian] Loop Exception: {ex}")
            time.sleep(5.0)

def start(inject_fn, speaking_fn) -> None:
    """Registers callbacks and starts the proactive background scanner loop."""
    global _inject_fn, _speaking_fn, _loop_thread, _running
    _inject_fn = inject_fn
    _speaking_fn = speaking_fn

    if _running:
        return

    _running = True
    _loop_thread = threading.Thread(target=_guardian_loop, name="vision-guardian", daemon=True)
    _loop_thread.start()
    print("[Guardian] Vision Guardian subsystem initialized.")

def vision_guardian(parameters: dict, player=None) -> str:
    """
    JARVIS tool function. Controls activation and settings of the screen monitoring system.
    """
    action = parameters.get("action", "status").lower().strip()
    seconds = parameters.get("seconds", None)

    state = _load_state()

    if action == "enable":
        state["enabled"] = True
        _save_state(state)
        msg = "El Guardián de Visión ha sido ACTIVADO. Vigilaré tu pantalla en segundo plano para darte asistencia proactiva."
        if player: player.write_log(f"👁️ {msg}")
        return msg

    elif action == "disable":
        state["enabled"] = False
        _save_state(state)
        msg = "El Guardián de Visión ha sido DESACTIVADO. Ya no monitorearé tu pantalla en segundo plano."
        if player: player.write_log(f"👁️ {msg}")
        return msg

    elif action == "set_interval":
        if seconds is None:
            return "Error: Se requiere el parámetro 'seconds' para cambiar el intervalo."
        sec = int(seconds)
        if sec < 15 or sec > 600:
            return "Error: El intervalo debe estar entre 15 y 600 segundos."
        state["interval"] = sec
        _save_state(state)
        msg = f"Intervalo del Guardián de Visión configurado a {sec} segundos."
        if player: player.write_log(f"👁️ {msg}")
        return msg

    elif action == "check_now":
        if player: player.write_log("👁️ Ejecutando escaneo inmediato de pantalla...")
        result = _perform_vision_analysis()
        if not result or "normal" in result.lower():
            return "Escaneo de pantalla completado. Todo se ve normal y en orden, señor."
        return f"Escaneo de pantalla completado. Sugerencia proactiva: {result}"

    else: # status action
        status_str = "Activo" if state.get("enabled", False) else "Inactivo"
        interval = state.get("interval", 45)
        return f"Estado del Guardián de Visión: {status_str}. Intervalo de escaneo actual: cada {interval} segundos."
