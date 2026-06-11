"""
core/telegram_bot.py — Control remoto de JARVIS vía Telegram.

SIN dependencia de python-telegram-bot: usa la API HTTP de Telegram
directamente con `requests` (long polling getUpdates). Esto elimina el
error "No module named 'telegram'" del arranque.

Funciones desde el teléfono:
  • Conversación con DeepSeek/Groq con memoria
  • Capturas de pantalla del PC
  • Abrir apps, controlar multimedia, escribir texto
  • Buscar archivos y enviarlos por WhatsApp
  • Estado de tareas en curso ("¿en qué vas?")
  • Lanzar investigaciones (deep_research) remotamente
"""
import sys
import json
import threading
import time
from pathlib import Path

import requests


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def get_config():
    if not API_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


chat_histories = {}
_stop_event = threading.Event()


# ══════════════════════════════════════════════════════════════════════════════
#  CLIENTE TELEGRAM HTTP (sin dependencias)
# ══════════════════════════════════════════════════════════════════════════════

class TelegramAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self._offset = 0

    def get_updates(self, timeout: int = 50) -> list[dict]:
        try:
            r = requests.get(
                f"{self.base}/getUpdates",
                params={"offset": self._offset, "timeout": timeout,
                        "allowed_updates": json.dumps(["message"])},
                timeout=timeout + 10,
            )
            data = r.json()
            updates = data.get("result", [])
            if updates:
                self._offset = updates[-1]["update_id"] + 1
            return updates
        except requests.exceptions.Timeout:
            return []
        except Exception as e:
            print(f"[Telegram] getUpdates error: {e}")
            time.sleep(5)
            return []

    def send_message(self, chat_id, text: str):
        # Telegram limita 4096 chars por mensaje
        for chunk_start in range(0, len(text), 4000):
            chunk = text[chunk_start:chunk_start + 4000]
            try:
                requests.post(f"{self.base}/sendMessage",
                              json={"chat_id": chat_id, "text": chunk}, timeout=30)
            except Exception as e:
                print(f"[Telegram] sendMessage error: {e}")

    def send_photo(self, chat_id, photo_path: str):
        try:
            with open(photo_path, "rb") as f:
                requests.post(f"{self.base}/sendPhoto",
                              data={"chat_id": chat_id},
                              files={"photo": f}, timeout=60)
            return True
        except Exception as e:
            print(f"[Telegram] sendPhoto error: {e}")
            return False

    def send_document(self, chat_id, file_path: str):
        try:
            with open(file_path, "rb") as f:
                requests.post(f"{self.base}/sendDocument",
                              data={"chat_id": chat_id},
                              files={"document": f}, timeout=120)
            return True
        except Exception as e:
            print(f"[Telegram] sendDocument error: {e}")
            return False

    def send_typing(self, chat_id):
        try:
            requests.post(f"{self.base}/sendChatAction",
                          json={"chat_id": chat_id, "action": "typing"}, timeout=10)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  HERRAMIENTAS DISPONIBLES DESDE TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {"type": "function", "function": {
        "name": "telegram_send_file_whatsapp",
        "description": "Busca un archivo en el PC y lo envía por WhatsApp a un contacto.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"}, "contact": {"type": "string"}},
            "required": ["filename", "contact"]}}},
    {"type": "function", "function": {
        "name": "take_screenshot",
        "description": "Toma una captura de la pantalla del PC. Parámetro screen: '1', '2' o 'combined'.",
        "parameters": {"type": "object", "properties": {
            "screen": {"type": "string"}}, "required": ["screen"]}}},
    {"type": "function", "function": {
        "name": "media_control",
        "description": "Controla multimedia del PC: play_pause, next_track, prev_track, mute, volume_up, volume_down.",
        "parameters": {"type": "object", "properties": {
            "sub_action": {"type": "string"}}, "required": ["sub_action"]}}},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "Busca archivos en el PC. path: 'home/Desktop', 'home/Documents', 'home/Downloads' o ruta absoluta.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "name": {"type": "string"},
            "extension": {"type": "string"}}, "required": ["path", "name"]}}},
    {"type": "function", "function": {
        "name": "open_app",
        "description": "Abre cualquier aplicación o programa en el PC.",
        "parameters": {"type": "object", "properties": {
            "app_name": {"type": "string"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {
        "name": "window_control",
        "description": "Maximiza/minimiza/cierra ventanas. sub_action: maximize|minimize|close|close_tab|move_monitor.",
        "parameters": {"type": "object", "properties": {
            "sub_action": {"type": "string"}, "target": {"type": "string"},
            "monitor": {"type": "string"}}, "required": ["sub_action", "target"]}}},
    {"type": "function", "function": {
        "name": "type_text",
        "description": "Escribe texto físicamente en el PC con el teclado.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "check_time",
        "description": "Obtiene fecha y hora actual del PC.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "task_status",
        "description": "Estado de las tareas en segundo plano de JARVIS (investigaciones, etc). Usar cuando pregunten '¿en qué vas?' o '¿cómo va X?'.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "deep_research",
        "description": "Lanza una investigación larga en el PC que genera un documento Word profesional. Corre en segundo plano.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string"},
            "target_pages": {"type": "integer"}},
            "required": ["topic"]}}},
    {"type": "function", "function": {
        "name": "send_file_to_telegram",
        "description": "Envía un archivo del PC directamente a este chat de Telegram. Útil tras buscar un archivo o terminar una investigación.",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Ruta absoluta del archivo"}},
            "required": ["file_path"]}}},
]


def _execute_tool(func_name: str, args: dict, api: TelegramAPI, chat_id) -> str:
    """Ejecutar una herramienta llamada desde Telegram."""
    try:
        if func_name == "telegram_send_file_whatsapp":
            from actions.file_controller import file_controller
            from actions.whatsapp import whatsapp
            f_res = file_controller({"action": "find", "filename": args.get("filename", ""),
                                     "copy_to_clipboard": True})
            if "No se encontró" in f_res or "falló" in f_res:
                return f_res
            w_res = whatsapp({"action": "send", "receiver": args.get("contact", ""),
                              "paste_clipboard": True})
            return f"Archivo encontrado y proceso completado: {w_res}"

        if func_name == "take_screenshot":
            from actions.computer_control import computer_control
            res = computer_control({"action": "take_screenshot",
                                    "screen": args.get("screen", "combined")})
            if "SCREENSHOT_SAVED:" in res:
                path = res.split("SCREENSHOT_SAVED:")[1].strip()
                if api.send_photo(chat_id, path):
                    return "Captura tomada y enviada al chat."
                return "Captura tomada pero falló el envío a Telegram."
            return res

        if func_name == "media_control":
            from actions.computer_control import computer_control
            return computer_control({"action": "media_control",
                                     "sub_action": args.get("sub_action", "")})

        if func_name == "search_files":
            from actions.file_controller import file_controller
            return file_controller({"action": "find", "path": args.get("path", ""),
                                    "name": args.get("name", ""),
                                    "extension": args.get("extension", "")})

        if func_name == "open_app":
            from actions.open_app import open_app
            return open_app({"app_name": args.get("app_name", "")})

        if func_name == "window_control":
            from actions.computer_control import computer_control
            return computer_control({"action": "window_control",
                                     "sub_action": args.get("sub_action", ""),
                                     "target": args.get("target", ""),
                                     "monitor": args.get("monitor", "1")})

        if func_name == "type_text":
            import pyautogui
            text = args.get("text", "")
            if not text:
                return "Error: sin texto."
            pyautogui.write(text, interval=0.01)
            return f"Texto escrito: '{text}'"

        if func_name == "check_time":
            import datetime
            return datetime.datetime.now().strftime("%A, %d %B %Y - %I:%M:%S %p")

        if func_name == "task_status":
            try:
                from core.task_queue import summary_for_voice, list_tasks
                lines = [summary_for_voice()]
                for t in list_tasks(limit=5):
                    prog = f" — {t.progress}" if t.progress else ""
                    lines.append(f"• {t.title} [{t.status}]{prog}")
                return "\n".join(lines)
            except Exception as e:
                return f"Error consultando tareas: {e}"

        if func_name == "deep_research":
            try:
                from actions.deep_research import deep_research
                return deep_research({
                    "topic": args.get("topic", ""),
                    "target_pages": args.get("target_pages", 15),
                    "background": True,
                })
            except Exception as e:
                return f"Error lanzando investigación: {e}"

        if func_name == "send_file_to_telegram":
            fp = args.get("file_path", "")
            if not fp or not Path(fp).exists():
                return f"Archivo no encontrado: {fp}"
            if api.send_document(chat_id, fp):
                return "Archivo enviado al chat."
            return "Falló el envío del archivo."

        return "Función no encontrada."
    except Exception as e:
        return f"Error ejecutando {func_name}: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  CONVERSACIÓN (DeepSeek / Groq con tool-calling)
# ══════════════════════════════════════════════════════════════════════════════

def _build_system_instruction(motor_name: str) -> str:
    from datetime import datetime
    now_str = datetime.now().strftime("%A, %d %B %Y - %I:%M:%S %p")
    mem_prompt = ""
    try:
        from memory.memory_manager import load_memory, format_memory_for_prompt
        mem_prompt = format_memory_for_prompt(load_memory())
    except Exception:
        pass

    screen_rule = ""
    try:
        import ctypes
        if ctypes.windll.user32.GetSystemMetrics(80) > 1:
            screen_rule = ("REGLA DE CAPTURAS: hay múltiples pantallas — pregunta "
                           "'¿pantalla 1, 2 o combinada?' antes de capturar.\n\n")
        else:
            screen_rule = ("REGLA DE CAPTURAS: 1 sola pantalla — captura de inmediato "
                           "con screen='combined' sin preguntar.\n\n")
    except Exception:
        pass

    return (
        "Eres JARVIS, asistente de IA del usuario, respondiendo por Telegram desde su PC. "
        f"Motor: {motor_name}. Respuestas concisas y serviciales en español.\n\n"
        f"[HORA ACTUAL]: {now_str}\n\n"
        f"{screen_rule}{mem_prompt}"
    )


def _call_ai(messages: list, tel_ai: str, api_key: str) -> dict:
    if tel_ai == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        model = "llama3-70b-8192"
    else:
        url = "https://api.deepseek.com/chat/completions"
        model = "deepseek-chat"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "tools": TOOLS, "max_tokens": 1000},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()


def _handle_text(api: TelegramAPI, chat_id, user_text: str):
    cfg = get_config()
    tel_ai = cfg.get("telegram_ai_provider", "deepseek")
    api_key = cfg.get("groq_api_key" if tel_ai == "groq" else "deepseek_api_key", "")
    motor_name = "Groq" if tel_ai == "groq" else "DeepSeek"

    if not api_key:
        api.send_message(chat_id, f"Advertencia: {motor_name} API Key no configurada en JARVIS.")
        return

    cid = str(chat_id)
    system_instruction = _build_system_instruction(motor_name)
    if cid not in chat_histories or not chat_histories[cid]:
        chat_histories[cid] = [{"role": "system", "content": system_instruction}]
    else:
        chat_histories[cid][0]["content"] = system_instruction

    chat_histories[cid].append({"role": "user", "content": user_text})

    # Trim del historial — sin cortar tool_call/respuesta a la mitad
    if len(chat_histories[cid]) > 20:
        history = chat_histories[cid]
        cut_index = -15
        while cut_index < -1 and history[cut_index].get("role") != "user":
            cut_index += 1
        chat_histories[cid] = [history[0]] + history[cut_index:]

    api.send_typing(chat_id)

    try:
        for _ in range(4):   # cadena de hasta 4 tools
            response_data = _call_ai(chat_histories[cid], tel_ai, api_key)
            message_obj = response_data.get("choices", [{}])[0].get("message", {})

            clean_msg = {"role": message_obj.get("role", "assistant"),
                         "content": message_obj.get("content") or ""}
            if message_obj.get("tool_calls"):
                clean_msg["tool_calls"] = message_obj["tool_calls"]
            chat_histories[cid].append(clean_msg)

            if message_obj.get("tool_calls"):
                for tool_call in message_obj["tool_calls"]:
                    func_name = tool_call.get("function", {}).get("name")
                    try:
                        args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                    except Exception:
                        args = {}
                    api.send_typing(chat_id)
                    tool_result = _execute_tool(func_name, args, api, chat_id)
                    chat_histories[cid].append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(tool_result),
                    })
            else:
                reply = message_obj.get("content", "")
                if reply:
                    api.send_message(chat_id, reply)
                break
    except Exception as e:
        api.send_message(chat_id, f"Error interno: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def run_telegram_bot():
    cfg = get_config()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id_cfg = str(cfg.get("telegram_chat_id", "")).strip()

    if not token or not chat_id_cfg:
        print("[Telegram] Token o Chat ID no configurados — servicio remoto inactivo (opcional).")
        return

    print(f"[Telegram] Bot remoto activo para chat {chat_id_cfg}.")
    api = TelegramAPI(token)

    while not _stop_event.is_set():
        updates = api.get_updates(timeout=50)
        for upd in updates:
            msg = upd.get("message") or {}
            from_chat = str((msg.get("chat") or {}).get("id", ""))
            if from_chat != chat_id_cfg:
                if from_chat:
                    print(f"[Telegram] Acceso denegado a chat ID: {from_chat}")
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            if text == "/start":
                chat_histories[from_chat] = []
                api.send_message(from_chat,
                                 "Hola señor. Sistemas en línea. ¿En qué puedo ayudarle?")
                continue
            # Procesar en hilo para no bloquear el polling
            threading.Thread(
                target=_handle_text, args=(api, from_chat, text), daemon=True
            ).start()


def start_telegram_listener():
    """Arrancar el listener en background — seguro de llamar siempre.
    Si no hay token configurado, simplemente queda inactivo."""
    cfg = get_config()
    if not cfg.get("telegram_bot_token", "").strip():
        # No imprimir error — es una función opcional
        return
    t = threading.Thread(target=run_telegram_bot, daemon=True, name="TelegramListener")
    t.start()


def stop_telegram_listener():
    _stop_event.set()
