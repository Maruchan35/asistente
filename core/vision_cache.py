"""
core/vision_cache.py — Reducir consumo de cuota de Gemini en visión.

Dos optimizaciones:
  1. CACHE por hash de imagen: si se pregunta lo mismo sobre una pantalla que
     no cambió, devolver la respuesta cacheada (TTL corto) sin gastar cuota.
  2. OCR LOCAL: cuando solo se necesita TEXTO plano de la pantalla (no
     interpretación), usar Tesseract/easyocr si están instalados, gratis,
     en vez de la visión multimodal de Gemini.

Ambas son best-effort: si no hay OCR o el cache no aplica, se cae al
comportamiento normal (visión Gemini). Cero impacto si las libs no están.
"""
from __future__ import annotations
import hashlib
import time

# ── Cache en memoria ──────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, str]] = {}   # key -> (ts, respuesta)
_TTL_S = 8.0          # respuestas válidas 8s (la pantalla cambia rápido)
_MAX_ENTRIES = 50


def _img_hash(img_bytes: bytes) -> str:
    return hashlib.md5(img_bytes).hexdigest()[:16]


def cache_key(img_bytes: bytes, question: str) -> str:
    return f"{_img_hash(img_bytes)}:{hashlib.md5(question.encode()).hexdigest()[:8]}"


def get_cached(img_bytes: bytes, question: str) -> str | None:
    key = cache_key(img_bytes, question)
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < _TTL_S:
        return hit[1]
    return None


def put_cache(img_bytes: bytes, question: str, answer: str) -> None:
    if len(_cache) > _MAX_ENTRIES:
        # Limpiar las más viejas
        old = sorted(_cache.items(), key=lambda kv: kv[1][0])[:20]
        for k, _ in old:
            _cache.pop(k, None)
    _cache[cache_key(img_bytes, question)] = (time.time(), answer)


# ── OCR local ─────────────────────────────────────────────────────────────────

_ocr_engine = None        # None = no probado | False = no disponible | callable
_TEXT_ONLY_HINTS = (
    "extrae el texto", "extract text", "qué texto", "que texto", "transcribe",
    "lee el texto", "read the text", "copia el texto", "ocr",
)


def is_text_only_query(question: str) -> bool:
    """¿La pregunta solo necesita texto plano (no interpretación visual)?"""
    q = question.lower()
    return any(h in q for h in _TEXT_ONLY_HINTS)


def _get_ocr():
    """Lazy-init del motor OCR. Prueba pytesseract → easyocr → None."""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    # pytesseract (requiere Tesseract instalado en el sistema)
    try:
        import pytesseract
        from PIL import Image
        # Verificar que el binario existe
        pytesseract.get_tesseract_version()

        def _run(img_bytes: bytes) -> str:
            import io
            return pytesseract.image_to_string(
                Image.open(io.BytesIO(img_bytes)), lang="spa+eng")
        _ocr_engine = _run
        return _ocr_engine
    except Exception:
        pass
    # easyocr (pesado pero no requiere binario externo)
    try:
        import easyocr
        import numpy as np
        from PIL import Image
        _reader = easyocr.Reader(["es", "en"], gpu=False)

        def _run2(img_bytes: bytes) -> str:
            import io
            arr = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
            return "\n".join(_reader.readtext(arr, detail=0))
        _ocr_engine = _run2
        return _ocr_engine
    except Exception:
        _ocr_engine = False
        return False


def ocr_image(img_bytes: bytes) -> str | None:
    """Extraer texto de una imagen con OCR local. None si no hay motor."""
    engine = _get_ocr()
    if not engine:
        return None
    try:
        text = engine(img_bytes).strip()
        return text if text else None
    except Exception:
        return None


def get_stats() -> dict:
    return {
        "cache_entries": len(_cache),
        "ocr_available": bool(_get_ocr()),
    }
