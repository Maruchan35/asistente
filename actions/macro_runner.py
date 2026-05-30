"""macro_runner.py — UI Automation Macro Engine."""
import time
import pyautogui
import json
from pathlib import Path

def macro_runner(parameters: dict, player=None) -> str:
    """
    Executes a sequence of UI actions based on a dynamic plan.
    This allows JARVIS to 'learn' and execute multi-step macros like opening an app,
    searching for something, and clicking.
    """
    action = parameters.get("action", "")
    
    if action == "run_saved":
        macro_name = parameters.get("name", "")
        if not macro_name:
            return "Falta el nombre de la macro a ejecutar."
        try:
            base_dir = Path(__file__).resolve().parent.parent
            macros_file = base_dir / "config" / "macros.json"
            if not macros_file.exists():
                return "El archivo de macros no existe."
            
            with open(macros_file, "r", encoding="utf-8") as f:
                macros = json.load(f)
                
            if macro_name not in macros:
                return f"No se encontró la macro '{macro_name}' en los ajustes."
                
            # Override action and steps to run it via the existing logic
            action = "execute_macro"
            parameters["steps"] = macros[macro_name]
        except Exception as e:
            return f"Error leyendo macros: {e}"
            
    if action == "execute_macro":
        steps = parameters.get("steps", [])
        if not steps:
            return "No se proporcionaron pasos para la macro."
            
        success_count = 0
        try:
            for i, step in enumerate(steps):
                cmd = step.get("cmd", "").lower()
                val = step.get("val", "")
                
                if player:
                    player.write_log(f"⚙️ Macro [{i+1}/{len(steps)}]: {cmd} {val}")
                
                if cmd == "open_url":
                    import webbrowser
                    webbrowser.open(str(val))
                    time.sleep(2)
                elif cmd == "win_search":
                    pyautogui.press("win")
                    time.sleep(0.5)
                    import unicodedata
                    clean_val = "".join(c for c in unicodedata.normalize('NFD', str(val)) if unicodedata.category(c) != 'Mn')
                    pyautogui.write(clean_val, interval=0.02)
                    time.sleep(0.8)
                    pyautogui.press("enter")
                elif cmd == "type":
                    import unicodedata
                    clean_val = "".join(c for c in unicodedata.normalize('NFD', str(val)) if unicodedata.category(c) != 'Mn')
                    pyautogui.write(clean_val, interval=0.03)
                elif cmd == "press":
                    if "," in str(val):
                        key, count = val.split(",", 1)
                        try:
                            pyautogui.press(key.strip(), presses=int(count.strip()))
                        except ValueError:
                            pyautogui.press(key.strip())
                    else:
                        pyautogui.press(str(val))
                elif cmd == "hotkey":
                    keys = [k.strip() for k in str(val).split("+")]
                    pyautogui.hotkey(*keys)
                elif cmd == "wait":
                    try:
                        time.sleep(float(val))
                    except ValueError:
                        pass
                elif cmd == "click":
                    if isinstance(val, str) and "," in val:
                        x, y = val.split(",", 1)
                        try:
                            pyautogui.click(x=int(x.strip()), y=int(y.strip()))
                        except ValueError:
                            pyautogui.click()
                    else:
                        pyautogui.click()
                
                time.sleep(0.3)
                success_count += 1
                
            return f"Macro ejecutada con éxito ({success_count} pasos)."
            
        except Exception as e:
            return f"Error ejecutando macro en el paso {success_count + 1}: {e}"
            
    return f"Acción de macro '{action}' no soportada."
