# -*- coding: utf-8 -*-
"""
open_app.py — Intelligent heuristic application finder and launcher for JARVIS.
"""
import os
import subprocess
import webbrowser
import traceback

def find_executable(app_name: str) -> str:
    """Scan standard system folders recursively to find executable, desktop link, or document matching name."""
    exe_search_dirs = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files")),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        os.path.join(os.environ.get("LocalAppData", ""), "Programs"),
        "C:\\Windows\\System32",
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
        # Start Menu del SISTEMA — aquí viven los accesos directos de la
        # mayoría de las apps instaladas (incluidas las de Microsoft Store)
        os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                     "Microsoft\\Windows\\Start Menu\\Programs"),
    ]
    
    doc_search_dirs = [
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "Documents"),
        os.path.join(os.path.expanduser("~"), "Downloads")
    ]
    
    app_lower = app_name.lower().strip()
    
    # First search: standard programs (.exe, .lnk)
    for base_dir in exe_search_dirs:
        if not base_dir or not os.path.exists(base_dir):
            continue
            
        for root, dirs, files in os.walk(base_dir):
            depth = root.count(os.sep) - base_dir.count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
                
            for file in files:
                if file.lower().endswith(".exe") or file.lower().endswith(".lnk"):
                    file_name_no_ext = os.path.splitext(file)[0].lower()
                    if app_lower == file_name_no_ext or app_lower in file_name_no_ext:
                        full_path = os.path.join(root, file)
                        if "redist" not in full_path.lower() and "uninstall" not in full_path.lower():
                            return full_path

    # Second search: user documents (.docx, .xlsx, .pptx, .pdf, .txt, .csv, .zip, etc.)
    doc_extensions = [".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".csv", ".zip", ".png", ".jpg"]
    for base_dir in doc_search_dirs:
        if not base_dir or not os.path.exists(base_dir):
            continue
            
        for root, dirs, files in os.walk(base_dir):
            depth = root.count(os.sep) - base_dir.count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
                
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in doc_extensions:
                    file_name_no_ext = os.path.splitext(file)[0].lower()
                    if app_lower == file_name_no_ext or app_lower in file_name_no_ext:
                        return os.path.join(root, file)
                        
    return None

def open_app(parameters: dict, response=None, player=None) -> str:
    """Launch local desktop applications, folders, or web URLs heuristically based on app_name."""
    app_name = parameters.get("app_name", "").strip()
    if not app_name:
        return "Error: Se requiere el parámetro 'app_name'."

    app_lower = app_name.lower().strip()

    try:
        # 1. Check if it's a URL
        if app_lower.startswith("http://") or app_lower.startswith("https://") or app_lower.endswith(".com") or app_lower.endswith(".org") or app_lower.endswith(".net") or app_lower.endswith(".es") or app_lower.endswith(".cl"):
            url = app_name if app_lower.startswith("http") else f"https://{app_name}"
            webbrowser.open(url)
            msg = f"Abriendo el sitio web: '{url}'."
            if player:
                player.write_log(f"🌐 {msg}")
            return msg

        # 2. Check if it is a directory path or drive letter
        if os.path.exists(app_name) and os.path.isdir(app_name):
            os.startfile(app_name)
            msg = f"Abriendo la carpeta local: '{app_name}'."
            if player:
                player.write_log(f"📁 {msg}")
            return msg

        # 3. Check virtual directories
        home = os.path.expanduser("~")
        virtual_folders = {
            "desktop": os.path.join(home, "Desktop"),
            "escritorio": os.path.join(home, "Desktop"),
            "downloads": os.path.join(home, "Downloads"),
            "descargas": os.path.join(home, "Downloads"),
            "documents": os.path.join(home, "Documents"),
            "documentos": os.path.join(home, "Documents"),
            "pictures": os.path.join(home, "Pictures"),
            "imagenes": os.path.join(home, "Pictures"),
            "music": os.path.join(home, "Music"),
            "musica": os.path.join(home, "Music"),
            "videos": os.path.join(home, "Videos")
        }
        if app_lower in virtual_folders:
            folder_path = virtual_folders[app_lower]
            os.startfile(folder_path)
            msg = f"Abriendo carpeta del sistema: '{app_lower}'."
            if player:
                player.write_log(f"📁 {msg}")
            return msg

        # 4. Standard Static mappings dictionary
        mappings = {
            "notepad": "notepad.exe",
            "bloc de notas": "notepad.exe",
            "calculator": "calc.exe",
            "calculadora": "calc.exe",
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "explorer": "explorer.exe",
            "explorador de archivos": "explorer.exe",
            "cmd": "cmd.exe",
            "terminal": "powershell.exe",
            "powershell": "powershell.exe",
            "paint": "mspaint.exe",
            "taskmgr": "taskmgr.exe",
            "administrador de tareas": "taskmgr.exe",
            "word": "winword.exe",
            "microsoft word": "winword.exe",
            "excel": "excel.exe",
            "microsoft excel": "excel.exe",
            "powerpoint": "powerpnt.exe",
            "microsoft powerpoint": "powerpnt.exe"
        }

        executable = mappings.get(app_lower, None)

        # 5. If not in static mappings, use our heuristics search
        if not executable:
            executable = find_executable(app_name)

        # ── Fallbacks web para apps que suelen NO estar instaladas como .exe ──
        # (WhatsApp/Telegram en versión web, etc.) Solo se usan si no se
        # encontró ejecutable local.
        WEB_FALLBACKS = {
            "whatsapp":      "https://web.whatsapp.com",
            "whatsapp web":  "https://web.whatsapp.com",
            "telegram":      "https://web.telegram.org",
            "youtube":       "https://www.youtube.com",
            "gmail":         "https://mail.google.com",
            "netflix":       "https://www.netflix.com",
            "spotify web":   "https://open.spotify.com",
            "discord web":   "https://discord.com/app",
            "twitter":       "https://x.com",
            "x":             "https://x.com",
        }
        # Nombres de navegador: si piden uno que no está instalado,
        # abrir el navegador PREDETERMINADO del sistema en su lugar.
        BROWSER_NAMES = {"chrome", "google chrome", "firefox", "edge",
                         "brave", "opera", "navegador", "browser"}

        def _web_fallback() -> str | None:
            """Intentar abrir versión web / navegador predeterminado."""
            if app_lower in WEB_FALLBACKS:
                webbrowser.open(WEB_FALLBACKS[app_lower])
                m = (f"'{app_name}' no está instalada como aplicación — "
                     f"abrí la versión web en tu navegador.")
                if player:
                    try: player.write_log(f"🌐 {m}")
                    except Exception: pass
                return m
            if app_lower in BROWSER_NAMES:
                webbrowser.open("https://www.google.com")
                m = (f"'{app_name}' no está instalado — abrí tu navegador "
                     "predeterminado en su lugar.")
                if player:
                    try: player.write_log(f"🌐 {m}")
                    except Exception: pass
                return m
            return None

        # 6. Si no hay ejecutable, probar fallback web ANTES del intento ciego
        if not executable:
            fb = _web_fallback()
            if fb:
                return fb
            executable = app_name

        # Security: block shell metacharacters that could enable injection
        DANGEROUS = ["&", "|", ";", "`", "$", ">", "<", "\n", "\r"]
        if any(c in executable for c in DANGEROUS):
            return f"Error: nombre de aplicación contiene caracteres inválidos."

        # Launch without shell=True to prevent injection
        try:
            os.startfile(executable)
        except Exception:
            # Fallback: launch as list (no shell) to avoid injection
            try:
                subprocess.Popen([executable], shell=False,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                # Último intento antes de rendirse: fallback web
                # (ej. mapping 'chrome.exe' estaba pero Chrome no está instalado)
                fb = _web_fallback()
                if fb:
                    return fb
                subprocess.Popen(executable, shell=False,
                                 creationflags=subprocess.CREATE_NO_WINDOW)

        msg = f"Abriendo la aplicación: '{app_name}'."
        if player:
            player.write_log(f"🚀 {msg}")
        return f"Aplicación '{app_name}' iniciada correctamente (Ruta: {executable})."

    except Exception as e:
        # Una sola línea de error — sin triple traceback en consola
        return (f"No pude abrir '{app_name}': {str(e)[:100]}. "
                "Verifica que esté instalada o dime el nombre exacto.")
