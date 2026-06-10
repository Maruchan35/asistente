"""desktop.py — Windows virtual desktop & window management.
Controls virtual desktops via Win+Ctrl shortcuts and manages windows
via pygetwindow + pyautogui."""
from __future__ import annotations
import subprocess, time

try:
    import pyautogui
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    _HAS_GW = True
except ImportError:
    gw = None
    _HAS_GW = False

def _ps(cmd: str, timeout: int = 8) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return f"ERROR: {e}"

def _require_pyautogui() -> str | None:
    if not _HAS_PYAUTOGUI:
        return "pyautogui no instalado: pip install pyautogui"
    return None

def _hotkey(*keys: str, pause: float = 0.3):
    pyautogui.hotkey(*keys)
    time.sleep(pause)

# ══════════════════════════════════════════════════════════════════════════════
def desktop_control(parameters: dict, player=None) -> str:
    action  = parameters.get("action", "list_windows").lower().strip()
    target  = parameters.get("window", parameters.get("title", "")).strip()
    count   = int(parameters.get("count", 1))

    def log(msg: str):
        if player:
            player.write_log(f"🖥 {msg}")

    err = _require_pyautogui()
    if err and action not in ("list_windows", "list_processes"):
        return err

    # ── VIRTUAL DESKTOP — NEW ─────────────────────────────────────────────────
    if action in ("new_desktop", "nuevo_escritorio", "new_virtual_desktop"):
        _hotkey("win", "ctrl", "d")
        log("Nuevo escritorio virtual creado.")
        return "Nuevo escritorio virtual creado."

    # ── VIRTUAL DESKTOP — SWITCH ─────────────────────────────────────────────
    elif action in ("switch_desktop", "cambiar_escritorio", "next_desktop"):
        direction = parameters.get("direction", "right").lower()
        key = "right" if direction in ("right", "next", "siguiente") else "left"
        _hotkey("win", "ctrl", key)
        log(f"Cambiado al escritorio {direction}.")
        return f"Cambiado al escritorio {direction}."

    # ── VIRTUAL DESKTOP — CLOSE ──────────────────────────────────────────────
    elif action in ("close_desktop", "cerrar_escritorio"):
        _hotkey("win", "ctrl", "f4")
        log("Escritorio virtual cerrado.")
        return "Escritorio virtual actual cerrado."

    # ── VIRTUAL DESKTOP — VIEW ────────────────────────────────────────────────
    elif action in ("task_view", "vista_tareas", "show_desktops"):
        _hotkey("win", "tab")
        log("Vista de tareas abierta.")
        return "Vista de tareas abierta."

    # ── WINDOW — LIST ─────────────────────────────────────────────────────────
    elif action in ("list_windows", "listar_ventanas", "windows"):
        if not _HAS_GW:
            # Fallback via PowerShell
            out = _ps("Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
                      "Select-Object Id, ProcessName, MainWindowTitle | "
                      "Format-Table -AutoSize | Out-String")
            return f"Ventanas abiertas:\n{out}" if out else "No se pudieron listar las ventanas."
        wins = [w for w in gw.getAllWindows() if w.title.strip()]
        if not wins:
            return "No hay ventanas abiertas detectadas."
        lines = [f"  [{i+1}] {w.title[:60]}" for i, w in enumerate(wins[:20])]
        log(f"{len(wins)} ventanas detectadas")
        return f"Ventanas abiertas ({len(wins)}):\n" + "\n".join(lines)

    # ── WINDOW — FOCUS / ACTIVATE ────────────────────────────────────────────
    elif action in ("focus", "activate", "enfocar", "activar"):
        if not target:
            return "Especificá window con el título de la ventana a enfocar."
        if not _HAS_GW:
            return "pygetwindow no instalado: pip install pygetwindow"
        wins = gw.getWindowsWithTitle(target)
        if not wins:
            # Partial match
            wins = [w for w in gw.getAllWindows() if target.lower() in w.title.lower()]
        if not wins:
            return f"No se encontró ninguna ventana con '{target}'."
        try:
            w = wins[0]
            if w.isMinimized:
                w.restore()
            w.activate()
            time.sleep(0.4)
            log(f"Ventana enfocada: {w.title[:50]}")
            return f"Ventana activada: '{w.title[:60]}'"
        except Exception as e:
            return f"Error activando ventana: {e}"

    # ── WINDOW — MINIMIZE ─────────────────────────────────────────────────────
    elif action in ("minimize", "minimizar"):
        if target and _HAS_GW:
            wins = gw.getWindowsWithTitle(target) or [
                w for w in gw.getAllWindows() if target.lower() in w.title.lower()]
            if wins:
                try:
                    wins[0].minimize()
                    return f"Ventana minimizada: '{wins[0].title[:60]}'"
                except Exception as e:
                    return f"Error: {e}"
            return f"Ventana '{target}' no encontrada."
        # Minimize active window
        _hotkey("win", "down")
        return "Ventana activa minimizada."

    # ── WINDOW — MAXIMIZE ─────────────────────────────────────────────────────
    elif action in ("maximize", "maximizar"):
        if target and _HAS_GW:
            wins = gw.getWindowsWithTitle(target) or [
                w for w in gw.getAllWindows() if target.lower() in w.title.lower()]
            if wins:
                try:
                    wins[0].maximize()
                    return f"Ventana maximizada: '{wins[0].title[:60]}'"
                except Exception as e:
                    return f"Error: {e}"
        _hotkey("win", "up")
        return "Ventana activa maximizada."

    # ── WINDOW — RESTORE ─────────────────────────────────────────────────────
    elif action in ("restore", "restaurar"):
        if target and _HAS_GW:
            wins = gw.getWindowsWithTitle(target) or [
                w for w in gw.getAllWindows() if target.lower() in w.title.lower()]
            if wins:
                try:
                    wins[0].restore()
                    return f"Ventana restaurada: '{wins[0].title[:60]}'"
                except Exception as e:
                    return f"Error: {e}"
        _hotkey("win", "down", "down")  # double-down restores
        return "Ventana restaurada."

    # ── WINDOW — CLOSE ────────────────────────────────────────────────────────
    elif action in ("close", "cerrar"):
        if target and _HAS_GW:
            wins = gw.getWindowsWithTitle(target) or [
                w for w in gw.getAllWindows() if target.lower() in w.title.lower()]
            if wins:
                try:
                    wins[0].close()
                    return f"Ventana cerrada: '{wins[0].title[:60]}'"
                except Exception as e:
                    return f"Error cerrando: {e}"
        _hotkey("alt", "f4")
        return "Ventana activa cerrada."

    # ── WINDOW — SNAP / TILE ──────────────────────────────────────────────────
    elif action in ("snap_left", "snap left", "izquierda"):
        _hotkey("win", "left")
        return "Ventana ajustada a la izquierda."

    elif action in ("snap_right", "snap right", "derecha"):
        _hotkey("win", "right")
        return "Ventana ajustada a la derecha."

    elif action in ("snap_top", "snap top", "arriba"):
        _hotkey("win", "up")
        return "Ventana maximizada/ajustada arriba."

    elif action in ("tile_windows", "organizar_ventanas"):
        # Windows built-in tiling
        _ps("(New-Object -ComObject Shell.Application).TileVertically()")
        return "Ventanas organizadas verticalmente."

    # ── SHOW DESKTOP ──────────────────────────────────────────────────────────
    elif action in ("show_desktop", "mostrar_escritorio"):
        _hotkey("win", "d")
        return "Escritorio mostrado."

    # ── MOVE WINDOW TO DESKTOP ────────────────────────────────────────────────
    elif action in ("move_to_desktop", "mover_a_escritorio"):
        # Open Task View then use keyboard to move (limited automation)
        _hotkey("win", "tab")
        time.sleep(0.8)
        return ("Vista de tareas abierta. Arrastrá la ventana al escritorio destino "
                "o hacé clic derecho → Mover a → Escritorio N.")

    # ── ALWAYS ON TOP ────────────────────────────────────────────────────────
    elif action in ("always_on_top", "siempre_encima"):
        if not target:
            return "Especificá window con el título de la ventana."
        # Use PowerShell to toggle always-on-top
        script = (
            "Add-Type -TypeDefinition @'\n"
            "using System; using System.Runtime.InteropServices;\n"
            "public class WinAPI {\n"
            "    [DllImport(\"user32.dll\")] public static extern bool SetWindowPos(IntPtr h, IntPtr i, int x, int y, int cx, int cy, uint f);\n"
            "    [DllImport(\"user32.dll\")] public static extern IntPtr FindWindow(string c, string t);\n"
            "}\n'@\n"
            f"$h = [WinAPI]::FindWindow($null, '{target}')\n"
            "$HWND_TOPMOST = [IntPtr](-1)\n"
            "[WinAPI]::SetWindowPos($h, $HWND_TOPMOST, 0, 0, 0, 0, 0x0003)"
        )
        _ps(script)
        return f"Ventana '{target}' configurada para estar siempre encima."

    # ── ARRANGE WINDOWS ──────────────────────────────────────────────────────
    elif action in ("cascade", "cascada"):
        _ps("(New-Object -ComObject Shell.Application).CascadeWindows()")
        return "Ventanas organizadas en cascada."

    return (f"Acción '{action}' no reconocida. "
            "Usa: new_desktop | switch_desktop | close_desktop | task_view | "
            "list_windows | focus | minimize | maximize | restore | close | "
            "snap_left | snap_right | tile_windows | show_desktop | always_on_top | cascade")
