"""app_macro.py - Automated UI macros for specific applications (e.g. MS Word, Excel)."""

def app_macro(parameters: dict, player=None) -> str:
    app = parameters.get("app", "").lower().strip()
    action = parameters.get("action", "").lower().strip()
    
    if not app or not action:
        return "Error: Faltan parámetros 'app' o 'action' para la macro."
        
    try:
        import pyautogui
        import pygetwindow as gw
        import time
        
        # Encontrar y enfocar la aplicación destino
        target_name = ""
        if "word" in app:
            target_name = "Word"
        elif "excel" in app:
            target_name = "Excel"
        elif "powerpoint" in app:
            target_name = "PowerPoint"
        else:
            target_name = app
            
        windows = gw.getWindowsWithTitle(target_name)
        if not windows:
            return f"Error: No se encontró la aplicación '{target_name}' abierta. Ábrela primero."
            
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.5) # Esperar a que la ventana obtenga el foco
        
        # MACROS DE MICROSOFT WORD / OFFICE
        if target_name in ("Word", "Excel", "PowerPoint"):
            if action == "change_font":
                font_name = parameters.get("font_name", "").strip()
                font_size = parameters.get("font_size", "").strip()
                
                msg_parts = []
                
                # Intentar usar COM Object nativo (Instantáneo y sin errores de atajos)
                com_success = False
                if target_name == "Word":
                    try:
                        import win32com.client
                        word = win32com.client.GetActiveObject("Word.Application")
                        sel = word.Selection
                        if font_name:
                            sel.Font.Name = font_name
                            msg_parts.append(f"fuente '{font_name}'")
                        if font_size:
                            sel.Font.Size = int(font_size)
                            msg_parts.append(f"tamaño '{font_size}'")
                        com_success = True
                    except Exception as ce:
                        print(f"COM fallback: {ce}")
                
                # Fallback a pyautogui si falla COM o es Excel/PowerPoint
                if not com_success:
                    if font_name:
                        pyautogui.hotkey('ctrl', 'shift', 'f')
                        time.sleep(0.4)
                        pyautogui.write(font_name, interval=0.01)
                        time.sleep(0.15)
                        pyautogui.press('enter')
                        msg_parts.append(f"fuente '{font_name}'")
                        time.sleep(0.3)
                        
                    if font_size:
                        # Ctrl+Shift+P abre el diálogo enfocado directamente en el Tamaño
                        pyautogui.hotkey('ctrl', 'shift', 'p')
                        time.sleep(0.4)
                        pyautogui.write(str(font_size), interval=0.01)
                        time.sleep(0.15)
                        pyautogui.press('enter')
                        msg_parts.append(f"tamaño '{font_size}'")
                    
                res_msg = f"Cambiado {', '.join(msg_parts)} en {target_name} (Nativo)." if com_success else f"Cambiado {', '.join(msg_parts)} en {target_name}."
                if player: player.write_log(f"🪄 {res_msg}")
                return res_msg
                
        return f"Macro '{action}' no implementada para la aplicación '{app}'."
        
    except Exception as e:
        return f"Error ejecutando macro en {app}: {e}"
