# -*- coding: utf-8 -*-
"""
file_controller.py — Pure Python robust file and directory operations manager for JARVIS.
"""
import os
import shutil
import traceback
from pathlib import Path
from datetime import datetime

def _copy_file_to_clipboard_physical(file_path: str):
    try:
        import subprocess
        import os
        if not os.path.exists(file_path):
            return False
        
        # Escapar comillas simples para PowerShell
        safe_path = file_path.replace("'", "''")
        
        # PowerShell para poner un FileDrop en el portapapeles (compatible con el explorador y WhatsApp)
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$c = New-Object System.Collections.Specialized.StringCollection; "
            f"$c.Add('{safe_path}'); "
            "[System.Windows.Forms.Clipboard]::SetFileDropList($c)"
        )
        subprocess.run(["powershell", "-Sta", "-NoProfile", "-Command", ps_cmd], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception as e:
        print(f"Error physically copying file: {e}")
        return False

def resolve_path(p: str) -> str:
    if not p:
        return os.path.expanduser("~/Desktop")

    p = p.strip()
    p_lower = p.lower()
    home = os.path.expanduser("~")

    # Si ya es una ruta absoluta, devolver tal cual
    if os.path.isabs(p):
        return p

    # Mapa de palabras clave → carpetas reales (inglés y español)
    _FOLDER_MAP = {
        # Escritorio
        "desktop": "Desktop", "escritorio": "Desktop",
        # Descargas
        "downloads": "Downloads", "descargas": "Downloads",
        # Documentos
        "documents": "Documents", "documentos": "Documents",
        # Imágenes
        "pictures": "Pictures", "imagenes": "Pictures", "imágenes": "Pictures", "images": "Pictures",
        # Música
        "music": "Music", "musica": "Music", "música": "Music",
        # Videos
        "videos": "Videos", "video": "Videos",
        # Home
        "home": "",
    }

    # Separar la primera parte del path del resto
    parts = p.replace("\\", "/").split("/", 1)
    first = parts[0].lower()
    rest  = parts[1] if len(parts) > 1 else ""

    if first in _FOLDER_MAP:
        base_folder = _FOLDER_MAP[first]
        base = os.path.join(home, base_folder) if base_folder else home
        return os.path.join(base, rest) if rest else base

    # Si la primera parte no es una palabra clave conocida,
    # buscar la carpeta en ubicaciones comunes del usuario
    search_roots = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        home,
    ]
    for root in search_roots:
        candidate = os.path.join(root, p)
        if os.path.exists(candidate):
            return candidate
        # Buscar subcarpeta cuyo nombre coincida (sin distinguir mayúsc./espacios vs _)
        first_norm = first.replace(" ", "_").replace("-", "_")
        if os.path.isdir(root):
            for folder in os.listdir(root):
                if folder.lower().replace(" ", "_").replace("-", "_") == first_norm:
                    base = os.path.join(root, folder)
                    return os.path.join(base, rest) if rest else base

    # Fallback: resolver relativo al Escritorio para no mezclar con el directorio de JARVIS
    return os.path.join(home, "Desktop", p)

def file_controller(parameters: dict, player=None) -> str:
    """
    Manages files and folders: list, create, delete, move, copy, rename, read, write, edit, find, largest, disk_usage, organize_desktop.
    """
    action = parameters.get("action", "").lower().strip()
    path_raw = parameters.get("path", "")
    destination_raw = parameters.get("destination", "")
    new_name = parameters.get("new_name", "")
    content = parameters.get("content", "")
    search_name = parameters.get("name", "")
    extension = parameters.get("extension", "")
    count = int(parameters.get("count", 10))
    old_text = parameters.get("old_text", "")
    new_text = parameters.get("new_text", "")
    mode = parameters.get("mode", "replace").lower().strip()
    confirm = parameters.get("confirm", False)

    if not action:
        return "Error: Se requiere el parámetro 'action'."

    try:
        resolved_path = resolve_path(path_raw)

        # 1. LIST DIRECTORY
        if action == "list":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            if not os.path.isdir(resolved_path):
                return f"Error: '{path_raw}' no es una carpeta."
            
            items = sorted(os.listdir(resolved_path))
            if not items:
                return f"La carpeta '{os.path.basename(resolved_path)}' está vacía."
                
            lines = [f"Contenido de '{os.path.basename(resolved_path)}' ({len(items)} elementos):"]
            for item in items:
                full_item = os.path.join(resolved_path, item)
                if os.path.isdir(full_item):
                    lines.append(f"  📁 {item}/")
                else:
                    sz_kb = os.path.getsize(full_item) / 1024
                    lines.append(f"  📄 {item} ({sz_kb:.1f} KB)")
            return "\n".join(lines)

        # 2. CREATE FILE
        elif action in ("create_file", "write"):
            # Si el path resuelto es una carpeta (no tiene nombre de archivo), usar Desktop por defecto
            if os.path.isdir(resolved_path) or not os.path.splitext(resolved_path)[1]:
                # Intentar extraer nombre de archivo del path_raw original
                raw_base = os.path.basename(path_raw.strip("/\\"))
                if raw_base and "." in raw_base:
                    resolved_path = os.path.join(os.path.expanduser("~/Desktop"), raw_base)
                else:
                    # Generar nombre por defecto en el Escritorio
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    resolved_path = os.path.join(os.path.expanduser("~/Desktop"), f"archivo_{timestamp}.txt")

            dir_part = os.path.dirname(resolved_path)
            if dir_part:
                os.makedirs(dir_part, exist_ok=True)

            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content or "")
            msg = f"Archivo creado exitosamente: '{os.path.basename(resolved_path)}' en '{os.path.dirname(resolved_path)}'."
            if player:
                player.write_log(f"📄 {msg}")
            return msg

        # 3. CREATE FOLDER
        elif action == "create_folder":
            os.makedirs(resolved_path, exist_ok=True)
            msg = f"Carpeta creada exitosamente: '{resolved_path}'."
            if player:
                player.write_log(f"📁 {msg}")
            return msg

        # 4. DELETE (Send to Recycle Bin)
        elif action == "delete":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            
            # Use send2trash for safety if possible
            try:
                import send2trash
                send2trash.send2trash(resolved_path)
                msg = f"'{os.path.basename(resolved_path)}' movido a la Papelera de Reciclaje exitosamente."
            except ImportError:
                if os.path.isdir(resolved_path):
                    shutil.rmtree(resolved_path)
                else:
                    os.remove(resolved_path)
                msg = f"'{os.path.basename(resolved_path)}' eliminado físicamente con éxito (send2trash no disponible)."
                
            if player:
                player.write_log(f"🗑️ {msg}")
            return msg

        # 5. MOVE
        elif action == "move":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta origen '{path_raw}' no existe."
            resolved_dest = resolve_path(destination_raw)
            os.makedirs(os.path.dirname(resolved_dest), exist_ok=True)
            shutil.move(resolved_path, resolved_dest)
            msg = f"Movido de '{path_raw}' a '{destination_raw}' correctamente."
            if player:
                player.write_log(f"🚚 {msg}")
            return msg

        # 6. COPY
        elif action == "copy":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta origen '{path_raw}' no existe."
            resolved_dest = resolve_path(destination_raw)
            if os.path.isdir(resolved_path):
                shutil.copytree(resolved_path, resolved_dest)
            else:
                os.makedirs(os.path.dirname(resolved_dest), exist_ok=True)
                shutil.copy2(resolved_path, resolved_dest)
            msg = f"Copiado de '{path_raw}' a '{destination_raw}' correctamente."
            if player:
                player.write_log(f"👥 {msg}")
            return msg

        # 7. RENAME
        elif action == "rename":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            if not new_name:
                return "Error: Se requiere 'new_name' para renombrar."
            new_path = os.path.join(os.path.dirname(resolved_path), new_name)
            os.rename(resolved_path, new_path)
            msg = f"Renombrado de '{os.path.basename(resolved_path)}' a '{new_name}' correctamente."
            if player:
                player.write_log(f"✏️ {msg}")
            return msg

        # 8. READ FILE
        elif action == "read":
            if not os.path.exists(resolved_path):
                return f"Error: El archivo '{path_raw}' no existe."
            if os.path.isdir(resolved_path):
                return f"Error: '{path_raw}' es una carpeta. Utilice action='list'."
                
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            if len(text) > 2000:
                return f"Mostrando primeros 2000 caracteres de '{os.path.basename(resolved_path)}':\n\n{text[:2000]}\n...[Truncado]"
            return text

        # 9. EDIT (Search and Replace/Append/Prepend/Overwrite)
        elif action == "edit":
            if not os.path.exists(resolved_path):
                return f"Error: El archivo '{path_raw}' no existe."
            
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                orig = f.read()
                
            if mode == "append":
                updated = orig + "\n" + new_text
            elif mode == "prepend":
                updated = new_text + "\n" + orig
            elif mode == "overwrite":
                updated = new_text
            else: # replace mode
                if not old_text:
                    return "Error: Se requiere 'old_text' para reemplazar en modo 'replace'."
                if old_text not in orig:
                    return f"Error: No se encontró el fragmento '{old_text}' en el archivo."
                updated = orig.replace(old_text, new_text, 1)
                
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(updated)
            return f"Archivo '{os.path.basename(resolved_path)}' editado exitosamente en modo '{mode}'."

        # 10. FIND RECURSIVELY
        elif action == "find":
            results = []
            target_name = search_name.lower().strip()
            target_ext = extension.lower().strip()
            
            if not target_name and not target_ext:
                return "Error: Proporcione un 'name' o una 'extension' para buscar."
                
            for root, _, files in os.walk(resolved_path):
                for file in files:
                    file_lower = file.lower()
                    match_name = not target_name or target_name in file_lower
                    match_ext = not target_ext or file_lower.endswith(target_ext)
                    if match_name and match_ext:
                        results.append(os.path.join(root, file))
                        if len(results) >= 20: # limit output size
                            break
                if len(results) >= 20:
                    break
                    
            if not results:
                return "No se encontró ningún archivo coincidente."
                
            lines = [f"Resultados de búsqueda en '{path_raw}':"]
            for idx, r in enumerate(results, 1):
                lines.append(f"{idx}. {r}")
            return "\n".join(lines)

        # 11. LARGEST FILES
        elif action == "largest":
            file_list = []
            for root, _, files in os.walk(resolved_path):
                for file in files:
                    fp = os.path.join(root, file)
                    try:
                        sz = os.path.getsize(fp)
                        file_list.append((fp, sz))
                    except: pass
            
            file_list.sort(key=lambda x: x[1], reverse=True)
            top = file_list[:count]
            if not top:
                return "No se encontraron archivos."
                
            lines = [f"Top {len(top)} archivos más grandes en '{path_raw}':"]
            for fp, sz in top:
                sz_mb = sz / (1024 * 1024)
                lines.append(f"  ⚖️ {sz_mb:.1f} MB — {fp}")
            return "\n".join(lines)

        # 12. DISK USAGE
        elif action == "disk_usage":
            total, used, free = shutil.disk_usage(resolved_path)
            gb = 1024 * 1024 * 1024
            return (
                f"Estadísticas del disco para '{path_raw}':\n"
                f"  💿 Capacidad Total: {total/gb:.1f} GB\n"
                f"  💾 Espacio Usado: {used/gb:.1f} GB\n"
                f"  🟢 Espacio Libre: {free/gb:.1f} GB"
            )

        # 13. INFO METADATA
        elif action == "info":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            
            is_dir = os.path.isdir(resolved_path)
            stat = os.stat(resolved_path)
            created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            lines = [
                f"Metadatos para '{os.path.basename(resolved_path)}':",
                f"  Tipo: {'Carpeta 📁' if is_dir else 'Archivo 📄'}",
                f"  Ruta completa: {resolved_path}",
                f"  Creado el: {created}",
                f"  Modificado el: {modified}"
            ]
            if not is_dir:
                lines.append(f"  Tamaño: {stat.st_size / 1024:.1f} KB")
            return "\n".join(lines)

        # 14. ORGANIZE DESKTOP
        elif action == "organize_desktop":
            desktop = resolve_path("desktop")
            cats = {
                "Documentos": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".md"],
                "Imagenes": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"],
                "Zips": [".zip", ".rar", ".7z", ".tar", ".gz"],
                "Ejecutables": [".exe", ".msi", ".bat", ".vbs"]
            }
            
            moved_count = 0
            for item in os.listdir(desktop):
                item_path = os.path.join(desktop, item)
                if os.path.isdir(item_path) or item.startswith("."):
                    continue
                
                ext = os.path.splitext(item)[1].lower()
                for cat_name, extensions in cats.items():
                    if ext in extensions:
                        dest_folder = os.path.join(desktop, cat_name)
                        os.makedirs(dest_folder, exist_ok=True)
                        shutil.move(item_path, os.path.join(dest_folder, item))
                        moved_count += 1
                        break
            
            msg = f"Organización del Escritorio completada. Se ordenaron {moved_count} archivos en carpetas categóricas."
            if player:
                player.write_log(f"🧹 {msg}")
            return msg

        # 15. GUI SEARCH (CUSTOM)
        elif action == "gui_search":
            filename = parameters.get("filename", "")
            folder = parameters.get("folder", "")
            if not filename or not folder:
                return "Error: Falta el parámetro 'filename' o 'folder'."
            user_profile = os.environ.get("USERPROFILE", "")
            folder_map = {
                "descargas": os.path.join(user_profile, "Downloads"),
                "downloads": os.path.join(user_profile, "Downloads"),
                "documentos": os.path.join(user_profile, "Documents"),
                "documents": os.path.join(user_profile, "Documents"),
                "escritorio": os.path.join(user_profile, "Desktop"),
                "desktop": os.path.join(user_profile, "Desktop"),
                "musica": os.path.join(user_profile, "Music"),
                "imagenes": os.path.join(user_profile, "Pictures")
            }
            target_path = folder_map.get(folder.lower().strip(), folder)
            try:
                import urllib.parse
                import subprocess
                encoded_path = urllib.parse.quote(target_path)
                search_uri = f'search-ms:query={filename}&crumb=location:{target_path}'
                subprocess.Popen(f'explorer "{search_uri}"', shell=True)
            except Exception as e:
                return f"Error abriendo explorador: {e}"
            if player:
                player.write_log(f"🔍 Búsqueda visual abierta en {target_path} para '{filename}'")
            results = []
            try:
                import time
                if os.path.exists(target_path):
                    start_time = time.time()
                    target_name_lower = filename.lower()
                    
                    for root, dirs, files in os.walk(target_path):
                        if time.time() - start_time > 3.0:  # Timeout 3 segundos máximo
                            break
                        for f in files:
                            if target_name_lower in f.lower():
                                full_p = os.path.join(root, f)
                                results.append(full_p)
                                if len(results) >= 8: # Hasta 8 resultados
                                    break
                        if len(results) >= 8:
                            break
            except Exception as e: 
                print(f"[gui_search] Error interno buscando: {e}")
            
            if not results:
                return f"He abierto el explorador buscando '{filename}' en {folder}. Sin embargo, no encontré los archivos rápidamente en mi búsqueda interna (se agotó el tiempo). Pídele al usuario que revise la ventana abierta y, si quiere copiar uno, te diga el nombre completo."
            
            res_list = "\n".join([f"{i+1}. {r}" for i, r in enumerate(results)])
            return f"Explorador abierto. Encontré internamente estos archivos:\n{res_list}\n\nDile al usuario: 'Encontré varios, por ejemplo el primero es [nombre del 1], el segundo es [nombre del 2]. ¿Cuál de ellos quieres?'"

        # 16. SELECT AND COPY (CUSTOM)
        elif action == "select_and_copy":
            filepath = parameters.get("filepath", "")
            if not filepath or not os.path.exists(filepath):
                return f"Error: No se proporcionó un filepath válido o el archivo no existe: '{filepath}'"
            success = _copy_file_to_clipboard_physical(filepath)
            if success:
                return f"El archivo '{filepath}' ha sido copiado al portapapeles exitosamente. Pregúntale al usuario: '¿Lo abro, o quieres que lo envíe por WhatsApp a alguien?'"
            return f"Falló la copia al portapapeles del archivo: '{filepath}'"

        # 17. OPEN FILE (CUSTOM)
        elif action == "open_file":
            filepath = parameters.get("filepath", "")
            if not filepath or not os.path.exists(filepath):
                return "Error: Ruta de archivo inválida para abrir."
            try:
                import sys
                import subprocess
                if sys.platform == "win32":
                    os.startfile(filepath)
                elif sys.platform == "darwin":
                    subprocess.call(["open", filepath])
                else:
                    subprocess.call(["xdg-open", filepath])
                return f"Archivo '{filepath}' abierto exitosamente."
            except Exception as e:
                return f"Error abriendo archivo: {e}"

        else:
            return f"Acción '{action}' no soportada en file_controller."

    except Exception as e:
        traceback.print_exc()
        return f"Error ejecutando la operación de archivo: {str(e)}"
