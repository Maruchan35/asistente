# -*- coding: utf-8 -*-
"""
image_generation.py — Genera imágenes a partir de una descripción de texto.

Antes era un STUB vacío que solo decía "Image generated successfully" sin
generar nada. Ahora genera de verdad:
  1. Pollinations.ai (GRATIS, sin API key) — modelo por defecto
  2. Guarda la imagen en Desktop/Imagenes JARVIS/
  3. La abre automáticamente para que el usuario la vea
  4. Opcionalmente la muestra en el holograma de la UI

Uso: image_generation({"prompt": "un gato astronauta en marte, estilo pixar"})
"""
from __future__ import annotations
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

_FOLDER = Path(os.path.expanduser("~")) / "Desktop" / "Imagenes JARVIS"


def _safe_name(text: str) -> str:
    return re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")[:50] or "imagen"


def _download(url: str, dest: Path, timeout: int = 90) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JARVIS"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        # Verificar que sea una imagen real (no un error HTML)
        if len(data) < 1000 or data[:10].lstrip().startswith(b"<"):
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"[ImageGen] descarga falló: {e}")
        return False


def _generate_pollinations(prompt: str, dest: Path, width=1024, height=1024) -> bool:
    """Pollinations.ai — generación gratuita sin API key."""
    # nologo=true quita la marca de agua; seed aleatorio para variedad
    seed = int(time.time()) % 100000
    encoded = urllib.parse.quote(prompt)
    url = (f"https://image.pollinations.ai/prompt/{encoded}"
           f"?width={width}&height={height}&seed={seed}&nologo=true")
    return _download(url, dest)


def image_generation(parameters: dict, player=None) -> str:
    prompt = (parameters.get("prompt") or parameters.get("description")
              or parameters.get("query") or parameters.get("text") or "").strip()
    if not prompt:
        return "¿Qué imagen quieres que genere, señor? Descríbemela."

    # Tamaño opcional — acepta 'size' o 'aspect_ratio' (el declarado)
    size = (parameters.get("size") or parameters.get("aspect_ratio") or "cuadrada").lower()
    dims = {
        "cuadrada": (1024, 1024), "square": (1024, 1024), "1:1": (1024, 1024),
        "horizontal": (1280, 720), "wide": (1280, 720), "16:9": (1280, 720),
        "vertical": (720, 1280), "portrait": (720, 1280), "9:16": (720, 1280),
        "4:3": (1024, 768), "3:4": (768, 1024),
    }
    width, height = dims.get(size, (1024, 1024))

    # Carpeta destino opcional
    _save = (parameters.get("save_path") or "").strip()
    global _FOLDER
    if _save:
        try:
            from actions.document_creator import _resolve_save_dir
            _FOLDER = _resolve_save_dir(_save)
        except Exception:
            pass

    if player:
        try: player.write_log(f"🎨 Generando imagen: {prompt[:50]}...")
        except Exception: pass

    _FOLDER.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = _FOLDER / f"{_safe_name(prompt)}_{stamp}.jpg"

    ok = _generate_pollinations(prompt, dest, width, height)
    if not ok:
        return ("No pude generar la imagen — el servicio no respondió, señor. "
                "Puede ser un problema temporal de red; inténtelo de nuevo.")

    # Abrir la imagen para que el usuario la vea
    try:
        os.startfile(str(dest))
    except Exception:
        pass

    # Mostrarla también en el holograma si hay UI disponible
    try:
        if player and hasattr(player, "_win"):
            import base64
            b64 = base64.b64encode(dest.read_bytes()).decode("ascii")
            html = (f"<div style='padding:8px;text-align:center'>"
                    f"<img src='data:image/jpeg;base64,{b64}' "
                    f"style='max-width:100%;max-height:520px;border-radius:10px'/></div>")
            player._win._holo_sig.emit("", html)
    except Exception:
        pass

    if player:
        try: player.write_log(f"✅ Imagen guardada en {dest}")
        except Exception: pass

    return (f"Imagen generada y guardada en '{dest.name}' (Escritorio/Imagenes JARVIS). "
            "La abrí para que la vea, señor.")
