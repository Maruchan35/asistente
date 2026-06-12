# -*- coding: utf-8 -*-
"""
openrouter_agent.py — Unified Local AI (Ollama) and Cloud API (OpenRouter) completion agent for JARVIS.
"""
import json
import urllib.request
import urllib.error
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"

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

def openrouter_agent(query: str, model: str = "google/gemini-2.5-flash") -> str:
    """
    Routes complex queries to either OpenRouter (Cloud) or Ollama (Local AI)
    based on user settings.
    """
    cfg = _load_config()
    provider = cfg.get("ai_provider", "openrouter").lower().strip()

    # INYECTAR FECHA Y HORA ACTUAL PARA EVITAR ALUCINACIONES
    from datetime import datetime
    now = datetime.now()
    time_str = now.strftime("%A, %d %B %Y — %I:%M:%S %p")
    time_context = f" La fecha y hora actual en el sistema del usuario es: {time_str}. Usa este tiempo exacto para responder si el usuario pregunta la hora o hace peticiones relativas al tiempo."

    # 1. LOCAL OLLAMA ROUTING
    if provider == "ollama":
        ollama_url = cfg.get("ollama_url", "http://127.0.0.1:11434").strip().rstrip("/")
        ollama_model = cfg.get("ollama_model", "gemma2:2b").strip()
        
        url = f"{ollama_url}/api/chat"
        payload = {
            "model": ollama_model,
            "messages": [
                {"role": "system", "content": "Eres JARVIS, un asistente inteligente local. Responde de forma clara, directa, muy concisa y al grano en español." + time_context},
                {"role": "user", "content": query}
            ],
            "options": {
                "temperature": 0.3,
                "num_predict": 150
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
            with urllib.request.urlopen(req, timeout=45) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if "message" in resp_data and "content" in resp_data["message"]:
                    return resp_data["message"]["content"]
                else:
                    return "Error: Respuesta inesperada de Ollama local."
        except urllib.error.URLError as e:
            return (
                f"Error al conectar con Ollama local ({ollama_url}): {e.reason}.\n"
                "Asegúrate de que Ollama esté ejecutándose en tu máquina (ollama serve) y de haber descargado el modelo."
            )
        except Exception as e:
            return f"Error en la llamada a Ollama local: {str(e)}"

    # 2. CLOUD OPENROUTER ROUTING (Default)
    else:
        api_key = cfg.get("openrouter_api_key", "").strip()
        if not api_key:
            return (
                "No se encontró una clave de OpenRouter en la configuración. "
                "Por favor, añade 'openrouter_api_key' en config/api_keys.json o cambia a Ollama Local."
            )

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/jarvis-beta",
            "X-Title": "JARVIS AI Assistant",
            "Content-Type": "application/json"
        }
        
        # Override default model with config model if specified
        active_model = cfg.get("openrouter_model", model).strip()
        
        payload = {
            "model": active_model,
            "max_tokens": 1500,
            "messages": [
                {"role": "system", "content": "Eres un Agente Especialista de JARVIS. Responde de forma clara, directa y muy concisa en español." + time_context},
                {"role": "user", "content": query}
            ]
        }

        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode("utf-8"), 
                headers=headers, 
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    return response_data["choices"][0]["message"]["content"]
                else:
                    return "Error: Respuesta vacía o inesperada de OpenRouter."
        except urllib.error.HTTPError as e:
            error_info = e.read().decode("utf-8")
            return f"Error de OpenRouter (HTTP {e.code}): {error_info}"
        except Exception as e:
            return f"Error al conectar con OpenRouter: {str(e)}"
