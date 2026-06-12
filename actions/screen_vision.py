# -*- coding: utf-8 -*-
import os
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path
from mss import mss
from PIL import Image
import io

API_FILE = Path("config/api_keys.json")

def _load_config() -> dict:
    """Loads configuration from config/api_keys.json."""
    if not API_FILE.exists():
        return {}
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _capture_screen_base64(save_path: Path = None) -> str:
    """
    Captura la pantalla principal, la redimensiona/comprime,
    la guarda opcionalmente en disco y la devuelve en base64.
    """
    with mss() as sct:
        monitor = sct.monitors[1] # Monitor principal
        screenshot = sct.grab(monitor)
        
        # Convertir a imagen de Pillow
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        # Redimensionar si es muy grande para ahorrar tokens/ancho de banda
        max_size = (1280, 720)
        img.thumbnail(max_size, Image.Resampling.BILINEAR)
        
        # Guardar en archivo local para que el usuario pueda verlo si lo solicita
        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(save_path, format="PNG")
        
        # Guardar en buffer en memoria como JPEG
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=65)
        
        # Codificar a base64
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return img_b64

def screen_vision(parameters: dict, player=None) -> str:
    """
    Toma una captura de pantalla y la analiza de forma multimodal.
    Respeta la elección de IA del usuario: Google Gemini, OpenRouter o Ollama Local.
    """
    cfg = _load_config()
    provider = cfg.get("ai_provider", "gemini").lower().strip()
    gemini_key = cfg.get("gemini_api_key", "").strip()
    openrouter_key = cfg.get("openrouter_api_key", "").strip()
    
    query = parameters.get("query") or parameters.get("text") or parameters.get("question") or "¿Qué ves en mi pantalla?"
    action = parameters.get("action", "describe").lower().strip()
    
    # Ruta local de guardado de pantalla
    img_path = Path("config/last_captured_screen.png")
    
    if player:
        player.write_log(f"👁️ Capturando pantalla en segundo plano para análisis ({provider.upper()})...")
        
    try:
        b64_image = _capture_screen_base64(save_path=img_path)
    except Exception as e:
        return f"Error al capturar la pantalla: {e}"

    # ── Optimización de cuota: cache + OCR local ──────────────────────────────
    # Solo para action='question'/'describe' (no para 'show').
    try:
        import base64 as _b64
        from core import vision_cache as _vc
        _img_bytes = _b64.b64decode(b64_image)
        # 1. Cache: misma pantalla + misma pregunta hace < 8s → respuesta cacheada
        _cached = _vc.get_cached(_img_bytes, query)
        if _cached is not None:
            if player:
                try: player.write_log("👁️ (cache de visión — sin gastar cuota)")
                except Exception: pass
            return _cached
        # 2. OCR local: si solo se pide TEXTO plano y hay motor OCR instalado
        if _vc.is_text_only_query(query):
            _ocr_text = _vc.ocr_image(_img_bytes)
            if _ocr_text:
                _vc.put_cache(_img_bytes, query, _ocr_text)
                if player:
                    try: player.write_log("👁️ (OCR local — sin gastar cuota)")
                    except Exception: pass
                return f"Texto extraído de la pantalla:\n{_ocr_text}"
    except Exception:
        pass

    # Verificar si el usuario solicita mostrar o ver lo que JARVIS está viendo
    show_words = ["mostrar", "muestra", "ver", "show", "mostrame", "visu", "pantalla"]
    should_show = (action == "show") or any(w in query.lower() for w in show_words)
    
    if should_show:
        try:
            if img_path.exists():
                os.startfile(img_path)
                if player:
                    player.write_log("👁️ ¡Abriendo la captura de pantalla en tu visor de Windows, señor!")
        except Exception as se:
            if player:
                player.write_log(f"⚠️ No se pudo abrir la imagen automáticamente: {se}")

    errors = []

    # --- CASO 1: Ollama (IA Local) ---
    if provider == "ollama":
        ollama_url = cfg.get("ollama_url", "http://127.0.0.1:11434").strip().rstrip("/")
        ollama_model = cfg.get("ollama_model", "phi3").strip() # Recomendado usar un modelo con visión
        
        if player:
            player.write_log(f"[Visión Local] Consultando Ollama ({ollama_model}) en {ollama_url}...")
            
        url = f"{ollama_url}/api/chat"
        payload = {
            "model": ollama_model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Esta es una captura de mi pantalla. {query}",
                    "images": [b64_image]
                }
            ],
            "options": {
                "temperature": 0.1,
                "num_predict": 200
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
            with urllib.request.urlopen(req, timeout=50) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if "message" in resp_data and "content" in resp_data["message"]:
                    return resp_data["message"]["content"].strip()
                else:
                    return (
                        "Error: Respuesta inesperada de Ollama local. Asegúrate de configurar "
                        "un modelo con soporte de visión multimodal (ej. llama3.2-vision o llava)."
                    )
        except urllib.error.URLError as e:
            err_msg = f"Error al conectar con Ollama local ({ollama_url}): {e.reason}"
            errors.append(err_msg)
            if player:
                player.write_log(f"[Visión Local] {err_msg}")
        except Exception as e:
            err_msg = f"Error en la llamada a Ollama local: {str(e)}"
            errors.append(err_msg)
            if player:
                player.write_log(f"[Visión Local] {err_msg}")

    # --- CASO 2: Google Gemini SDK Nativo ---
    elif provider == "gemini" and gemini_key:
        try:
            if player:
                player.write_log("[Visión Nube] Intentando análisis nativo con Google Gemini API...")
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=gemini_key)
            raw_bytes = base64.b64decode(b64_image)
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(parts=[
                        types.Part(text=f"Esta es una captura de mi pantalla. {query}"),
                        types.Part(
                            inline_data=types.Blob(data=raw_bytes, mime_type="image/jpeg")
                        )
                    ])
                ]
            )
            res_text = response.text
            if res_text and res_text.strip():
                _ans = res_text.strip()
                # Poblar cache para evitar re-consultas idénticas en ~8s
                try:
                    import base64 as _b64
                    from core import vision_cache as _vc
                    _vc.put_cache(_b64.b64decode(b64_image), query, _ans)
                except Exception:
                    pass
                return _ans
            else:
                errors.append("Gemini nativo devolvió una respuesta vacía.")
        except Exception as e:
            err_msg = f"Fallo en Gemini nativo: {str(e)}"
            errors.append(err_msg)
            if player:
                player.write_log(f"[Visión] {err_msg}")

    # --- CASO 3: OpenRouter (Cloud fallback) ---
    elif provider == "openrouter" and openrouter_key:
        try:
            if player:
                player.write_log("[Visión Nube] Intentando análisis vía OpenRouter...")
                
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "HTTP-Referer": "https://github.com/jarvis-beta",
                "X-Title": "JARVIS AI Assistant",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "google/gemini-2.5-flash",
                "max_tokens": 1500,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Esta es una captura de mi pantalla. {query}"
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
            
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=45) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    return response_data["choices"][0]["message"]["content"]
                else:
                    errors.append("Respuesta inesperada de OpenRouter.")
        except Exception as e:
            errors.append(f"Fallo en OpenRouter: {str(e)}")

    # --- FALLBACK DE SEGURIDAD ---
    # Si el proveedor preferido falló o no estaba configurado, intentar con cualquiera disponible
    if not errors:
        # Si llegó aquí es porque no tiene configurada la clave del proveedor elegido
        errors.append(f"El proveedor '{provider}' no está completamente configurado o faltan credenciales.")

    if provider != "gemini" and gemini_key:
        try:
            if player:
                player.write_log("[Visión Fallback] Intentando recuperar con Gemini Nube...")
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            raw_bytes = base64.b64decode(b64_image)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(parts=[
                        types.Part(text=f"Esta es una captura de mi pantalla. {query}"),
                        types.Part(inline_data=types.Blob(data=raw_bytes, mime_type="image/jpeg"))
                    ])
                ]
            )
            if response.text and response.text.strip():
                return response.text.strip()
        except Exception:
            pass

    if provider != "openrouter" and openrouter_key:
        try:
            if player:
                player.write_log("[Visión Fallback] Intentando recuperar con OpenRouter...")
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {openrouter_key}", "HTTP-Referer": "https://github.com/jarvis-beta", "X-Title": "JARVIS AI Assistant", "Content-Type": "application/json"}
            payload = {"model": "google/gemini-2.5-flash", "max_tokens": 1500, "messages": [{"role": "user", "content": [{"type": "text", "text": f"Esta es una captura de mi pantalla. {query}"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}]}]}
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=45) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    return response_data["choices"][0]["message"]["content"]
        except Exception:
            pass

    # Si todo falló, reportar
    err_report = "\n- ".join(errors)
    return (
        f"Fallo de visión multiservicio. No se pudo procesar la pantalla con el proveedor '{provider}':\n- {err_report}\n\n"
        "Verifica tu configuración de IA (Gemini Key, OpenRouter Key u Ollama Local ejecutándose)."
    )
