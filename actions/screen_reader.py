"""screen_reader.py — Accessibility screen reader.
Captures a region or the full screen, analyzes via Gemini vision (multimodal),
and can narrate, extract text, locate UI elements, or describe layout."""
from __future__ import annotations
import base64, io, json, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _load_keys() -> dict:
    try:
        from core.secure_config import read_config
        return read_config()
    except Exception:
        p = BASE_DIR / "config" / "api_keys.json"
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: return {}

def _screenshot_b64(region: tuple | None = None) -> str:
    """Take a screenshot and return base64-encoded JPEG."""
    import pyautogui
    from PIL import Image
    img = pyautogui.screenshot(region=region)
    # Downscale for API
    w, h = img.size
    if w > 1920:
        ratio = 1920 / w
        img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode()

def _gemini_vision(b64: str, prompt: str, api_key: str, model: str = "gemini-2.0-flash") -> str:
    """Call Gemini REST API with an image."""
    import urllib.request, urllib.error
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                {"text": prompt}
            ]
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}
    }
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            return (resp.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", ""))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return f"Error API Gemini {e.code}: {body[:300]}"
    except Exception as e:
        return f"Error: {e}"

def _openrouter_vision(b64: str, prompt: str, api_key: str) -> str:
    """Call OpenRouter with vision (GPT-4o or Claude)."""
    import urllib.request, urllib.error
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        "max_tokens": 1024
    }
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://jarvis.local",
        "X-Title": "JARVIS"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            return (resp.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", ""))
    except Exception as e:
        return f"Error: {e}"

# ══════════════════════════════════════════════════════════════════════════════
def screen_reader(parameters: dict, player=None) -> str:
    action    = parameters.get("action", "describe").lower().strip()
    region_p  = parameters.get("region")   # [x, y, w, h] or null
    prompt_ov = parameters.get("prompt", "").strip()
    element   = parameters.get("element", "").strip()
    window    = parameters.get("window", "").strip()

    def log(msg):
        if player: player.write_log(f"👁 {msg}")

    keys = _load_keys()
    api_key    = keys.get("gemini_api_key", keys.get("google_api_key", "")).strip()
    openrouter = keys.get("openrouter_api_key", "").strip()

    if not api_key and not openrouter:
        return "Screen reader requiere gemini_api_key u openrouter_api_key en la configuración."

    # Build region tuple
    region = None
    if region_p and isinstance(region_p, (list, tuple)) and len(region_p) == 4:
        region = tuple(int(x) for x in region_p)

    # Focus window if requested
    if window:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(window)
            if wins:
                wins[0].activate()
                import time; time.sleep(0.4)
        except Exception:
            pass

    # ── Take screenshot ────────────────────────────────────────────────────────
    try:
        log(f"Capturando {f'región {region}' if region else 'pantalla completa'}…")
        b64 = _screenshot_b64(region)
    except Exception as e:
        return f"Error capturando pantalla: {e}. Necesitás pyautogui y Pillow."

    # ── Build prompt based on action ───────────────────────────────────────────
    if action in ("describe", "describir", "read", "leer", "ver", "analyze"):
        prompt = prompt_ov or "Describí detalladamente lo que ves en esta pantalla en español. Mencioná todos los textos visibles, ventanas abiertas, botones, menús y contenido importante."

    elif action in ("ocr", "extract_text", "texto", "leer_texto"):
        prompt = "Extraé y transcribí TODO el texto visible en esta pantalla, manteniendo la estructura y el formato. Solo el texto, sin descripciones adicionales."

    elif action in ("find", "buscar", "locate", "localizar"):
        if not element:
            return "Especificá el elemento a buscar con el parámetro 'element'."
        prompt = (f"Buscá el elemento '{element}' en esta pantalla. "
                  "Indicá: ¿está visible? ¿dónde está (arriba/abajo/izquierda/derecha/centro)? "
                  "¿Cuál es su posición aproximada en píxeles? "
                  "Respondé en español.")

    elif action in ("ui", "interface", "interfaz"):
        prompt = ("Describí la interfaz de usuario visible: "
                  "ventanas abiertas, aplicaciones activas, botones, menús, campos de texto, "
                  "contenido principal. Sé específico para que alguien pueda navegar por ella sin verla.")

    elif action in ("accessibility", "accesibilidad", "narrate", "narrar"):
        prompt = ("Actuá como lector de pantalla para accesibilidad. "
                  "Narrá todo el contenido de esta pantalla de manera clara y ordenada: "
                  "aplicación activa, contenido principal, botones disponibles, "
                  "estado del sistema (hora, batería, notificaciones).")

    elif action in ("check_change", "changed", "cambio"):
        prompt = (f"Describí brevemente los elementos más importantes activos en esta pantalla. "
                  "¿Qué aplicación está en primer plano y qué muestra?")

    elif prompt_ov:
        prompt = prompt_ov

    else:
        prompt = "Describí esta pantalla en español de manera concisa."

    # ── Call vision API ────────────────────────────────────────────────────────
    if api_key:
        log("Analizando con Gemini Vision…")
        result = _gemini_vision(b64, prompt, api_key)
    elif openrouter:
        log("Analizando con OpenRouter Vision…")
        result = _openrouter_vision(b64, prompt, openrouter)
    else:
        result = "No hay API key configurada para visión."

    if not result:
        result = "No pude obtener una respuesta de la API de visión."

    log(f"Screen reader: {result[:80]}…")
    return result
