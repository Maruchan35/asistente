import os
import time
import subprocess
import urllib.parse
import webbrowser
import json
import unicodedata
from pathlib import Path

try:
    import pyautogui
except ImportError:
    pyautogui = None

BASE_DIR       = Path(__file__).resolve().parent.parent
CONTACTS_FILE  = BASE_DIR / "config" / "whatsapp_contacts.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_contacts() -> dict:
    if CONTACTS_FILE.exists():
        try:
            return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_contacts(contacts: dict):
    CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_FILE.write_text(json.dumps(contacts, indent=4, ensure_ascii=False), encoding="utf-8")

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")
    return text

def _resolve_file_path(raw: str) -> Path:
    """Resuelve rutas relativas con palabras clave a rutas absolutas."""
    if not raw:
        return Path()
    home = Path(os.path.expanduser("~"))
    raw  = raw.replace("~", str(home)).strip()
    p    = Path(raw)
    if p.is_absolute():
        return p

    _MAP = {
        "desktop": home / "Desktop",     "escritorio": home / "Desktop",
        "downloads": home / "Downloads", "descargas":  home / "Downloads",
        "documents": home / "Documents", "documentos": home / "Documents",
        "pictures":  home / "Pictures",  "imagenes":   home / "Pictures",
    }
    parts = raw.replace("\\", "/").split("/", 1)
    first = parts[0].lower()
    rest  = parts[1] if len(parts) > 1 else ""
    if first in _MAP:
        return _MAP[first] / rest if rest else _MAP[first]

    # Búsqueda en carpetas comunes
    for root in [home / "Desktop", home / "Downloads", home / "Documents", home]:
        candidate = root / raw
        if candidate.exists():
            return candidate
    return p

def _copy_file_to_clipboard(file_path: str) -> bool:
    """Copia un archivo al portapapeles como FileDrop (compatible con WhatsApp Web)."""
    try:
        safe = str(file_path).replace("'", "''")
        ps   = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$c = New-Object System.Collections.Specialized.StringCollection; "
            f"$c.Add('{safe}'); "
            "[System.Windows.Forms.Clipboard]::SetFileDropList($c)"
        )
        subprocess.run(
            ["powershell", "-Sta", "-NoProfile", "-Command", ps],
            check=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10
        )
        return True
    except Exception as e:
        print(f"[WhatsApp] Error copiando al portapapeles: {e}")
        return False

def _navigate_to_contact(phone: str, receiver: str, target_desc: str,
                          contacts: dict, player=None) -> bool:
    """
    Abre WhatsApp Web en el chat del contacto indicado.
    Devuelve True si se pudo navegar, False si hubo error.
    """
    import pygetwindow as gw

    wsp_window = None
    for win in gw.getAllWindows():
        t = win.title.lower()
        if "whatsapp" in t and any(b in t for b in ("chrome","opera","edge","brave","firefox")):
            wsp_window = win
            break

    if wsp_window:
        if player:
            try: player.write_log(f"💬 Navegando en pestaña WhatsApp abierta → {target_desc}")
            except: pass
        try:
            if wsp_window.isMinimized:
                wsp_window.restore()
            wsp_window.activate()
        except: pass
        time.sleep(1)

        # Buscar contacto con Ctrl+Alt+/
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(1.2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        pyautogui.press("backspace")
        time.sleep(0.4)
        pyautogui.write(target_desc, interval=0.02)
        time.sleep(2.2)
        pyautogui.press("enter")
        time.sleep(1.2)
        return True
    else:
        # Abrir WhatsApp Web con URL directa
        encoded_msg = ""
        if phone:
            url = f"https://web.whatsapp.com/send?phone={phone}"
        else:
            url = "https://web.whatsapp.com"

        if player:
            try: player.write_log(f"💬 Abriendo WhatsApp Web → {target_desc}")
            except: pass

        webbrowser.open(url)
        time.sleep(13)   # Esperar carga

        if not phone:
            pyautogui.hotkey("ctrl", "alt", "/")
            time.sleep(1.2)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.press("backspace")
            time.sleep(0.4)
            pyautogui.write(target_desc, interval=0.02)
            time.sleep(2.5)
            pyautogui.press("enter")
            time.sleep(1.5)
        return True

def _resolve_phone(receiver: str, contacts: dict) -> tuple[str, str]:
    """Devuelve (phone, contact_name) dado un receiver."""
    cleaned  = "".join(c for c in receiver if c.isdigit() or c == "+")
    n_digits = sum(c.isdigit() for c in cleaned)
    if n_digits >= 8:
        return cleaned.replace("+", ""), receiver

    match = contacts.get(receiver.lower())
    if match:
        return match["phone"], match["name"]

    for k, v in contacts.items():
        if receiver.lower() in k or k in receiver.lower():
            return v["phone"], v["name"]

    return "", receiver


# ── Función principal ─────────────────────────────────────────────────────────

def whatsapp(parameters: dict, player=None) -> str:
    """
    Control completo de WhatsApp Web.
    Acciones: send | send_image | send_document | read | unread |
              add_contact | list_contacts | delete_contact
    """
    action   = parameters.get("action", "").lower().strip()
    receiver = parameters.get("receiver", "").strip()

    # Aliases
    if action == "send_text":  action = "send"
    if action in ("read_unread", "read_chat", "unread"): action = "read"

    contacts = load_contacts()

    # ── GESTIÓN DE CONTACTOS ──────────────────────────────────────────────────
    if action == "add_contact":
        name_c  = parameters.get("name", receiver).strip()
        phone_c = "".join(filter(str.isdigit, parameters.get("phone", "").strip()))
        if not name_c or not phone_c:
            return "Error: Se requiere 'name' y 'phone' para agregar un contacto."
        contacts[name_c.lower()] = {"name": name_c, "phone": phone_c}
        save_contacts(contacts)
        return f"Contacto '{name_c}' guardado con teléfono {phone_c}."

    elif action == "delete_contact":
        name_c = parameters.get("name", receiver).strip()
        if name_c.lower() in contacts:
            del contacts[name_c.lower()]
            save_contacts(contacts)
            return f"Contacto '{name_c}' eliminado."
        return f"No se encontró el contacto '{name_c}'."

    elif action == "list_contacts":
        if not contacts:
            return "No hay contactos guardados en JARVIS."
        return "Contactos:\n" + "\n".join(f"• {v['name']}: {v['phone']}" for v in contacts.values())

    # ── ENVÍO ─────────────────────────────────────────────────────────────────
    elif action in ("send", "send_image", "send_document"):
        if not receiver:
            return "Error: Falta el destinatario ('receiver')."
        if not pyautogui:
            return "Error: pyautogui no está instalado."

        phone, target_desc = _resolve_phone(receiver, contacts)
        message    = clean_text(parameters.get("message", ""))
        caption    = clean_text(parameters.get("caption", ""))
        image_path = parameters.get("image_path", "").strip()
        file_path  = parameters.get("file_path", "").strip()

        # Navegar al contacto
        ok = _navigate_to_contact(phone, receiver, target_desc, contacts, player)
        if not ok:
            return f"No se pudo navegar al chat de '{target_desc}'."

        # ── ENVIAR MENSAJE DE TEXTO ───────────────────────────────────────
        if action == "send":
            if not message:
                return "Error: Falta el mensaje ('message')."
            pyautogui.write(message, interval=0.02)
            time.sleep(0.4)
            pyautogui.press("enter")
            time.sleep(0.8)
            if player:
                try: player.write_log(f"✅ Mensaje enviado a {target_desc}")
                except: pass
            return f"Mensaje enviado a '{target_desc}' por WhatsApp."

        # ── ENVIAR IMAGEN ─────────────────────────────────────────────────
        elif action == "send_image":
            img_p = _resolve_file_path(image_path) if image_path else Path()
            if not img_p.exists():
                return f"Error: No se encontró la imagen en '{image_path}'."

            # Copiar imagen al portapapeles como DIB (bitmap)
            try:
                import ctypes
                from PIL import Image
                import io as _io

                image = Image.open(img_p)
                buf   = _io.BytesIO()
                image.convert("RGB").save(buf, "BMP")
                data  = buf.getvalue()[14:]
                buf.close()

                ctypes.windll.user32.OpenClipboard(None)
                ctypes.windll.user32.EmptyClipboard()
                h = ctypes.windll.kernel32.GlobalAlloc(0x0002, len(data))
                p = ctypes.windll.kernel32.GlobalLock(h)
                ctypes.cdll.msvcrt.memcpy(p, data, len(data))
                ctypes.windll.kernel32.GlobalUnlock(h)
                ctypes.windll.user32.SetClipboardData(8, h)
                ctypes.windll.user32.CloseClipboard()
            except Exception as e:
                return f"Error copiando imagen al portapapeles: {e}"

            time.sleep(0.5)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(3.0)
            if caption:
                pyautogui.write(caption, interval=0.02)
                time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(1.0)
            if player:
                try: player.write_log(f"✅ Imagen enviada a {target_desc}")
                except: pass
            return f"Imagen enviada a '{target_desc}' vía WhatsApp."

        # ── ENVIAR DOCUMENTO ──────────────────────────────────────────────
        elif action == "send_document":
            fp = _resolve_file_path(file_path) if file_path else Path()
            if not fp.exists() or not fp.is_file():
                return (
                    f"Error: No se encontró el archivo '{file_path}'. "
                    "Verifica que la ruta sea correcta."
                )

            if player:
                try: player.write_log(f"📎 Enviando documento '{fp.name}' a {target_desc}...")
                except: pass

            # ── MÉTODO PRINCIPAL: Botón 📎 → Document → Diálogo de Windows ───
            try:
                # Cargar coordenadas calibradas
                coords_file = BASE_DIR / "config" / "whatsapp_coords.json"
                attach_x, attach_y = 702, 979   # calibrados para esta PC
                doc_x,    doc_y    = 707, 601

                if coords_file.exists():
                    try:
                        _c = json.loads(coords_file.read_text(encoding="utf-8"))
                        attach_x = _c["attach_button"]["x"]
                        attach_y = _c["attach_button"]["y"]
                        doc_x    = _c["document_item"]["x"]
                        doc_y    = _c["document_item"]["y"]
                    except Exception:
                        pass

                # 1. Clic en el campo de mensaje para dar foco al chat
                pyautogui.click(attach_x + 300, attach_y)
                time.sleep(0.5)

                # 2. Clic en el botón 📎
                pyautogui.click(attach_x, attach_y)
                time.sleep(1.5)

                # 3. Clic en "Documento" del menú
                pyautogui.click(doc_x, doc_y)
                time.sleep(1.8)

                # 4. Se abre diálogo de Windows "Abrir archivo"
                #    Escribir la ruta completa directamente
                #    Primero limpiar el campo con Ctrl+A, luego escribir
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.3)
                pyautogui.hotkey("ctrl", "a")  # doble por si acaso
                time.sleep(0.2)

                # Escribir la ruta carácter por carácter es más seguro
                # con pyperclip para evitar problemas con caracteres especiales
                try:
                    import pyperclip
                    pyperclip.copy(str(fp))
                    pyautogui.hotkey("ctrl", "v")
                except Exception:
                    pyautogui.write(str(fp), interval=0.03)

                time.sleep(0.4)
                pyautogui.press("enter")
                time.sleep(3.5)  # Esperar que WhatsApp cargue el preview del doc

                # 5. Agregar caption si se proporcionó
                if caption:
                    pyautogui.write(caption, interval=0.02)
                    time.sleep(0.3)

                # 6. Enviar
                pyautogui.press("enter")
                time.sleep(1.5)

                if player:
                    try: player.write_log(f"✅ Documento '{fp.name}' enviado a {target_desc}")
                    except: pass
                return f"Documento '{fp.name}' enviado a '{target_desc}' vía WhatsApp."

            except Exception as e_m2:
                print(f"[WhatsApp] Método botón 📎 falló: {e_m2}")

            # ── FALLBACK: FileDrop clipboard ──────────────────────────────
            try:
                if _copy_file_to_clipboard(str(fp)):
                    time.sleep(0.5)
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(4.0)
                    if caption:
                        pyautogui.write(caption, interval=0.02)
                        time.sleep(0.3)
                    pyautogui.press("enter")
                    time.sleep(1.5)
                    return f"Documento '{fp.name}' enviado (método clipboard) a '{target_desc}'."
            except Exception as e_fb:
                pass

            return (
                f"No se pudo enviar '{fp.name}' automáticamente. "
                f"Abrí WhatsApp Web, presioná el botón 📎, elegí 'Documento' "
                f"y seleccioná el archivo desde: {fp}"
            )

    # ── LEER ─────────────────────────────────────────────────────────────────
    elif action == "read":
        webbrowser.open("https://web.whatsapp.com")
        return "Abriendo WhatsApp Web para visualizar tus chats."

    else:
        webbrowser.open("https://web.whatsapp.com")
        return f"Abriendo WhatsApp Web (acción: {action})."
