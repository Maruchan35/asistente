def computer_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower()
    
    if action == "take_screenshot":
        try:
            import os
            import time
            from PIL import ImageGrab
            
            save_dir = os.path.join(os.path.dirname(__file__), "..", "config")
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"screenshot_{int(time.time())}.png")
            
            screen_pref = str(parameters.get("screen", "combined")).lower()
            
            try:
                import mss
                from PIL import Image
                with mss.mss() as sct:
                    # sct.monitors[0] es la combinada.
                    # sct.monitors[1:] son los monitores individuales, pero pueden estar desordenados.
                    # Los ordenamos por su posición horizontal (coordenada 'left') para que
                    # actual_monitors[0] sea físicamente la Pantalla 1 (Izquierda) y actual_monitors[1] la Pantalla 2 (Derecha).
                    actual_monitors = sorted(sct.monitors[1:], key=lambda m: m["left"])
                    
                    if "1" in screen_pref and len(actual_monitors) >= 1:
                        sct_img = sct.grab(actual_monitors[0])
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    elif "2" in screen_pref and len(actual_monitors) >= 2:
                        sct_img = sct.grab(actual_monitors[1])
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    else:
                        sct_img = sct.grab(sct.monitors[0])
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception as e:
                # Fallback en caso de que mss falle
                from PIL import ImageGrab
                img = ImageGrab.grab(all_screens=True)
                
            img.save(path)
            if player: player.write_log(f"📸 Captura de pantalla tomada: {path}")
            return f"SCREENSHOT_SAVED:{path}"
        except Exception as e:
            return f"Error tomando captura: {e}"
            
    if action == "media_control":
        sub_action = parameters.get("sub_action", "").lower()
        try:
            import pyautogui
            if sub_action == "play_pause" or sub_action == "play" or sub_action == "pause":
                pyautogui.press('playpause')
                msg = "Reproducción/Pausa ejecutada."
            elif sub_action == "next" or sub_action == "next_track":
                pyautogui.press('nexttrack')
                msg = "Siguiente pista ejecutada."
            elif sub_action == "prev" or sub_action == "prev_track":
                pyautogui.press('prevtrack')
                msg = "Pista anterior ejecutada."
            elif sub_action == "mute":
                pyautogui.press('volumemute')
                msg = "Silencio/Sonido alternado."
            elif sub_action == "volume_up":
                pyautogui.press('volumeup', presses=5)
                msg = "Volumen subido."
            elif sub_action == "volume_down":
                pyautogui.press('volumedown', presses=5)
                msg = "Volumen bajado."
            else:
                return f"Comando multimedia desconocido: {sub_action}"
                
            if player: player.write_log(f"🎵 {msg}")
            return msg
        except Exception as e:
            return f"Error en control multimedia: {e}"

    if action == "type":
        text_to_type = parameters.get("text", "")
        if not text_to_type:
            return "Error: Falta el texto a escribir."
            
        try:
            import pyautogui
            import time
            time.sleep(0.5) # Pausa para que el usuario pueda poner el foco si lo necesita
            pyautogui.write(text_to_type, interval=0.01)
            msg = f"Texto escrito: '{text_to_type}'"
            if player: player.write_log(f"⌨️ {msg}")
            return msg
        except Exception as e:
            return f"Error escribiendo texto: {e}"
            
    if action == "seek" or "adelantar" in str(parameters).lower() or "retroceder" in str(parameters).lower() or parameters.get("sub_action") == "seek":
        try:
            import pyautogui
            import time
            import re
            
            # Extraer los segundos de los parámetros
            params_str = str(parameters).lower()
            
            # Intentar obtenerlo directamente del parámetro 'seconds'
            seconds = 10
            sec_param = parameters.get("seconds")
            if sec_param:
                # Extraer solo los números del parámetro seconds si viene con texto
                nums = re.findall(r'\d+', str(sec_param))
                if nums:
                    seconds = int(nums[0])
            else:
                # Fallback al regex original
                match = re.search(r'(\d+)\s*(segundos|s|seconds)', params_str)
                seconds = int(match.group(1)) if match else 10
            
            # YouTube y la mayoría de reproductores web usan flechas para saltar 5 segundos
            presses = max(1, seconds // 5)
            
            key = 'right' if "adelanta" in params_str or "forward" in params_str or action == "seek_forward" or "1" in str(sec_param) else 'left'
            if "retrocede" in params_str or "back" in params_str or (isinstance(sec_param, str) and "-" in sec_param):
                key = 'left'
            
            # Hacemos los saltos rápidamente
            pyautogui.press(key, presses=presses, interval=0.05)
            
            msg = f"Video adelantado/retrocedido {seconds} segundos (enviado {presses} pulsaciones de {key})."
            if player: player.write_log(f"⏩ {msg}")
            return msg
        except Exception as e:
            return f"Error en control de video: {e}"
            
    if action == "window_control":
        sub_action = parameters.get("sub_action", "").lower()
        target = parameters.get("target", "").lower()
        
        try:
            import pygetwindow as gw
            import pyautogui
            import time
            
            # Find target window (case-insensitive substring match)
            if target:
                windows = [w for w in gw.getAllWindows() if target in w.title.lower() and w.title.strip()]
            else:
                windows = [gw.getActiveWindow()]
                
            if not windows or not windows[0]:
                return f"No se encontró ninguna ventana con el nombre '{target}'."
                
            win = windows[0]
            
            if sub_action == "close_tab":
                win.activate()
                time.sleep(0.2)
                pyautogui.hotkey('ctrl', 'w')
                msg = f"Pestaña cerrada en {win.title}."
                if player: player.write_log(f"🪟 {msg}")
                return msg
                
            if sub_action == "close":
                win.close()
                msg = f"Ventana cerrada: {win.title}."
                if player: player.write_log(f"🪟 {msg}")
                return msg
                
            if sub_action == "minimize":
                win.minimize()
                msg = f"Ventana minimizada: {win.title}."
                if player: player.write_log(f"🪟 {msg}")
                return msg
                
            if sub_action == "maximize":
                if win.isMinimized:
                    win.restore()
                win.maximize()
                win.activate()
                msg = f"Ventana maximizada: {win.title}."
                if player: player.write_log(f"🪟 {msg}")
                return msg
                
            if sub_action == "move_monitor":
                if win.isMinimized:
                    win.restore()
                    time.sleep(0.5)
                
                try:
                    import win32gui
                    import win32api
                    hwnd = win._hWnd
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    width = right - left
                    height = bottom - top
                    
                    monitors = win32api.EnumDisplayMonitors()
                    if len(monitors) > 1:
                        center_x = left + width // 2
                        current_monitor = None
                        target_monitor = None
                        
                        for mon in monitors:
                            m_left, m_top, m_right, m_bottom = mon[2]
                            if m_left <= center_x <= m_right:
                                current_monitor = mon[2]
                                
                        for mon in monitors:
                            if mon[2] != current_monitor:
                                target_monitor = mon[2]
                                break
                                
                        if target_monitor:
                            t_left, t_top, t_right, t_bottom = target_monitor
                            new_x = t_left + max(0, left - (current_monitor[0] if current_monitor else 0))
                            new_y = t_top + max(0, top - (current_monitor[1] if current_monitor else 0))
                            
                            # Si es muy grande, ajustamos al monitor
                            mw = t_right - t_left
                            mh = t_bottom - t_top
                            new_width = min(width, mw)
                            new_height = min(height, mh)
                            
                            win32gui.SetWindowPos(hwnd, 0, new_x, new_y, new_width, new_height, 0x0040)
                            
                except Exception as e:
                    print(f"Native move failed: {e}")
                    # Fallback
                    try:
                        win.activate()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    pyautogui.hotkey('win', 'shift', 'right')
                msg = f"Ventana '{win.title}' movida al otro monitor."
                if player: player.write_log(f"🪟 {msg}")
                return msg
                
        except Exception as e:
            return f"Error en control de ventanas: {e}"

    return f"Computer control action '{action}' executed successfully."
