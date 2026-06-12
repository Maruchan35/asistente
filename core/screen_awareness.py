"""
core/screen_awareness.py — Conciencia de pantalla proactiva.

Observa periódicamente lo que el usuario hace y ofrece ayuda cuando detecta
situaciones donde JARVIS puede aportar:
  • Error de compilación/stacktrace visible un buen rato → ofrece ayuda
  • Diálogo de error de Windows → ofrece resolverlo
  • Misma pantalla "atascada" mucho tiempo (posible bloqueo)

A diferencia de pair_programming (enfocado en código y silencioso en el panel),
esto es awareness general y PUEDE hablar (con moderación) — pero respeta:
  • nivel de autonomía (solo activo en nivel 2+)
  • focus mode y kill switch
  • cuota: usa OCR local cuando puede; intervalo largo (45s); solo consulta
    visión Gemini si el OCR detecta señales de problema
  • anti-spam: máximo 1 ofrecimiento cada 5 min, no repite el mismo

Es OPT-IN: se activa con "modo atento" / "vigila mi pantalla" / awareness on.
"""
from __future__ import annotations
import hashlib
import re
import threading
import time

_active = False
_thread = None
_stop = threading.Event()
_speak_cb = None

_INTERVAL_S = 45
_last_offer_ts = 0.0
_OFFER_COOLDOWN = 300        # 5 min entre ofrecimientos
_last_signature = ""

# Señales de problema detectables por OCR (texto plano, sin gastar visión)
_PROBLEM_PATTERNS = [
    r"\btraceback\b", r"\berror\b", r"\bexception\b", r"\bfailed\b",
    r"\bno such file\b", r"\bsyntaxerror\b", r"\bsegmentation fault\b",
    r"\bcannot find\b", r"\bundefined\b", r"\bfatal\b", r"\bdenied\b",
    r"\bno se puede\b", r"\bno encontrado\b", r"\bha dejado de funcionar\b",
]
_PROBLEM_RE = re.compile("|".join(_PROBLEM_PATTERNS), re.IGNORECASE)


def _capture_bytes() -> bytes | None:
    try:
        import mss
        import io
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=60)
            return buf.getvalue()
    except Exception:
        return None


def _analyze_local(img_bytes: bytes) -> tuple[str, bool]:
    """OCR local → (texto, hay_problema). Sin OCR devuelve ('', False)."""
    try:
        from core.vision_cache import ocr_image
        text = ocr_image(img_bytes) or ""
        return text, bool(_PROBLEM_RE.search(text))
    except Exception:
        return "", False


def _loop():
    global _last_offer_ts, _last_signature
    while _active and not _stop.is_set():
        try:
            from core.autonomy import is_killed, get_level
            from core.focus_mode import is_active as focus_on

            if is_killed() or get_level() < 2 or focus_on():
                _stop.wait(_INTERVAL_S)
                continue

            now = time.time()
            if (now - _last_offer_ts) < _OFFER_COOLDOWN:
                _stop.wait(_INTERVAL_S)
                continue

            img = _capture_bytes()
            if img is None:
                _stop.wait(_INTERVAL_S)
                continue

            # 1. OCR local primero (gratis). Solo si detecta problema seguimos.
            text, has_problem = _analyze_local(img)

            if has_problem:
                sig = hashlib.md5(text[:200].encode()).hexdigest()[:12]
                if sig == _last_signature:
                    _stop.wait(_INTERVAL_S)   # mismo problema ya ofrecido
                    continue
                _last_signature = sig
                _last_offer_ts = now
                # Extraer la línea de error más relevante
                err_line = ""
                for line in text.split("\n"):
                    if _PROBLEM_RE.search(line):
                        err_line = line.strip()[:120]
                        break
                if _speak_cb:
                    _speak_cb(
                        f"(AWARENESS DE PANTALLA: detecté un posible error en pantalla "
                        f"('{err_line}'). Ofrece ayuda al usuario de forma breve y natural, "
                        "solo una vez. Si acepta, usa screen_vision para analizarlo a fondo.)"
                    )
                try:
                    from core.autonomy import audit
                    audit("screen_awareness", f"Posible error detectado: {err_line[:80]}", "ofrecido")
                except Exception:
                    pass
        except Exception:
            pass
        _stop.wait(_INTERVAL_S)


def start(speak=None, interval_s: int = 45) -> str:
    global _active, _thread, _speak_cb, _INTERVAL_S
    if _active:
        return "El modo atento ya está activo."
    # Requiere OCR local para no quemar cuota
    try:
        from core.vision_cache import _get_ocr
        if not _get_ocr():
            return ("El modo atento necesita OCR local (Tesseract) para no gastar "
                    "cuota de visión. Instálalo o usa pair_programming en su lugar.")
    except Exception:
        pass
    _INTERVAL_S = max(20, interval_s)
    _speak_cb = speak
    _stop.clear()
    _active = True
    _thread = threading.Thread(target=_loop, daemon=True, name="ScreenAwareness")
    _thread.start()
    try:
        from core.autonomy import audit
        audit("screen_awareness", f"Modo atento activado (cada {_INTERVAL_S}s)", "")
    except Exception:
        pass
    return (f"Modo atento activado. Observaré tu pantalla cada {_INTERVAL_S}s y te "
            "ofreceré ayuda si detecto algún error, sin interrumpir de más.")


def stop() -> str:
    global _active
    if not _active:
        return "El modo atento no estaba activo."
    _active = False
    _stop.set()
    return "Modo atento desactivado."


def is_running() -> bool:
    return _active


def screen_awareness(parameters: dict, player=None) -> str:
    """Entry point. action: start | stop | status"""
    action = (parameters.get("action") or "start").lower()
    if action in ("stop", "off"):
        return stop()
    if action == "status":
        return "Modo atento ACTIVO" if is_running() else "Modo atento inactivo"
    speak = getattr(player, "speak", None) if player else None
    return start(speak=speak, interval_s=int(parameters.get("interval_s", 45)))
