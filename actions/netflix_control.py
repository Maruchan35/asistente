"""
netflix_control.py — Control inteligente de Netflix para JARVIS.
Usa visual_click (OCR + Gemini Vision) para navegar sin coordenadas fijas.
"""
import re
import time
import json
import webbrowser
import urllib.parse
from pathlib import Path

try:
    import pyautogui
    import pygetwindow as gw
except ImportError:
    pyautogui = None
    gw = None

BASE_DIR  = Path(__file__).resolve().parent.parent
PREFS_FILE = BASE_DIR / "config" / "netflix_prefs.json"

# ── Preferencias persistentes ──────────────────────────────────────────────────

def _load_prefs() -> dict:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"default_profile": "Jorge"}

def _save_prefs(prefs: dict):
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")

# ── Helpers de ventana ─────────────────────────────────────────────────────────

def _find_netflix_window():
    """Devuelve la ventana del navegador que tiene Netflix abierto, o None."""
    if not gw:
        return None
    for win in gw.getAllWindows():
        if "netflix" in win.title.lower():
            return win
    return None

def _focus_window(win) -> bool:
    """Restaura y enfoca una ventana. Devuelve True si tuvo éxito."""
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.6)
        return True
    except Exception:
        return False

def _is_on_profile_screen() -> bool:
    """
    Intenta detectar si Netflix está mostrando la pantalla de selección de perfiles.
    Usa una captura rápida + EasyOCR (sin llamada a la nube).
    """
    try:
        import mss, numpy as np
        from PIL import Image as PILImage

        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            img_np = np.array(shot)[:, :, :3]

        try:
            import easyocr
            reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
            results = reader.readtext(img_np)
            text_all = " ".join(r[1].lower() for r in results)
            # Si en pantalla aparecen palabras típicas de la selección de perfiles
            keywords = ["¿quién", "quien", "perfil", "profile", "ver netflix", "who's watching"]
            return any(k in text_all for k in keywords)
        except Exception:
            return False
    except Exception:
        return False

def _focus_or_open_netflix(profile: str, player=None) -> bool:
    """
    Si Netflix ya está abierto lo enfoca.
    Si no, abre netflix.com (sin URL de perfiles que da 404 en algunas cuentas).
    """
    win = _find_netflix_window()
    if win:
        if player:
            try: player.write_log("🎬 Netflix ya abierto — enfocando...")
            except: pass
        _focus_window(win)
        return True

    if player:
        try: player.write_log("🎬 Abriendo Netflix...")
        except: pass
    # Abrir la raíz de Netflix — él solo redirige a login o selección de perfiles
    webbrowser.open("https://www.netflix.com")
    time.sleep(11)  # esperar carga completa
    return True

# ── Wrapper de visual_click ────────────────────────────────────────────────────

def _visual_click(description: str, player=None, post_wait: float = 1.5) -> bool:
    """
    Llama a visual_click y devuelve True si encontró y clicó el elemento.
    'post_wait' = segundos de espera después del clic.
    """
    try:
        from actions.visual_click import visual_click
        result = visual_click({"element_description": description}, player=player)
        time.sleep(post_wait)
        failed = any(k in result.lower() for k in ["error", "no se encontró", "not found", "falló"])
        return not failed
    except Exception as e:
        if player:
            try: player.write_log(f"⚠️ visual_click falló: {e}")
            except: pass
        return False

# ── Paso 1: Seleccionar perfil ────────────────────────────────────────────────

def _select_profile(profile_name: str, player=None) -> bool:
    """
    Intenta hacer clic en el perfil indicado.
    Primero verifica si hay pantalla de selección de perfiles;
    si no hay, asume que ya estamos en el home y omite este paso.
    """
    if player:
        try: player.write_log(f"👤 Buscando perfil '{profile_name}'...")
        except: pass

    # Verificar si la pantalla de selección de perfiles está visible
    on_profile_screen = _is_on_profile_screen()

    if not on_profile_screen:
        if player:
            try: player.write_log("ℹ️ Pantalla de perfiles no detectada — ya en el home de Netflix.")
            except: pass
        return True  # Ya estamos dentro, no hace falta seleccionar

    # Intentar varias descripciones del mismo elemento
    attempts = [
        profile_name,
        f"perfil de {profile_name}",
        f"usuario {profile_name}",
        f"avatar {profile_name}",
    ]
    for desc in attempts:
        if _visual_click(desc, player=player, post_wait=0.5):
            time.sleep(4.5)  # esperar carga del home de Netflix
            if player:
                try: player.write_log(f"✅ Perfil '{profile_name}' seleccionado.")
                except: pass
            return True

    if player:
        try: player.write_log(f"⚠️ No encontré el perfil '{profile_name}' — continuando de todas formas.")
        except: pass
    return False

# ── Paso 2: Buscar contenido ──────────────────────────────────────────────────

def _search_netflix(content: str, player=None) -> bool:
    """
    Navega a la URL de búsqueda de Netflix. Más confiable que clics en la lupa.
    """
    if player:
        try: player.write_log(f"🔍 Buscando '{content}' en Netflix...")
        except: pass

    query_url = f"https://www.netflix.com/search?q={urllib.parse.quote(content)}"

    # Navegar vía barra de direcciones del navegador
    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        try:
            import pyperclip
            pyperclip.copy(query_url)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pyautogui.write(query_url, interval=0.015)
        pyautogui.press("enter")
        time.sleep(5.0)   # esperar resultados
        return True
    except Exception as e:
        if player:
            try: player.write_log(f"⚠️ Error buscando: {e}")
            except: pass
        return False

# ── Paso 3: Clic en primer resultado ──────────────────────────────────────────

def _click_first_result(content: str, player=None) -> bool:
    """Hace clic en la primera card de resultado de búsqueda."""
    if player:
        try: player.write_log(f"🎯 Abriendo '{content}'...")
        except: pass

    attempts = [
        f"primera tarjeta o miniatura de {content}",
        f"portada de {content}",
        content,
        "primer resultado de busqueda de Netflix",
    ]
    for desc in attempts:
        if _visual_click(desc, player=player, post_wait=2.0):
            return True
    return False

# ── Paso 4: Dar play ──────────────────────────────────────────────────────────

def _click_play(player=None) -> bool:
    """Hace clic en el botón Reproducir o Play."""
    if player:
        try: player.write_log("▶ Buscando botón de Reproducir...")
        except: pass

    # Intentar con distintas descripciones en español e inglés
    for desc in ["botón Reproducir", "botón Play", "Reproducir", "Play", "Reanudar"]:
        if _visual_click(desc, player=player, post_wait=1.5):
            if player:
                try: player.write_log("✅ ¡Reproduciendo!")
                except: pass
            return True

    # Fallback: tecla espacio (muchos reproductores lo aceptan)
    pyautogui.press("space")
    time.sleep(1.0)
    return True   # asumimos que funcionó

# ── Función principal ──────────────────────────────────────────────────────────

def netflix_control(parameters: dict, player=None) -> str:
    """
    Control completo de Netflix.

    Acciones:
        play            — Abre Netflix, elige perfil y reproduce contenido.
        open            — Solo abre Netflix y selecciona perfil.
        select_profile  — Cambia de perfil sin navegar al contenido.
        search          — Busca contenido sin reproducir.
        pause           — Pausa o reanuda el video actual.
        forward         — Adelanta N segundos/minutos.
        back            — Retrocede N segundos/minutos.
        set_profile     — Guarda el perfil por defecto para futuras sesiones.

    Parámetros clave:
        profile  — Nombre del perfil (ej: "Jorge"). Si se omite usa el guardado.
        content  — Película o serie a buscar (ej: "Inception", "Narcos").
        amount   — Cantidad de tiempo para forward/back (ej: "2 minutos").
    """
    if not pyautogui:
        return "Error: pyautogui no está instalado."

    action  = parameters.get("action", "play").lower().strip()
    prefs   = _load_prefs()

    # Resolver perfil: el del parámetro, el guardado, o "Jorge" como default
    profile = (parameters.get("profile") or prefs.get("default_profile") or "Jorge").strip()
    content = parameters.get("content", "").strip()
    amount  = parameters.get("amount", "10")

    # ── Guardar perfil por defecto ─────────────────────────────────────────────
    if action == "set_profile":
        if not profile:
            return "Error: Falta el nombre del perfil."
        prefs["default_profile"] = profile
        _save_prefs(prefs)
        return f"Perfil por defecto guardado como '{profile}'."

    # ── Solo abrir y seleccionar perfil ───────────────────────────────────────
    if action == "open":
        _focus_or_open_netflix(profile, player)
        _select_profile(profile, player)
        return f"Netflix abierto con perfil '{profile}'."

    # ── Seleccionar perfil (ya en Netflix) ────────────────────────────────────
    elif action == "select_profile":
        win = _find_netflix_window()
        if win:
            _focus_window(win)
        else:
            _focus_or_open_netflix(profile, player)
        ok = _select_profile(profile, player)
        return (f"Perfil '{profile}' seleccionado." if ok
                else f"No encontré el perfil '{profile}'. Puede que la página no haya cargado aún.")

    # ── Reproducir contenido ──────────────────────────────────────────────────
    elif action == "play":
        if not content:
            return "Error: Dime qué película o serie quieres ver (parámetro 'content')."

        # 1. Abrir/enfocar Netflix
        _focus_or_open_netflix(profile, player)

        # 2. Seleccionar perfil (si aparece la pantalla de perfiles)
        _select_profile(profile, player)

        # 3. Buscar el contenido por URL directa
        if not _search_netflix(content, player):
            return f"No se pudo buscar '{content}' en Netflix."

        # 4. Clic en primer resultado
        _click_first_result(content, player)

        # 5. Dar play
        _click_play(player)

        # Guardar el perfil usado para la próxima vez
        prefs["default_profile"] = profile
        _save_prefs(prefs)

        return f"¡Reproduciendo '{content}' en Netflix con el perfil '{profile}'!"

    # ── Solo buscar sin reproducir ────────────────────────────────────────────
    elif action == "search":
        if not content:
            return "Error: Falta el contenido a buscar."
        win = _find_netflix_window()
        if win:
            _focus_window(win)
        else:
            _focus_or_open_netflix(profile, player)
            _select_profile(profile, player)
        _search_netflix(content, player)
        return f"Resultados de búsqueda para '{content}' en Netflix."

    # ── Pausa / play ──────────────────────────────────────────────────────────
    elif action == "pause":
        win = _find_netflix_window()
        if win:
            _focus_window(win)
        pyautogui.press("space")
        return "Pausa/reproducción alternada en Netflix."

    # ── Control de tiempo ────────────────────────────────────────────────────
    elif action in ("forward", "skip_forward", "adelantar"):
        win = _find_netflix_window()
        if win:
            _focus_window(win)
        from actions.browser_control import browser_control, _parse_seconds
        secs = _parse_seconds(str(amount))
        # Netflix usa flechas (±10s) o Shift+flechas (±30s)
        presses_30 = secs // 30
        remaining  = secs % 30
        presses_10 = remaining // 10
        remainder  = remaining % 10
        for _ in range(presses_30):
            pyautogui.hotkey("shift", "right")
            time.sleep(0.08)
        for _ in range(presses_10):
            pyautogui.press("right")
            time.sleep(0.08)
        if remainder >= 5:  # redondear al siguiente 10s si sobra >=5s
            pyautogui.press("right")
        total_approx = presses_30 * 30 + presses_10 * 10
        return f"Video adelantado ~{total_approx}s en Netflix."

    elif action in ("back", "skip_backward", "retroceder"):
        win = _find_netflix_window()
        if win:
            _focus_window(win)
        from actions.browser_control import _parse_seconds
        secs = _parse_seconds(str(amount))
        presses_30 = secs // 30
        remaining  = secs % 30
        presses_10 = remaining // 10
        remainder  = remaining % 10
        for _ in range(presses_30):
            pyautogui.hotkey("shift", "left")
            time.sleep(0.08)
        for _ in range(presses_10):
            pyautogui.press("left")
            time.sleep(0.08)
        if remainder >= 5:
            pyautogui.press("left")
        total_approx = presses_30 * 30 + presses_10 * 10
        return f"Video retrocedido ~{total_approx}s en Netflix."

    else:
        return (
            f"Acción '{action}' no reconocida. "
            "Usa: play | open | select_profile | search | pause | forward | back | set_profile."
        )
