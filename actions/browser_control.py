import re
import time
import pyautogui
import pygetwindow as gw

# ── Helpers ────────────────────────────────────────────────────────────────────

def _focus_browser():
    """Encuentra y enfoca el navegador activo. Devuelve la ventana o None."""
    browser_keywords = ["Chrome", "Edge", "Firefox", "Brave", "Opera"]
    for win in gw.getAllWindows():
        if win.title.strip():
            for kw in browser_keywords:
                if kw.lower() in win.title.lower():
                    try:
                        if win.isMinimized:
                            win.restore()
                        win.activate()
                        time.sleep(0.3)
                    except Exception:
                        pass
                    return win
    return None

def _is_youtube(win) -> bool:
    """Devuelve True si la ventana activa es YouTube."""
    if not win:
        return False
    return "youtube" in win.title.lower()

def _parse_seconds(amount_str: str) -> int:
    """
    Convierte texto a segundos.
    Entiende: 'un minuto', '2 minutos 30 segundos', '45s', '90', etc.
    """
    if not amount_str:
        return 10

    s = amount_str.lower().strip()

    # Palabras numéricas en español
    word_nums = {
        "un": 1, "uno": 1, "una": 1,
        "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
        "diez": 10, "once": 11, "doce": 12, "trece": 13,
        "catorce": 14, "quince": 15, "veinte": 20,
        "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
        "noventa": 90, "cien": 100,
    }
    for word, num in word_nums.items():
        s = re.sub(r'\b' + word + r'\b', str(num), s)

    total = 0

    # Horas
    hr = re.search(r'(\d+(?:\.\d+)?)\s*(?:hora[s]?|hr[s]?)\b', s)
    if hr:
        total += int(float(hr.group(1)) * 3600)

    # Minutos
    mn = re.search(r'(\d+(?:\.\d+)?)\s*(?:minuto[s]?|min\b)', s)
    if mn:
        total += int(float(mn.group(1)) * 60)

    # Segundos
    sc = re.search(r'(\d+(?:\.\d+)?)\s*(?:segundo[s]?|seg\b|s\b)', s)
    if sc:
        total += int(float(sc.group(1)))

    # Solo un número suelto → asumir segundos
    if total == 0:
        nm = re.search(r'(\d+)', s)
        if nm:
            total = int(nm.group(1))

    return max(total, 1)

def _inject_js(js: str, win=None) -> bool:
    """
    Inyecta JavaScript en el navegador activo usando la consola de desarrollador
    (Ctrl+Shift+J en Chrome/Brave/Edge, Ctrl+Shift+K en Firefox).
    Devuelve True si el proceso se completó sin error.
    """
    try:
        import pyperclip
        pyperclip.copy(js)
    except Exception:
        # Sin pyperclip: escribir directamente (puede fallar con caracteres especiales)
        pass

    # Detectar si es Firefox
    is_firefox = win and "firefox" in win.title.lower()

    try:
        if is_firefox:
            pyautogui.hotkey("ctrl", "shift", "k")
        else:
            pyautogui.hotkey("ctrl", "shift", "j")
        time.sleep(0.8)

        # Limpiar y pegar el JS
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)

        try:
            import pyperclip
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pyautogui.write(js, interval=0.02)

        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.5)

        # Cerrar consola
        if is_firefox:
            pyautogui.hotkey("ctrl", "shift", "k")
        else:
            pyautogui.hotkey("ctrl", "shift", "j")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"[BrowserControl] Error inyectando JS: {e}")
        return False


# ── Función principal ──────────────────────────────────────────────────────────

def browser_control(parameters: dict, player=None) -> str:
    """
    Controla el navegador activo: navegación, pestañas, scroll y CONTROL MULTIMEDIA.

    Acciones de navegación:
        go_to | search | new_tab | close_tab | scroll

    Acciones multimedia (video/audio en el navegador):
        media_skip_forward   — adelanta N segundos/minutos
        media_skip_backward  — retrocede N segundos/minutos
        media_play_pause     — reproducir / pausar
        media_mute           — silenciar / activar sonido
        media_fullscreen     — pantalla completa / salir
        media_speed_up       — aumentar velocidad de reproducción
        media_speed_down     — reducir velocidad de reproducción
        media_restart        — reiniciar el video desde el inicio
        media_volume_up      — subir volumen del video
        media_volume_down    — bajar volumen del video
    """
    action = parameters.get("action", "").lower().strip()

    # ── Alias naturales ────────────────────────────────────────────────────────
    _aliases = {
        # adelantar
        "adelantar": "media_skip_forward",
        "adelanta":  "media_skip_forward",
        "forward":   "media_skip_forward",
        "skip":      "media_skip_forward",
        "avanzar":   "media_skip_forward",
        # retroceder
        "retroceder":  "media_skip_backward",
        "retrocede":   "media_skip_backward",
        "backward":    "media_skip_backward",
        "rewind":      "media_skip_backward",
        "atrás":       "media_skip_backward",
        "atras":       "media_skip_backward",
        # play/pause
        "pausar":      "media_play_pause",
        "pausa":       "media_play_pause",
        "reproducir":  "media_play_pause",
        "play":        "media_play_pause",
        "pause":       "media_play_pause",
        # mute
        "silenciar":   "media_mute",
        "mute":        "media_mute",
        # fullscreen
        "pantalla_completa": "media_fullscreen",
        "fullscreen":        "media_fullscreen",
        # velocidad
        "mas_rapido":  "media_speed_up",
        "más rápido":  "media_speed_up",
        "mas lento":   "media_speed_down",
        "más lento":   "media_speed_down",
        # reiniciar
        "reiniciar":   "media_restart",
        "restart":     "media_restart",
    }
    action = _aliases.get(action, action)

    # ── Encontrar navegador ────────────────────────────────────────────────────
    win = _focus_browser()

    # ══════════════════════════════════════════════════════════════════════════
    # CONTROL MULTIMEDIA
    # ══════════════════════════════════════════════════════════════════════════

    if action == "media_skip_forward":
        amount_str = parameters.get("amount", parameters.get("seconds", "10"))
        if isinstance(amount_str, (int, float)):
            seconds = int(amount_str)
        else:
            seconds = _parse_seconds(str(amount_str))

        if player:
            try: player.write_log(f"⏩ Adelantando {seconds}s en el video...")
            except Exception: pass

        if _is_youtube(win):
            # En YouTube: L adelanta 10s
            presses = max(1, round(seconds / 10))
            for _ in range(presses):
                pyautogui.press("l")
                time.sleep(0.05)
            actual = presses * 10
            return f"Video adelantado ~{actual} segundos en YouTube."
        else:
            # Sitio genérico: inyectar JS
            js = f"var v=document.querySelector('video');if(v){{v.currentTime+={seconds};console.log('skip+{seconds}');}}"
            ok = _inject_js(js, win)
            if ok:
                return f"Video adelantado {seconds} segundos."
            # Fallback: flecha derecha (±5s en la mayoría de sitios)
            presses = max(1, round(seconds / 5))
            for _ in range(presses):
                pyautogui.press("right")
                time.sleep(0.05)
            return f"Video adelantado ~{presses * 5} segundos (teclado)."

    elif action == "media_skip_backward":
        amount_str = parameters.get("amount", parameters.get("seconds", "10"))
        if isinstance(amount_str, (int, float)):
            seconds = int(amount_str)
        else:
            seconds = _parse_seconds(str(amount_str))

        if player:
            try: player.write_log(f"⏪ Retrocediendo {seconds}s en el video...")
            except Exception: pass

        if _is_youtube(win):
            presses = max(1, round(seconds / 10))
            for _ in range(presses):
                pyautogui.press("j")
                time.sleep(0.05)
            actual = presses * 10
            return f"Video retrocedido ~{actual} segundos en YouTube."
        else:
            js = f"var v=document.querySelector('video');if(v){{v.currentTime-={seconds};console.log('skip-{seconds}');}}"
            ok = _inject_js(js, win)
            if ok:
                return f"Video retrocedido {seconds} segundos."
            presses = max(1, round(seconds / 5))
            for _ in range(presses):
                pyautogui.press("left")
                time.sleep(0.05)
            return f"Video retrocedido ~{presses * 5} segundos (teclado)."

    elif action == "media_play_pause":
        if player:
            try: player.write_log("⏯ Play/Pause...")
            except Exception: pass
        if _is_youtube(win):
            pyautogui.press("k")
        else:
            # Space funciona en la mayoría de reproductores
            pyautogui.press("space")
        return "Play/Pause ejecutado."

    elif action == "media_mute":
        if player:
            try: player.write_log("🔇 Mute/Unmute...")
            except Exception: pass
        if _is_youtube(win):
            pyautogui.press("m")
        else:
            js = "var v=document.querySelector('video');if(v){v.muted=!v.muted;}"
            _inject_js(js, win)
        return "Silencio/audio activado."

    elif action == "media_fullscreen":
        if player:
            try: player.write_log("🔲 Pantalla completa...")
            except Exception: pass
        if _is_youtube(win):
            pyautogui.press("f")
        else:
            js = (
                "var v=document.querySelector('video');"
                "if(v){"
                "  if(!document.fullscreenElement){v.requestFullscreen();}"
                "  else{document.exitFullscreen();}"
                "}"
            )
            _inject_js(js, win)
        return "Pantalla completa activada/desactivada."

    elif action == "media_speed_up":
        if _is_youtube(win):
            pyautogui.press(">")
        else:
            js = "var v=document.querySelector('video');if(v){v.playbackRate=Math.min(v.playbackRate+0.25,3.0);}"
            _inject_js(js, win)
        return "Velocidad de reproducción aumentada."

    elif action == "media_speed_down":
        if _is_youtube(win):
            pyautogui.press("<")
        else:
            js = "var v=document.querySelector('video');if(v){v.playbackRate=Math.max(v.playbackRate-0.25,0.25);}"
            _inject_js(js, win)
        return "Velocidad de reproducción reducida."

    elif action == "media_restart":
        if _is_youtube(win):
            pyautogui.press("0")
        else:
            js = "var v=document.querySelector('video');if(v){v.currentTime=0;v.play();}"
            _inject_js(js, win)
        return "Video reiniciado desde el inicio."

    elif action == "media_volume_up":
        if _is_youtube(win):
            for _ in range(2):
                pyautogui.press("up")
                time.sleep(0.05)
        else:
            js = "var v=document.querySelector('video');if(v){v.volume=Math.min(v.volume+0.1,1.0);}"
            _inject_js(js, win)
        return "Volumen del video subido."

    elif action == "media_volume_down":
        if _is_youtube(win):
            for _ in range(2):
                pyautogui.press("down")
                time.sleep(0.05)
        else:
            js = "var v=document.querySelector('video');if(v){v.volume=Math.max(v.volume-0.1,0.0);}"
            _inject_js(js, win)
        return "Volumen del video bajado."

    # ══════════════════════════════════════════════════════════════════════════
    # NAVEGACIÓN WEB
    # ══════════════════════════════════════════════════════════════════════════

    if not win:
        return "No se encontró ningún navegador (Chrome, Edge, Firefox, Brave) abierto."

    try:
        if action == "go_to":
            url = parameters.get("url", "")
            if not url:
                return "Error: Falta la URL."
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.05)
            pyautogui.write(url, interval=0.005)
            pyautogui.press("enter")
            return f"Navegando a {url}."

        elif action == "search":
            query = parameters.get("query", "")
            if not query:
                return "Error: Falta la búsqueda (query)."
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.05)
            pyautogui.write(query, interval=0.005)
            pyautogui.press("enter")
            return f"Buscando '{query}'."

        elif action == "new_tab":
            url = parameters.get("url", "")
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.3)
            if url:
                pyautogui.write(url, interval=0.01)
                pyautogui.press("enter")
                return f"Nueva pestaña abierta → {url}."
            return "Nueva pestaña abierta."

        elif action == "close_tab":
            pyautogui.hotkey("ctrl", "w")
            return "Pestaña cerrada."

        elif action == "scroll":
            direction = parameters.get("direction", "down")
            if direction == "down":
                pyautogui.press("pgdn")
            else:
                pyautogui.press("pgup")
            return f"Scroll hacia {direction}."

        else:
            return (
                f"Acción '{action}' no reconocida. "
                "Navegación: go_to | search | new_tab | close_tab | scroll. "
                "Multimedia: media_skip_forward | media_skip_backward | media_play_pause | "
                "media_mute | media_fullscreen | media_speed_up | media_speed_down | "
                "media_restart | media_volume_up | media_volume_down."
            )

    except Exception as e:
        return f"Error controlando el navegador: {e}"
