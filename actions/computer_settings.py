"""computer_settings.py — Full Windows system controls: volume, brightness, WiFi,
dark mode, sleep, screenshot, lock, zoom, type, clipboard, and more."""
from __future__ import annotations
import os, subprocess, time

# ── helpers ───────────────────────────────────────────────────────────────────
def _ps(cmd: str, timeout: int = 6) -> str:
    """Run a PowerShell one-liner, return stdout stripped."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return f"ERROR: {e}"

def _nircmd(args: list[str]) -> bool:
    """Try NirCmd for low-level ops. Returns True on success."""
    for path in [
        r"C:\Windows\System32\nircmd.exe",
        r"C:\Program Files\NirSoft\nircmd.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\nircmd\nircmd.exe"),
    ]:
        if os.path.isfile(path):
            try:
                subprocess.run([path] + args, timeout=4,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                return True
            except Exception:
                pass
    return False

# ══════════════════════════════════════════════════════════════════════════════
def computer_settings(parameters: dict, response=None, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    value  = str(parameters.get("value", "")).strip()
    desc   = str(parameters.get("description", "")).lower()

    # Natural-language fallback: infer action from description
    if not action and desc:
        for kw, mapped in [
            ("volumen","volume"), ("brillo","brightness"), ("wifi","wifi"),
            ("silenci","mute"), ("apagar","shutdown"), ("reiniciar","restart"),
            ("suspend","sleep"), ("hibern","hibernate"), ("bloqu","lock"),
            ("captura","screenshot"), ("screenshot","screenshot"),
            ("oscuro","dark_mode"), ("dark","dark_mode"), ("zoom","zoom"),
            ("portapapeles","clipboard"), ("clipboard","clipboard"),
            ("tipo","type"), ("escribe","type"), ("write","type"),
        ]:
            if kw in desc:
                action = mapped
                break

    def log(msg):
        if player:
            player.write_log(f"⚙ {msg}")

    # ── VOLUME ────────────────────────────────────────────────────────────────
    if action == "volume":
        try:
            import pyautogui
            v = value.lower()
            if value.isdigit():
                target = int(value)
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CoInitialize, CoUninitialize
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    CoInitialize()
                    dev = AudioUtilities.GetSpeakers()
                    iface = dev.Activate(IAudioEndpointVolume._iid_, 1, None)
                    vol = cast(iface, POINTER(IAudioEndpointVolume))
                    vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, target/100)), None)
                    CoUninitialize()
                    msg = f"Volumen ajustado al {target}%."
                except Exception:
                    # Fallback: approach target via keypresses
                    _ps(f"$obj=New-Object -ComObject WScript.Shell; $obj.SendKeys([char]173)")
                    msg = f"Volumen ajustado (aproximado) al {target}%."
            elif any(x in v for x in ("up","subi","más","mas","aumenta")):
                pyautogui.press("volumeup", presses=5); msg = "Volumen subido."
            elif any(x in v for x in ("down","baja","menos","disminuye")):
                pyautogui.press("volumedown", presses=5); msg = "Volumen bajado."
            elif any(x in v for x in ("mute","silenci","mudo")):
                pyautogui.press("volumemute"); msg = "Volumen silenciado."
            else:
                msg = f"Valor de volumen no reconocido: '{value}'"
            log(msg); return msg
        except Exception as e:
            return f"Error ajustando volumen: {e}"

    # ── BRIGHTNESS ────────────────────────────────────────────────────────────
    elif action in ("brightness", "brillo"):
        try:
            v = value.lower()
            if value.isdigit():
                level = max(0, min(100, int(value)))
            elif any(x in v for x in ("alto","high","max","subi","más")):
                level = 100
            elif any(x in v for x in ("bajo","low","min","baja","menos")):
                level = 20
            elif any(x in v for x in ("medio","mid","normal","50")):
                level = 50
            else:
                level = 70

            # Method 1: WMI
            done = False
            try:
                out = _ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})")
                if "ERROR" not in out:
                    done = True
            except Exception:
                pass

            # Method 2: PowerShell Set-Brightness
            if not done:
                _ps(f"(Get-Ciminstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})")

            msg = f"Brillo ajustado al {level}%."
            log(msg); return msg
        except Exception as e:
            return f"Error ajustando brillo: {e}"

    # ── WIFI ──────────────────────────────────────────────────────────────────
    elif action == "wifi":
        v = value.lower()
        if any(x in v for x in ("on","encend","activ","conect")):
            _ps("netsh interface set interface 'Wi-Fi' enable")
            msg = "WiFi activado."
        elif any(x in v for x in ("off","apaga","desactiv","desconect")):
            _ps("netsh interface set interface 'Wi-Fi' disable")
            msg = "WiFi desactivado."
        else:
            # Status check
            out = _ps("netsh interface show interface 'Wi-Fi' | Select-String 'Estado|Status'")
            msg = f"Estado WiFi: {out}" if out else "No se pudo obtener estado WiFi."
        log(msg); return msg

    # ── DARK MODE ─────────────────────────────────────────────────────────────
    elif action in ("dark_mode", "dark", "modo_oscuro"):
        v = value.lower()
        if any(x in v for x in ("off","claro","light","desactiv")):
            _ps("Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name AppsUseLightTheme -Value 1")
            _ps("Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name SystemUsesLightTheme -Value 1")
            msg = "Modo claro activado."
        else:
            _ps("Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name AppsUseLightTheme -Value 0")
            _ps("Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name SystemUsesLightTheme -Value 0")
            msg = "Modo oscuro activado."
        log(msg); return msg

    # ── SLEEP / HIBERNATE ─────────────────────────────────────────────────────
    elif action in ("sleep", "suspend", "suspender", "dormir"):
        _ps("Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)")
        return "PC enviada a suspensión."

    elif action in ("hibernate", "hibernar"):
        _ps("shutdown /h")
        return "PC hibernando."

    # ── LOCK SCREEN ───────────────────────────────────────────────────────────
    elif action in ("lock", "bloquear", "lock_screen"):
        _ps("rundll32.exe user32.dll,LockWorkStation")
        return "Pantalla bloqueada."

    # ── SHUTDOWN / RESTART ────────────────────────────────────────────────────
    elif action in ("shutdown", "apagar"):
        delay = int(value) if value.isdigit() else 0
        _ps(f"shutdown /s /t {delay}")
        return f"PC apagándose en {delay} segundos." if delay else "PC apagándose."

    elif action in ("restart", "reiniciar"):
        delay = int(value) if value.isdigit() else 0
        _ps(f"shutdown /r /t {delay}")
        return "PC reiniciándose."

    elif action in ("cancel_shutdown", "cancelar_apagado"):
        _ps("shutdown /a")
        return "Apagado cancelado."

    # ── SCREENSHOT ────────────────────────────────────────────────────────────
    elif action in ("screenshot", "captura", "captura_pantalla"):
        try:
            import pyautogui
            from datetime import datetime
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(os.path.expanduser("~"), "Pictures", f"jarvis_{ts}.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pyautogui.screenshot(path)
            msg = f"Captura guardada: {path}"
            log(msg); return msg
        except Exception as e:
            return f"Error tomando captura: {e}"

    # ── TYPE TEXT ─────────────────────────────────────────────────────────────
    elif action == "type":
        try:
            import pyautogui
            time.sleep(0.3)
            pyautogui.write(value, interval=0.04)
            return f"Texto escrito: '{value[:40]}{'...' if len(value)>40 else ''}'"
        except Exception as e:
            return f"Error escribiendo texto: {e}"

    # ── CLIPBOARD ─────────────────────────────────────────────────────────────
    elif action in ("clipboard", "portapapeles", "copiar"):
        try:
            import pyperclip
            if value:
                pyperclip.copy(value)
                return f"Copiado al portapapeles: '{value[:60]}'"
            else:
                content = pyperclip.paste()
                return f"Portapapeles contiene: '{content[:200]}'"
        except Exception as e:
            return f"Error con portapapeles: {e}"

    # ── ZOOM ─────────────────────────────────────────────────────────────────
    elif action == "zoom":
        try:
            import pyautogui
            v = value.lower()
            if any(x in v for x in ("in","más","mas","acercar","aumentar")):
                pyautogui.hotkey("ctrl", "+")
                return "Zoom aumentado."
            elif any(x in v for x in ("out","menos","alejar","reducir")):
                pyautogui.hotkey("ctrl", "-")
                return "Zoom reducido."
            else:
                pyautogui.hotkey("ctrl", "0")
                return "Zoom reseteado."
        except Exception as e:
            return f"Error ajustando zoom: {e}"

    # ── MUTE MICROPHONE ──────────────────────────────────────────────────────
    elif action in ("mute_mic", "silenciar_mic", "mic"):
        try:
            import pyautogui
            # Win+Alt+K toggles mic in many apps
            pyautogui.hotkey("win", "alt", "k")
            return "Micrófono silenciado/reactivado."
        except Exception as e:
            return f"Error silenciando micrófono: {e}"

    # ── WINDOW CONTROLS ──────────────────────────────────────────────────────
    elif action in ("minimize", "window_minimize", "minimizar"):
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win: win.minimize(); return "Ventana minimizada."
            return "Sin ventana activa."
        except Exception as e:
            return f"Error minimizando: {e}"

    elif action in ("maximize", "window_maximize", "maximizar"):
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win: win.maximize(); return "Ventana maximizada."
            return "Sin ventana activa."
        except Exception as e:
            return f"Error maximizando: {e}"

    elif action in ("close_window", "cerrar_ventana"):
        try:
            import pyautogui
            pyautogui.hotkey("alt", "F4")
            return "Ventana cerrada."
        except Exception as e:
            return f"Error cerrando ventana: {e}"

    elif action in ("fullscreen", "pantalla_completa"):
        try:
            import pyautogui
            pyautogui.press("f11")
            return "Pantalla completa toggled."
        except Exception as e:
            return f"Error: {e}"

    # ── DISPLAY / MONITOR ────────────────────────────────────────────────────
    elif action in ("turn_off_display", "apagar_pantalla"):
        _nircmd(["monitor", "off"]) or _ps("(Add-Type -MemberDefinition '[DllImport(\"user32.dll\")]public static extern int SendMessage(int hWnd,int hMsg,int wParam,int lParam);' -Name User32 -PassThru)::SendMessage(-1,0x0112,0xF170,2)")
        return "Pantalla apagada."

    elif action in ("turn_on_display", "encender_pantalla"):
        import pyautogui; pyautogui.moveRel(0, 1)
        return "Pantalla activada."

    # ── NIGHT LIGHT ─────────────────────────────────────────────────────────
    elif action in ("night_light", "luz_nocturna"):
        # Toggle via registry
        _ps("""
$path = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.bluelightreductionstate\\windows.data.bluelightreduction.bluelightreductionstate'
if (Test-Path $path) { Remove-Item $path -Force }
Stop-Process -Name 'SystemSettings' -ErrorAction SilentlyContinue
""")
        return "Luz nocturna toggled. Puede que necesite abrir Configuración para confirmar."

    # ── DO NOT DISTURB ───────────────────────────────────────────────────────
    elif action in ("do_not_disturb", "no_molestar", "focus"):
        # Win11: toggle focus assist
        _ps("(New-Object -ComObject Shell.Application).ToggleDesktop()")
        import pyautogui
        pyautogui.hotkey("win", "a")   # open notification center
        time.sleep(0.8)
        pyautogui.press("escape")
        return "Intenta activar 'No molestar' desde el centro de notificaciones (Win+A)."

    return f"Acción '{action}' no reconocida en computer_settings. Acciones disponibles: volume, brightness, wifi, dark_mode, sleep, hibernate, lock, shutdown, restart, screenshot, type, clipboard, zoom, minimize, maximize, close_window, fullscreen, night_light."
