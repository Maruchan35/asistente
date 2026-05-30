import json
import urllib.request
import urllib.error
import base64
import io
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"

_ocr_reader = None
def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            # Cargamos modelos español e inglés en CPU para mayor compatibilidad
            _ocr_reader = easyocr.Reader(['es', 'en'], gpu=False)
        except ImportError:
            pass
    return _ocr_reader

def _get_api_keys() -> tuple[str, str]:
    if not API_FILE.exists(): return "", ""
    try:
        data = json.loads(API_FILE.read_text(encoding="utf-8"))
        return data.get("gemini_api_key", ""), data.get("openrouter_api_key", "")
    except: return "", ""

def visual_click(parameters: dict, player=None) -> str:
    """
    Toma una captura de pantalla de todas las pantallas, usa VISIÓN DE LA MATRIX (EasyOCR) para encontrar textos al instante.
    Si falla, usa Gemini (API directa para ultra-baja latencia o OpenRouter como respaldo) para encontrar elementos.
    """
    element_desc = parameters.get("element_description", "")
    if not element_desc:
        return "Error: No se especificó el elemento a cliquear."

    try:
        import mss
        import pyautogui
        import numpy as np
        from PIL import Image
    except ImportError:
        return "Error: Faltan dependencias (mss, pyautogui, numpy, Pillow). Asegúrate de instalarlas."

    if player:
        player.write_log(f"👁 Visión de la Matrix buscando: '{element_desc}'...")

    try:
        with mss.mss() as sct:
            # sct.monitors[0] es la pantalla virtual que unifica todos los monitores activos
            mon = sct.monitors[0]
            sct_img = sct.grab(mon)
            
            # 1. INTENTO LOCAL: VISIÓN DE LA MATRIX (OCR)
            reader = _get_ocr_reader()
            if reader:
                # Convertir a numpy array para EasyOCR
                img_np = np.array(sct_img)[:, :, :3] # BGR format
                results = reader.readtext(img_np)
                
                desc_lower = element_desc.lower()
                desc_words = set(w for w in desc_lower.split() if len(w) > 3)
                
                for bbox, text, prob in results:
                    text_lower = text.lower()
                    text_words = set(w for w in text_lower.split() if len(w) > 3)
                    
                    # Coincidencia directa o coincidencia cruzada de palabras clave
                    if (desc_lower in text_lower or 
                        (len(desc_lower) > 3 and text_lower in desc_lower) or
                        (desc_words and desc_words.issubset(text_words))):
                        
                        # Encontramos coincidencia
                        center_x = int((bbox[0][0] + bbox[2][0]) / 2) + mon["left"]
                        center_y = int((bbox[0][1] + bbox[2][1]) / 2) + mon["top"]
                        
                        pyautogui.moveTo(center_x, center_y, duration=0.2, tween=pyautogui.easeInOutQuad)
                        pyautogui.click()
                        
                        msg = f"Clic visual (Matrix OCR) ejecutado en el texto '{text}' en coordenadas globales: X={center_x}, Y={center_y}."
                        if player: player.write_log(f"✅ {msg}")
                        return msg
                        
            # 2. RESPALDO: VISIÓN EN LA NUBE (GEMINI)
            if player: player.write_log(f"☁️ Elemento no encontrado por OCR local. Analizando escena con Gemini...")
            gemini_key, openrouter_key = _get_api_keys()
            if not gemini_key and not openrouter_key:
                return "Error: No se encontró el texto por OCR y no hay gemini_api_key ni openrouter_api_key configuradas."
                
            orig_w, orig_h = sct_img.size
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            max_size = (1280, 720)
            img.thumbnail(max_size, Image.Resampling.BILINEAR)
            new_w, new_h = img.size
            
            scale_x = orig_w / new_w
            scale_y = orig_h / new_h
            
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=75)
            img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        prompt = (
            f"Encuentra el elemento descrito como '{element_desc}'. "
            "DEBES devolver ÚNICA Y EXCLUSIVAMENTE su bounding box en el formato [ymin, xmin, ymax, xmax] "
            "usando una escala normalizada de 0 a 1000. "
            "Si el elemento no existe, devuelve un array vacío []. Ejemplo: [450, 312, 480, 350]"
        )

        raw_text = ""
        used_provider = ""
        
        # Intentar llamada directa a la API de Gemini para máxima velocidad y baja latencia (gratis)
        if gemini_key:
            used_provider = "Gemini Directo"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": img_b64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "maxOutputTokens": 50,
                    "temperature": 0.1
                }
            }
            headers = {"Content-Type": "application/json"}
            
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                try:
                    raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception as parse_err:
                    return f"Error al parsear respuesta de Gemini Directo: {parse_err}. Respuesta: {response_data}"
        
        # Caer en OpenRouter si no hay clave directa de Gemini
        elif openrouter_key:
            used_provider = "OpenRouter"
            payload = {
                "model": "google/gemini-2.5-flash",
                "max_tokens": 50,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }
                ]
            }
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "HTTP-Referer": "https://github.com/jarvis-beta",
                "Content-Type": "application/json"
            }
            
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    raw_text = response_data["choices"][0]["message"]["content"].strip()
                else:
                    return "Error: Respuesta vacía de OpenRouter."

        # Procesar coordenadas de la IA
        match_bbox = re.search(r"\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]", raw_text)
        match_pixel = re.search(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", raw_text)
        
        if match_bbox:
            ymin, xmin, ymax, xmax = map(int, match_bbox.groups())
            cx_normalized = (xmin + xmax) / 2 / 1000
            cy_normalized = (ymin + ymax) / 2 / 1000
            real_x = int(cx_normalized * orig_w) + mon["left"]
            real_y = int(cy_normalized * orig_h) + mon["top"]
        elif match_pixel:
            coords = json.loads(match_pixel.group(0))
            real_x = int(coords[0] * scale_x) + mon["left"]
            real_y = int(coords[1] * scale_y) + mon["top"]
        else:
            if "[]" in raw_text:
                return f"No se encontró el elemento '{element_desc}' en la pantalla."
            return f"Error al parsear coordenadas de {used_provider}: {raw_text}"
        
        pyautogui.moveTo(real_x, real_y, duration=0.3, tween=pyautogui.easeInOutQuad)
        pyautogui.click()
        
        msg = f"Clic visual ({used_provider}) ejecutado en '{element_desc}' (coordenadas reales: X={real_x}, Y={real_y})."
        if player: player.write_log(f"✅ {msg}")
        return msg

    except Exception as e:
        return f"Error en visual_click: {str(e)}"
