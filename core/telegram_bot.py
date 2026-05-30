import sys
import json
import threading
import asyncio
import requests
import time
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import socket
_old_getaddrinfo = socket.getaddrinfo
def _new_getaddrinfo(*args, **kwargs):
    if len(args) > 0 and isinstance(args[0], str) and "telegram.org" in args[0]:
        kwargs['family'] = socket.AF_INET
    return _old_getaddrinfo(*args, **kwargs)
socket.getaddrinfo = _new_getaddrinfo

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
    except:
        return {}

chat_histories = {}

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = get_config()
    chat_id = cfg.get("telegram_chat_id", "")
    
    if str(update.effective_chat.id) != str(chat_id):
        print(f"[Telegram] Acceso denegado a ID: {update.effective_chat.id}")
        return
        
    chat_histories[str(chat_id)] = []
    await update.message.reply_text("Hola señor. Sus sistemas en línea con motor DeepSeek. ¿En qué puedo ayudarle?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = get_config()
    chat_id = str(cfg.get("telegram_chat_id", ""))
    
    if str(update.effective_chat.id) != chat_id:
        print(f"[Telegram] Intento de acceso denegado. ID no autorizado: {update.effective_chat.id}")
        return
        
    user_text = update.message.text
    if not user_text:
        return
        
    tel_ai = cfg.get("telegram_ai_provider", "deepseek")
    
    if tel_ai == "groq":
        api_key = cfg.get("groq_api_key", "")
        if not api_key:
            await update.message.reply_text("Advertencia: Groq API Key no configurada en los ajustes de JARVIS.")
            return
        motor_name = "Groq"
    else:
        api_key = cfg.get("deepseek_api_key", "")
        if not api_key:
            await update.message.reply_text("Advertencia: DeepSeek API Key no configurada en los ajustes de JARVIS.")
            return
        motor_name = "DeepSeek"
        
    from memory.memory_manager import load_memory, format_memory_for_prompt
    mem = load_memory()
    mem_prompt = format_memory_for_prompt(mem)
    
    from datetime import datetime
    now_str = datetime.now().strftime("%A, %d %B %Y - %I:%M:%S %p")
    
    import ctypes
    screen_count = ctypes.windll.user32.GetSystemMetrics(80)
    if screen_count > 1:
        screen_rule = (
            "REGLA DE CAPTURAS: El usuario tiene múltiples pantallas. Si pide una captura, NO la tomes de inmediato. "
            "Pregúntale primero: '¿Desea la pantalla 1, la pantalla 2 o combinada?'. Solo cuando el usuario te "
            "responda especificando, ejecuta la herramienta take_screenshot.\n\n"
        )
    else:
        screen_rule = (
            "REGLA DE CAPTURAS: El usuario tiene 1 sola pantalla. Cuando pida una captura, ejecuta la herramienta "
            "take_screenshot de inmediato (screen='combined'). NO le preguntes nada sobre qué pantalla elegir.\n\n"
        )
    
    system_instruction = (
        "Eres JARVIS, el asistente de inteligencia artificial de Tony Stark. "
        "Estás respondiendo directamente a través de un chat seguro de Telegram al usuario. "
        f"Usa modelo {motor_name}. Proporciona respuestas concisas, naturales y serviciales.\n\n"
        f"[IMPORTANTE - HORA ACTUAL]: El sistema indica que en este preciso momento es: {now_str}. Usa esta hora para cualquier pregunta relacionada.\n\n"
        f"{screen_rule}"
        f"{mem_prompt}"
    )
    
    if chat_id not in chat_histories or not chat_histories[chat_id]:
        chat_histories[chat_id] = [{"role": "system", "content": system_instruction}]
    else:
        # Siempre actualizar la instrucción de sistema con la hora más reciente
        if chat_histories[chat_id] and chat_histories[chat_id][0].get("role") == "system":
            chat_histories[chat_id][0]["content"] = system_instruction
        
    # Appending user message
    chat_histories[chat_id].append({"role": "user", "content": user_text})
    
    if len(chat_histories[chat_id]) > 20:
        history = chat_histories[chat_id]
        cut_index = -15
        # Evitar cortar el historial en medio de un tool_call y su respuesta (causa Error 400)
        while cut_index < -1 and history[cut_index].get("role") != "user":
            cut_index += 1
        chat_histories[chat_id] = [history[0]] + history[cut_index:]
        
    tools = [
        {
            "type": "function",
            "function": {
                "name": "telegram_send_file_whatsapp",
                "description": "Busca un archivo en el PC y lo envía por WhatsApp a un contacto.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "contact": {"type": "string"}
                    },
                    "required": ["filename", "contact"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Toma una captura de la pantalla física del PC. REQUIERE que le pases el parámetro 'screen' como '1', '2' o 'combined'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "screen": {"type": "string", "description": "Debe ser '1', '2' o 'combined'"}
                    },
                    "required": ["screen"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "media_control",
                "description": "Controla la reproducción multimedia del sistema (Spotify, YouTube, etc) usando teclas nativas, incluso si la app está en segundo plano.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sub_action": {"type": "string", "description": "Debe ser: 'play_pause', 'next_track', 'prev_track', 'mute', 'volume_up', 'volume_down'"}
                    },
                    "required": ["sub_action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Busca archivos o carpetas en el disco duro local de la PC en una ruta específica y devuelve una lista numerada de resultados con sus rutas exactas.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Ruta donde buscar, ej: 'home/Desktop', 'home/Documents', 'home/Downloads', o 'C:\\\\'"},
                        "name": {"type": "string", "description": "Parte del nombre del archivo o carpeta a buscar."},
                        "extension": {"type": "string", "description": "Extensión opcional (ej: '.pdf', '.xlsx')."}
                    },
                    "required": ["path", "name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "video_seek",
                "description": "Adelanta o retrocede un video en YouTube o cualquier reproductor web enviando pulsaciones rápidas de teclas direccionales.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seconds": {"type": "string", "description": "Cantidad de segundos a adelantar (positivo) o retroceder (negativo). Ejemplo: '10 segundos', '-5 segundos'"}
                    },
                    "required": ["seconds"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_app",
                "description": "Abre cualquier aplicación, programa o carpeta en la computadora (ej. Word, Excel, Chrome, Explorador de Archivos, Spotify).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "Nombre exacto de la aplicación o programa a abrir (ej. 'Word', 'Chrome', 'explorer')"}
                    },
                    "required": ["app_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "Escribe texto físicamente en la computadora usando el teclado (pyautogui).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "El texto exacto que debes escribir."}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "window_control",
                "description": "Maximiza, minimiza, cierra o mueve ventanas en la PC del usuario (ej: opera, chrome). También puede cerrar pestañas (close_tab).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sub_action": {"type": "string", "description": "maximize | minimize | close | close_tab | move_monitor"},
                        "target": {"type": "string", "description": "Nombre de la app (ej: opera)"},
                        "monitor": {"type": "string", "description": "Número de monitor (1 o 2) solo para move_monitor"}
                    },
                    "required": ["sub_action", "target"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "app_macro",
                "description": "Automatiza clics paso a paso en programas (ej. cambiar fuente/tamaño en Word).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app": {"type": "string", "description": "Nombre de la aplicación (ej: Word)"},
                        "action": {"type": "string", "description": "Macro a ejecutar: change_font"},
                        "font_name": {"type": "string", "description": "Nombre de la fuente (ej: Arial)"},
                        "font_size": {"type": "string", "description": "Tamaño de la fuente (ej: 11)"}
                    },
                    "required": ["app", "action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_time",
                "description": "Obtiene la fecha y hora exacta actual. Úsalo siempre que el usuario pregunte la hora.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]

    try:
        status_msg = await update.message.reply_text("⏳ Conectando con DeepSeek...")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        loop = asyncio.get_running_loop()
        def _call_ai(messages):
            if tel_ai == "groq":
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                payload = {
                    "model": "llama3-70b-8192", 
                    "messages": messages,
                    "tools": tools,
                    "max_tokens": 1000
                }
            else:
                url = "https://api.deepseek.com/chat/completions"
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                payload = {
                    "model": "deepseek-chat", # deepseek-chat supports tools, reasoner doesn't
                    "messages": messages,
                    "tools": tools,
                    "max_tokens": 1000
                }
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"[DeepSeek/Groq ERROR] Status: {resp.status_code}")
                print(f"[DeepSeek/Groq ERROR] Response: {resp.text}")
                raise e
            return resp.json()
            
        for _ in range(4): # Loop for tool chains
            response_data = await loop.run_in_executor(None, _call_ai, chat_histories[chat_id])
            message_obj = response_data.get("choices", [{}])[0].get("message", {})
            
            # Prevenir Error 400 Bad Request: Limpiar campos extra del asistente
            clean_msg = {"role": message_obj.get("role", "assistant")}
            
            if message_obj.get("content") is not None:
                clean_msg["content"] = message_obj.get("content")
            else:
                clean_msg["content"] = ""
                
            if message_obj.get("tool_calls"):
                clean_msg["tool_calls"] = message_obj["tool_calls"]
                
            chat_histories[chat_id].append(clean_msg)
            
            if message_obj.get("tool_calls"):
                for tool_call in message_obj["tool_calls"]:
                    func_name = tool_call.get("function", {}).get("name")
                    try:
                        args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                    except:
                        args = {}
                        
                    tool_result = ""
                    
                    if func_name == "telegram_send_file_whatsapp":
                        from actions.file_controller import file_controller
                        from actions.whatsapp import whatsapp
                        f_res = file_controller({"action": "find", "filename": args.get("filename", ""), "copy_to_clipboard": True})
                        if "No se encontró" in f_res or "falló" in f_res:
                            tool_result = f_res
                        else:
                            w_res = whatsapp({"action": "send", "receiver": args.get("contact", ""), "paste_clipboard": True})
                            tool_result = f"Archivo encontrado y proceso completado: {w_res}"
                            
                    elif func_name == "take_screenshot":
                        from actions.computer_control import computer_control
                        res = computer_control({"action": "take_screenshot", "screen": args.get("screen", "combined")})
                        if "SCREENSHOT_SAVED:" in res:
                            path = res.split("SCREENSHOT_SAVED:")[1]
                            try:
                                with open(path, 'rb') as f:
                                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f)
                                tool_result = "La captura ha sido tomada y enviada con éxito al chat de Telegram."
                            except Exception as e:
                                tool_result = f"Error subiendo la foto a Telegram: {e}"
                        else:
                            tool_result = res
                            
                    elif func_name == "window_control":
                        from actions.computer_control import computer_control
                        tool_result = computer_control({
                            "action": "window_control", 
                            "sub_action": args.get("sub_action", ""), 
                            "target": args.get("target", ""),
                            "monitor": args.get("monitor", "1")
                        })
                    elif func_name == "open_app":
                        from actions.open_app import open_app
                        tool_result = open_app({"app_name": args.get("app_name", "")})
                    elif func_name == "type_text":
                        import pyautogui
                        text_to_type = args.get("text", "")
                        if text_to_type:
                            pyautogui.write(text_to_type, interval=0.01)
                            tool_result = f"Texto escrito con éxito: '{text_to_type}'"
                        else:
                            tool_result = "Error: No se proporcionó texto para escribir."
                    elif func_name == "media_control":
                        from actions.computer_control import computer_control
                        tool_result = computer_control({
                            "action": "media_control",
                            "sub_action": args.get("sub_action", "")
                        })
                    elif func_name == "video_seek":
                        from actions.computer_control import computer_control
                        tool_result = computer_control({
                            "action": "seek",
                            "sub_action": "seek",
                            "seconds": str(args.get("seconds", "10"))
                        })
                    elif func_name == "search_files":
                        from actions.file_controller import file_controller
                        tool_result = file_controller({
                            "action": "find",
                            "path": args.get("path", ""),
                            "name": args.get("name", ""),
                            "extension": args.get("extension", "")
                        })
                    elif func_name == "app_macro":
                        from actions.app_macro import app_macro
                        tool_result = app_macro({
                            "app": args.get("app", ""),
                            "action": args.get("action", ""),
                            "font_name": args.get("font_name", ""),
                            "font_size": args.get("font_size", "")
                        })
                    elif func_name == "check_time":
                        import datetime
                        now = datetime.datetime.now()
                        tool_result = f"La hora y fecha exacta del sistema es: {now.strftime('%A, %d %B %Y - %I:%M:%S %p')}"
                    else:
                        tool_result = "Función no encontrada."
                        
                    chat_histories[chat_id].append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(tool_result)
                    })
            else:
                reply_text = message_obj.get("content", "")
                if reply_text:
                    try:
                        await status_msg.delete()
                    except: pass
                    await update.message.reply_text(reply_text)
                break
                
    except Exception as e:
        try: await status_msg.delete()
        except: pass
        await update.message.reply_text(f"Se ha producido un error interno con DeepSeek: {e}")

def run_telegram_bot():
    cfg = get_config()
    token = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    
    if not token or not chat_id:
        print("[Telegram] Bot token o Chat ID faltantes. El servicio se mantendrá inactivo.")
        return
        
    print(f"[Telegram] Iniciando bot (DeepSeek Powered) para el chat {chat_id}...")
    try:
        app = (
            ApplicationBuilder()
            .token(token)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .get_updates_connect_timeout(30.0)
            .get_updates_read_timeout(60.0)
            .build()
        )
        
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        app.run_polling(close_loop=False)
    except Exception as e:
        print(f"[Telegram] Error crítico al iniciar el bot: {e}")

def start_telegram_listener():
    t = threading.Thread(target=run_telegram_bot, daemon=True, name="TelegramListener")
    t.start()
