import os
import json
import sys
import time
from pathlib import Path

# Load config early to determine GPU acceleration settings
_gpu_enabled = False
try:
    if getattr(sys, "frozen", False):
        _base_dir = Path(sys.executable).parent
    else:
        _base_dir = Path(__file__).resolve().parent
    _cfg_path = _base_dir / "config" / "api_keys.json"
    if _cfg_path.exists():
        _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
        _gpu_enabled = _cfg.get("gpu_acceleration", False)
except Exception:
    pass

if _gpu_enabled:
    # GPU / High Performance Mode: sustain rendering workload on GPU VRAM, maximize space size
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--ignore-gpu-blocklist "
        "--enable-gpu-rasterization "
        "--enable-zero-copy "
        "--num-raster-threads=4 "
        "--renderer-process-limit=1 "
        "--disable-site-isolation-trials "
        "--js-flags=--max-old-space-size=256"
    )
    # Enable hardware acceleration backends for Qt
    os.environ["QSG_RHI_BACKEND"] = "d3d11" # Force Direct3D 11 for hardware rendering on Windows
    os.environ["QSG_INFO"] = "1"
    print("[JARVIS] GPU Acceleration is ENABLED. Offloading RAM rendering workload to GPU.")
else:
    # Balanced low-RAM mode: Keep GPU hardware compositing enabled so glowing CSS effects and drop-shadows are rendered beautifully, but limit renderer processes and JS space size.
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--enable-low-end-device-mode "
        "--renderer-process-limit=1 "
        "--disable-site-isolation-trials "
        "--js-flags=--max-old-space-size=64 "
        "--disable-gpu-shader-disk-cache "
        "--disable-dev-shm-usage "
        "--disable-extensions "
        "--disable-sync "
        "--mute-audio"
    )
    print("[JARVIS] Using Balanced Low RAM GPU-Composited mode for beautiful fluid rendering.")

import asyncio
from concurrent.futures import ThreadPoolExecutor
from beta_config import is_pro_tool, check_daily_limit, increment_calls, pro_tool_message, daily_limit_message
import re
import threading
import json
import sys
try:
    import pygetwindow as gw
except ImportError:
    gw = None
from PyQt6.QtCore import QMetaObject, Qt

import traceback
from pathlib import Path

# --- PARCHE GLOBAL PARA ESCRITURA EN PYAUTOGUI ---
# Asegura que todas las acciones de escritura de JARVIS sean en minúsculas,
# sin tildes, y desactivando Bloq Mayús si el usuario lo dejó encendido.
try:
    import pyautogui
    import ctypes
    import unicodedata
    
    _original_write = pyautogui.write
    
    def _safe_write(message, *args, **kwargs):
        # 1. Apagar Bloq Mayús si está encendido
        VK_CAPITAL = 0x14
        if ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1:
            pyautogui.press('capslock')
            
        # 2. Convertir el texto a minúsculas
        msg = str(message).lower()
        
        # 3. Eliminar tildes y acentos (Normalización NFD y filtrado de marcas no espaciadas)
        msg = ''.join(c for c in unicodedata.normalize('NFD', msg) if unicodedata.category(c) != 'Mn')
        
        # 4. Escribir usando el método original
        return _original_write(msg, *args, **kwargs)
        
    pyautogui.write = _safe_write
    pyautogui.typewrite = _safe_write
except Exception as e:
    print(f"[Core] No se pudo aplicar el parche de escritura segura: {e}")
# ---------------------------------------------------

# ── Dedicated thread pool for tool execution — prevents starvation ────────────
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="jarvis-tool")

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BA_TZ = _ZoneInfo("America/Lima")
except Exception:
    from datetime import timezone as _tz, timedelta as _td
    _BA_TZ = _tz(_td(hours=-5))


def _load_tz():
    """Load timezone from api_keys.json config."""
    global _BA_TZ
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        tz_name = cfg.get("timezone", "")
        if tz_name:
            try:
                _BA_TZ = _ZoneInfo(tz_name)
                print(f"[TZ] Timezone loaded: {tz_name}")
            except Exception as e:
                print(f"[TZ] Failed to load '{tz_name}': {e}")
                # Fallback: try to find a common alias or partial match
                import zoneinfo as _zi
                available = _zi.available_timezones()
                # Try case-insensitive match
                tz_lower = tz_name.lower()
                for known in available:
                    if known.lower() == tz_lower:
                        _BA_TZ = _ZoneInfo(known)
                        print(f"[TZ] Matched '{tz_name}' → '{known}'")
                        break
                else:
                    # Try partial match (e.g., "Buenos_Aires" → "America/Argentina/Buenos_Aires")
                    parts = tz_name.replace("\\", "/").split("/")
                    short = parts[-1].lower() if parts else ""
                    for known in available:
                        if known.lower().endswith("/" + short):
                            _BA_TZ = _ZoneInfo(known)
                            print(f"[TZ] Partial match '{tz_name}' → '{known}'")
                            break
                    else:
                        from datetime import datetime as _dt
                        _BA_TZ = _dt.now().astimezone().tzinfo
                        print(f"[TZ] Falling back to system timezone: {_BA_TZ}")
    except Exception as e:
        print(f"[TZ] Error reading config: {e}")

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI

def _patch_settings_ui():
    pass

_patch_settings_ui()

from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)
from memory.memory_engine import (
    record_turn, remember as engine_remember,
    get_context_block, clear_recent_turns, get_stats as memory_stats,
)

# ── Mejoras integradas (logger, quota, tasks, sandbox, panel, hotkey) ─────────
try:
    from core.jarvis_logger import (
        log_info as _jlog_info, log_warn as _jlog_warn,
        log_error as _jlog_error, log_tool as _jlog_tool,
        log_session as _jlog_session, log_audio as _jlog_audio,
    )
except Exception:
    def _jlog_info(*a, **k): pass
    def _jlog_warn(*a, **k): pass
    def _jlog_error(*a, **k): pass
    def _jlog_tool(*a, **k): pass
    def _jlog_session(*a, **k): pass
    def _jlog_audio(*a, **k): pass

try:
    from core.quota_manager import is_quota_error as _is_quota_error, mark_exhausted as _mark_quota
except Exception:
    def _is_quota_error(e): return False
    def _mark_quota(*a, **k): pass

try:
    from core.task_queue import (
        submit as _task_submit, list_tasks as _task_list,
        summary_for_voice as _task_voice_summary,
        set_notify_callback as _task_set_notify,
    )
except Exception:
    def _task_submit(*a, **k): return None
    def _task_list(*a, **k): return []
    def _task_voice_summary(): return "Sistema de tareas no disponible."
    def _task_set_notify(cb): pass

try:
    from core.sandbox import classify_command as _sandbox_cmd, classify_paths as _sandbox_paths
except Exception:
    def _sandbox_cmd(c): return None
    def _sandbox_paths(o, p): return None

try:
    from core.activity_panel import ActivityPanel as _ActivityPanel, position_panel as _position_panel
except Exception:
    _ActivityPanel = None
    def _position_panel(p): pass

try:
    from core.global_hotkey import register_attention_hotkey as _register_hotkey
except Exception:
    def _register_hotkey(*a, **k): return False

try:
    from actions.file_processor import file_processor
except ImportError:
    file_processor = None
try:
    from actions.flight_finder     import flight_finder
except ImportError:
    flight_finder = None
try:
    from actions.open_app          import open_app
except ImportError:
    open_app = None
try:
    from actions.weather_report    import weather_action
except ImportError:
    weather_action = None
try:
    from actions.send_message      import send_message
except ImportError:
    send_message = None
try:
    from actions.reminder          import reminder
except ImportError:
    reminder = None
try:
    from actions.computer_settings import computer_settings
except ImportError:
    computer_settings = None
try:
    from actions.screen_vision import screen_vision
except ImportError:
    screen_vision = None
try:
    from actions.youtube_video     import youtube_video
except ImportError:
    youtube_video = None
try:
    from actions.desktop           import desktop_control
except ImportError:
    desktop_control = None
try:
    from actions.browser_control   import browser_control
except ImportError:
    browser_control = None
try:
    from actions.visual_click import visual_click
except ImportError:
    visual_click = None
try:
    from actions.file_controller   import file_controller
except ImportError:
    file_controller = None

try:
    from actions.code_helper import code_helper
except ImportError:
    code_helper = None

try:
    from actions.dev_agent         import dev_agent
except ImportError:
    dev_agent = None
try:
    from actions.web_search        import web_search as web_search_action
except ImportError:
    web_search_action = None
try:
    from actions.computer_control  import computer_control
except ImportError:
    computer_control = None
try:
    from actions.game_updater      import game_updater
except ImportError:
    game_updater = None
try:
    from actions.google_calendar   import google_calendar
except ImportError:
    google_calendar = None
try:
    from actions.spotify_control   import spotify_control
except ImportError:
    spotify_control = None
try:
    from actions.rgb_control       import rgb_control
except ImportError:
    rgb_control = None
try:
    from actions.scheduler         import scheduler, start_runner
except ImportError:
    scheduler = None; start_runner = None
try:
    from actions.google_drive      import google_drive
except ImportError:
    google_drive = None
try:
    from actions.gmail_control     import gmail_control
except ImportError:
    gmail_control = None
try:
    from actions.google_maps       import google_maps
except ImportError:
    google_maps = None
try:
    from actions.rules_engine      import rules_engine, start_rules_runner, check_phrase_triggers, _run_action as _rules_run_action
except ImportError:
    rules_engine = None; start_rules_runner = None; check_phrase_triggers = None; _rules_run_action = None
try:
    from actions.social_media      import social_media
except ImportError:
    social_media = None
try:
    from actions.whatsapp          import whatsapp
except ImportError:
    whatsapp = None
try:
    from actions.netflix_control   import netflix_control
except ImportError:
    netflix_control = None
try:
    from actions.user_profile      import user_profile, record_action
except ImportError:
    user_profile = None; record_action = None
try:
    from actions.goals             import goals
except ImportError:
    goals = None
try:
    from actions.git_control       import git_control
except ImportError:
    git_control = None
try:
    from actions.codebase          import codebase
except ImportError:
    codebase = None
try:
    from actions.knowledge_base    import knowledge_base
except ImportError:
    knowledge_base = None
try:
    from actions.windows_settings  import windows_settings
except ImportError:
    windows_settings = None
try:
    from actions.document_creator  import document_creator
except ImportError:
    document_creator = None
try:
    from actions.document_manager  import document_manager
except ImportError:
    document_manager = None
try:
    from actions.web_navigation    import web_navigation
except ImportError:
    web_navigation = None
try:
    from actions.image_generation  import image_generation
except ImportError:
    image_generation = None
try:
    from actions.smart_home        import smart_home
except ImportError:
    smart_home = None
try:
    from actions.system_monitor    import system_monitor
except ImportError:
    system_monitor = None
try:
    from actions.tiktok_analyzer   import tiktok_analyzer
except ImportError:
    tiktok_analyzer = None
try:
    from actions.arca_invoice      import arca_invoice
except ImportError:
    arca_invoice = None
try:
    from actions.terminal_agent    import terminal_agent
except ImportError:
    terminal_agent = None
try:
    from actions.native_ui         import native_ui
except ImportError:
    native_ui = None
try:
    from actions.accessibility          import accessibility, eye_tracking, micro_movement, task_simplify, routine_gamify
except ImportError:
    accessibility = None
    eye_tracking = None
    micro_movement = None
    task_simplify = None
    routine_gamify = None
try:
    from actions.screen_reader          import screen_reader
except ImportError:
    screen_reader = None
try:
    from actions.accessibility_overlay  import accessibility_overlay
except ImportError:
    accessibility_overlay = None
try:
    from actions.morning_brief     import morning_brief, already_briefed_today, mark_briefed
except ImportError:
    morning_brief = None; already_briefed_today = None; mark_briefed = None
try:
    from actions.vision_guardian   import vision_guardian, start as _start_vision_guardian
except ImportError:
    vision_guardian = None; _start_vision_guardian = None
try:
    from actions.openrouter_agent  import openrouter_agent
except ImportError:
    openrouter_agent = None
try:
    from actions.deepseek_agent    import deepseek_agent
except ImportError:
    deepseek_agent = None
try:
    from actions.deep_research     import deep_research
except ImportError:
    deep_research = None
try:
    from actions.pair_programming  import pair_programming
except ImportError:
    pair_programming = None
try:
    from actions.notion_control    import notion_control
except ImportError:
    notion_control = None
try:
    from actions.git_control       import git_control
except ImportError:
    git_control = None
try:
    from actions.desktop           import desktop_control
except ImportError:
    desktop_control = None
try:
    from actions.codebase          import codebase
except ImportError:
    codebase = None
try:
    from actions.smart_home        import smart_home
except ImportError:
    smart_home = None
try:
    from actions.arca_invoice      import arca_invoice
except ImportError:
    arca_invoice = None
try:
    from actions.tiktok_analyzer   import tiktok_analyzer
except ImportError:
    tiktok_analyzer = None
try:
    from actions.flight_finder     import flight_finder
except ImportError:
    flight_finder = None



def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LOG_PATH        = BASE_DIR / "jarvis.log"

# ── Redirect output to log file (pythonw.exe has no console) ─
try:
    import io as _io
    _log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = [s for s in streams if s is not None]
        def write(self, data):
            for s in self._streams:
                try: s.write(data)
                except Exception: pass
        def flush(self):
            for s in self._streams:
                try: s.flush()
                except Exception: pass
        @property
        def encoding(self): return "utf-8"
        def fileno(self): raise _io.UnsupportedOperation("fileno")

    sys.stdout = _TeeStream(sys.stdout, _log_fh)
    sys.stderr = _TeeStream(sys.stderr, _log_fh)
except Exception:
    pass

# ── Suppress console windows from all child subprocesses ─────────────────────
# Disabled global Popen patch to allow interactive GUI applications (cmd, notepad, etc.) to show on screen.
# Background CLI tasks already use CREATE_NO_WINDOW explicitly in actions/terminal_agent.py.

LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 256      # 16ms chunks — mic input (keep small for low latency)
PLAY_CHUNK_SIZE     = 480      # 20ms chunks — playback (smaller = lower latency)

_cached_api_key: str | None = None

def _get_api_key() -> str:
    global _cached_api_key
    if _cached_api_key:
        return _cached_api_key
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cached_api_key = json.load(f)["gemini_api_key"]
    return _cached_api_key


JARVIS_VOICES = {
    "Aoede":  ("Femenina", "Cálida y sofisticada — ideal para asistente IA"),
    "Kore":   ("Femenina", "Suave y precisa"),
    "Leda":   ("Femenina", "Natural y fluida"),
    "Zephyr": ("Femenina", "Dinámica y expresiva"),
    "Charon": ("Masculina", "Profunda y seria — voz original de JARVIS"),
    "Puck":   ("Masculina", "Ágil y versátil"),
    "Fenrir": ("Masculina", "Grave y autoritaria"),
    "Orus":   ("Masculina", "Clásica y equilibrada"),
}

def _get_jarvis_voice() -> str:
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("jarvis_voice", "Aoede")
    except Exception:
        return "Aoede"


def _load_system_prompt() -> str:
    try:
        prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
        try:
            cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            user_name = cfg.get("user_name", "Señor").strip()
            if user_name:
                prompt_text += f"\n\n## PERSONALIZACIÓN DEL USUARIO\nEl nombre del usuario es '{user_name}'. Dirígete a él como '{user_name}' (o variantes cortas respetuosas como 'señor {user_name}') de manera leal y natural en cada interacción, a menos que él te pida explícitamente cambiar su nombre."
        except Exception:
            pass
        return prompt_text
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "activate_protocol",
        "description": "Activa un Workspace o Protocolo de Entorno configurado por el usuario. Usa esta herramienta cuando el usuario te pida activar un protocolo (ej. 'Protocolo Trabajo', 'Modo Ocio').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "protocol_name": {"type": "STRING", "description": "El nombre del protocolo a activar."}
            }
        }
    },
    {
        "name": "show_hologram",
        "description": "Muestra información visual, noticias, artículos web o imágenes en un widget holográfico flotante dorado.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "URL a mostrar (opcional, ej. para noticias o web)"},
                "html": {"type": "STRING", "description": "Contenido HTML a renderizar (opcional)"}
            }
        }
    },
    {
        "name": "get_current_time",
        "description": (
            "Obtiene la fecha y hora actual exacta. "
            "DEBES USAR SIEMPRE esta herramienta antes de responder cualquier pregunta sobre la hora "
            "o el día, o antes de establecer alarmas/recordatorios."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "camera_bus",
        "description": (
            "Controla el subsistema de pilotaje y navegación gestual por cámara de JARVIS. "
            "Permite activar, desactivar o alternar el control gestual del mouse usando la webcam en segundo plano."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "enable (activar/conectar cámara gestual) | disable (desactivar/apagar cámara gestual) | toggle (alternar estado)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "jarvis_ui_control",
        "description": (
            "Control total sobre la ventana principal y los widgets de la interfaz de JARVIS. "
            "Permite minimizar/restaurar la ventana principal, o abrir, cerrar, alternar la visibilidad de cualquier widget del dashboard.\n"
            "Widgets disponibles: weather (clima), spotify (música), system (sistema), "
            "notes (notas), todo (tareas), maps (mapas), image (imágenes), camera (cámara)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "minimize (minimizar ventana) | restore (restaurar ventana) | show (mostrar widget) | hide (ocultar widget) | hide_all (ocultar todos los widgets) | toggle (alternar widget)"
                },
                "widget": {
                    "type": "STRING",
                    "description": "Nombre del widget (solo para show/hide/toggle): weather | spotify | system | notes | todo | maps | image | camera"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "window_control",
        "description": "Maximiza, minimiza, cierra o mueve ventanas en la PC (ej: opera, chrome). También puede cerrar pestañas (close_tab).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "sub_action": {"type": "STRING", "description": "maximize | minimize | close | close_tab | move_monitor"},
                "target": {"type": "STRING", "description": "Nombre de la app (ej: opera)"},
                "monitor": {"type": "STRING", "description": "Número de monitor (1 o 2) solo para move_monitor"}
            },
            "required": ["sub_action", "target"]
        }
    },
    {
        "name": "app_macro",
        "description": "Automatiza clics paso a paso en programas (ej. cambiar fuente/tamaño en Word).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app": {"type": "STRING", "description": "Nombre de la aplicación (ej: Word)"},
                "action": {"type": "STRING", "description": "Macro a ejecutar: change_font"},
                "font_name": {"type": "STRING", "description": "Nombre de la fuente (ej: Arial)"},
                "font_size": {"type": "STRING", "description": "Tamaño de la fuente (ej: 11)"}
            },
            "required": ["app", "action"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web for any information. Returns titles, snippets and URLs of real sources. "
            "Set with_citations=true when the user wants verifiable sources or asks 'where did you read that', "
            "'cite your sources', 'según qué fuente', or for any factual/research query where citations help."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"},
                "with_citations": {
                    "type": "BOOLEAN",
                    "description": "True to return formatted results with explicit source URLs the user can verify."
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Number of results to return (1-10). Default 5."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "whatsapp",
        "description": (
            "Integración completa con WhatsApp. "
            "SIEMPRE usar para CUALQUIER pedido de WhatsApp: enviar mensajes, "
            "enviar imágenes, enviar documentos/archivos (PDF, Word, Excel, ZIP, etc.), "
            "leer conversaciones, ver mensajes sin leer, "
            "guardar/listar contactos con su número de teléfono. "
            "Para enviar, primero verificar si el contacto está guardado con su teléfono. "
            "Si no está, pedir el número al usuario o usar add_contact primero. "
            "Para enviar un documento usar action='send_document' con file_path=ruta del archivo."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "send | send_image | send_document | read | unread | add_contact | list_contacts | delete_contact"},
                "receiver":   {"type": "STRING",  "description": "Nombre del contacto o número de teléfono con código de país (ej: 5215512345678)"},
                "message":    {"type": "STRING",  "description": "Texto del mensaje a enviar (para action=send)"},
                "image_path": {"type": "STRING",  "description": "Ruta de la imagen (para action=send_image). Ej: 'desktop/foto.png'"},
                "file_path":  {"type": "STRING",  "description": "Ruta del documento a enviar (para action=send_document). Ej: 'documentos/reporte.pdf', 'desktop/factura.xlsx'"},
                "caption":    {"type": "STRING",  "description": "Descripción/caption para imagen o documento (opcional)"},
                "count":      {"type": "INTEGER", "description": "Cantidad de mensajes a leer (default: 10)"},
                "name":       {"type": "STRING",  "description": "Nombre del contacto para add_contact/delete_contact"},
                "phone":      {"type": "STRING",  "description": "Número de teléfono con código de país (ej: 5215512345678) para add_contact"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "netflix_control",
        "description": (
            "Control COMPLETO e inteligente de Netflix. "
            "USA SIEMPRE para cualquier pedido relacionado con Netflix: abrir, elegir perfil, buscar películas/series, reproducir. "
            "Puede seleccionar el perfil de usuario automáticamente usando visión de IA. "
            "Acciones: play (abrir + perfil + buscar + reproducir), open (solo abrir con perfil), "
            "select_profile (cambiar perfil), search (buscar sin reproducir), "
            "pause (pausar/reanudar), forward (adelantar), back (retroceder), "
            "set_profile (guardar perfil por defecto). "
            "El perfil por defecto es 'Jorge' (guardado automáticamente). "
            "Ejemplos: 'pon Inception en Netflix' → action=play content='Inception', "
            "'abre Netflix con el perfil Jorge' → action=open profile='Jorge', "
            "'adelanta 2 minutos en Netflix' → action=forward amount='2 minutos'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "play | open | select_profile | search | pause | forward | back | set_profile"},
                "profile": {"type": "STRING",
                            "description": "Nombre del perfil de Netflix (ej: 'Jorge'). Si se omite usa el guardado."},
                "content": {"type": "STRING",
                            "description": "Nombre de la película o serie a reproducir (ej: 'Inception', 'Narcos', 'Breaking Bad')."},
                "amount":  {"type": "STRING",
                            "description": "Tiempo a adelantar o retroceder: 'un minuto', '30 segundos', '2 minutos'. Para forward/back."},
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via Telegram, Discord, Signal or other messaging platform. For WhatsApp, use the 'whatsapp' tool instead.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: Telegram, Discord, Signal, Messenger (NOT WhatsApp — use whatsapp tool)"}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task. "
            "IMPORTANT: to type text, MUST use action='type' and value='<text>'. "
            "IMPORTANT: to minimize windows, MUST use action='minimize'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controla el navegador activo (Chrome, Edge, Firefox, Brave) sin abrir uno nuevo. "
            "USA SIEMPRE para controlar videos/multimedia en el navegador. "
            "NAVEGACIÓN: go_to | search | new_tab | close_tab | scroll. "
            "MULTIMEDIA (video/audio): media_skip_forward (adelantar), media_skip_backward (retroceder), "
            "media_play_pause (pausar/reproducir), media_mute (silenciar), media_fullscreen (pantalla completa), "
            "media_speed_up (más rápido), media_speed_down (más lento), media_restart (reiniciar), "
            "media_volume_up (subir volumen del video), media_volume_down (bajar volumen del video). "
            "Funciona en YouTube, Netflix, Twitch, y CUALQUIER sitio con video HTML5. "
            "Ejemplos: 'adelanta un minuto' → action=media_skip_forward amount='1 minuto', "
            "'retrocede 30 segundos' → action=media_skip_backward amount='30 segundos', "
            "'pausa el video' → action=media_play_pause."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",
                              "description": (
                                  "Acción a ejecutar. "
                                  "Navegación: go_to | search | new_tab | close_tab | scroll. "
                                  "Multimedia: media_skip_forward | media_skip_backward | media_play_pause | "
                                  "media_mute | media_fullscreen | media_speed_up | media_speed_down | "
                                  "media_restart | media_volume_up | media_volume_down."
                              )},
                "url":       {"type": "STRING", "description": "URL para go_to o new_tab"},
                "query":     {"type": "STRING", "description": "Término de búsqueda para search"},
                "direction": {"type": "STRING", "description": "Dirección de scroll: up | down"},
                "amount":    {"type": "STRING",
                              "description": (
                                  "Cantidad de tiempo para adelantar/retroceder. "
                                  "Acepta lenguaje natural: 'un minuto', '2 minutos 30 segundos', '45 segundos', '90'. "
                                  "Usado por media_skip_forward y media_skip_backward."
                              )},
            },
            "required": ["action"]
        }
    },
    {
        "name": "visual_click",
        "description": "Utiliza Visión Espacial para encontrar las coordenadas matemáticas de un elemento en la pantalla y hacer clic en él físicamente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element_description": {"type": "STRING", "description": "Descripción clara de lo que quieres cliquear (ej: 'botón de enviar', 'ícono de la papelera')."}
            },
            "required": ["element_description"]
        }
    },
    {
        "name": "sleep_mode",
        "description": "Entra en modo suspensión. Desactiva el micrófono para la IA hasta que el usuario diga 'Oye JARVIS' o 'JARVIS' localmente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "file_controller",
        "description": (
            "ESTRICTAMENTE OBLIGATORIO - SECUENCIA DE BÚSQUEDA Y MANEJO DE ARCHIVOS:\n"
            "1. Cuando el usuario pida buscar un archivo, PREGÚNTALE EN QUÉ CARPETA ESTÁ.\n"
            "2. Usa `action='gui_search'` con filename y folder.\n"
            "3. Lee la lista de encontrados. Si el usuario elige uno por posición (ej: 'el primero', 'el 5to'), DIME EL NOMBRE EXACTO DEL ARCHIVO Y PREGUNTA SI ES EL CORRECTO **ANTES** DE COPIARLO.\n"
            "4. SOLO TRAS CONFIRMAR que es el correcto, usa `action='select_and_copy'` con el `filepath` exacto.\n"
            "5. Luego de copiarlo, pregúntale si quiere ABRIRLO o ENVIARLO POR WHATSAPP.\n\n"
            "Además, gestiona archivos locales: list, create, delete, move, copy, rename, read, edit, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | edit | find | largest | disk_usage | organize_desktop | info | gui_search | select_and_copy | open_file"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "filename":    {"type": "STRING", "description": "Nombre del archivo a buscar (para gui_search)"},
                "folder":      {"type": "STRING", "description": "Carpeta (ej: 'Descargas') (para gui_search)"},
                "filepath":    {"type": "STRING", "description": "Ruta absoluta (para select_and_copy u open_file)"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
                "old_text":    {"type": "STRING",  "description": "Texto a reemplazar (para edit)"},
                "new_text":    {"type": "STRING",  "description": "Nuevo texto o contenido (para edit)"},
                "mode":        {"type": "STRING",  "description": "replace | append | prepend | overwrite (para edit)"},
                "confirm":     {"type": "BOOLEAN", "description": "true para confirmar eliminaciones"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": (
            "Controls the desktop: wallpaper, organize, clean, list, stats. "
            "When the user says to use a file from a directory (e.g. 'el archivo X del escritorio'), "
            "use search_name + search_path to auto-find the file before applying the action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":        {"type": "STRING", "description": "Image path for wallpaper"},
                "url":         {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":        {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":        {"type": "STRING", "description": "Natural language desktop task"},
                "search_name": {"type": "STRING", "description": "Filename to search for in a directory (auto-finds full path)"},
                "search_path": {"type": "STRING", "description": "Directory to search: desktop, downloads, documents, pictures, home (default: desktop)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "Manages Steam and Epic Games library: list installed games, "
            "update/install/download a game, check download status, launch a specific game. "
            "Use for: 'cuántos juegos tengo en Steam', 'actualiza X', 'instala AppID Y', "
            "'qué juegos tengo instalados', 'lanza [juego]'. "
            "DO NOT use for 'abre Steam' (use open_app instead)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "pair_programming",
        "description": (
            "Activar / desactivar modo 'pair programmer'. Cuando está activo, JARVIS captura "
            "la pantalla del IDE cada N segundos, analiza el código, y reporta problemas en el "
            "panel de actividad sin interrumpir la voz del usuario. "
            "Usar cuando el usuario diga: 'modo programador', 'pair programming', 'ayúdame a programar', "
            "'observa mi código', 'sé mi copiloto', o explícitamente lo pida."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'start' para activar, 'stop' para desactivar, 'status' para consultar",
                    "enum": ["start", "stop", "status"]
                },
                "interval_s": {
                    "type": "INTEGER",
                    "description": "Cada cuántos segundos analizar (10-120). Default 25."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "focus_mode",
        "description": (
            "Activar o desactivar el modo concentración / no molestar. "
            "Cuando está activo, JARVIS suprime notificaciones no críticas, "
            "no envía sugerencias proactivas, y vision_guardian queda silenciado. "
            "Solo eventos marcados como críticos (correos urgentes, alarmas) interrumpen. "
            "Usar cuando el usuario diga: 'modo concentración', 'modo focus', 'no me molestes', "
            "'voy a trabajar X horas', 'silencio'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'enable' para activar, 'disable' para desactivar, 'status' para consultar",
                    "enum": ["enable", "disable", "status"]
                },
                "duration_minutes": {
                    "type": "INTEGER",
                    "description": "Duración en minutos (solo para enable). Default 60."
                },
                "reason": {
                    "type": "STRING",
                    "description": "Razón opcional (ej: 'trabajo profundo', 'reunión')"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "task_status",
        "description": (
            "Reports the status of background tasks JARVIS is running. "
            "Call this when the user asks '¿en qué vas?', '¿cómo va la tarea?', "
            "'qué estás haciendo', or wants a status update on long-running operations. "
            "Returns a human-readable summary."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'list' to see running tasks, 'summary' for a brief voice summary",
                    "enum": ["list", "summary"]
                }
            }
        }
    },
    {
        "name": "show_activity_panel",
        "description": (
            "Shows or hides the floating activity panel that displays the current tool, "
            "running tasks, and step-by-step plan. Use when the user asks to see what "
            "JARVIS is doing, the activity panel, or to hide it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "show": {
                    "type": "BOOLEAN",
                    "description": "true to show, false to hide"
                }
            }
        }
    },
    {
        "name": "usage_dashboard",
        "description": (
            "Muestra el dashboard de uso de JARVIS: top herramientas, errores frecuentes, "
            "latencias, estado de memoria y de proveedores. Usar cuando el usuario diga "
            "'dashboard', 'estadísticas de uso', '¿qué tanto te uso?', 'reporte de uso'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'text' (default) para resumen verbal, 'html' para holograma visual",
                    "enum": ["text", "html"]
                }
            }
        }
    },
    {
        "name": "system_diagnostics",
        "description": (
            "Returns diagnostic info about JARVIS internals: memory stats, "
            "log sizes, quota state of AI providers. Use when user asks for "
            "system status, diagnostics, or 'cómo estás'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "google_calendar",
        "description": (
            "Manages the user's Google Calendar: create, list, edit, or delete events. "
            "Use for ANY request about calendar events, appointments, reminders with dates, "
            "scheduling meetings, or checking what's coming up. "
            "ALWAYS call this tool for calendar requests — never simulate. "
            "For 'list': shows upcoming events. "
            "For 'create': needs summary and start (end defaults to +1h). "
            "For 'edit'/'delete': needs event_id (get it from 'list' first)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "list | create | edit | delete"},
                "summary":     {"type": "STRING",  "description": "Event title/name"},
                "start":       {"type": "STRING",  "description": "Start date/time: ISO, YYYY-MM-DD HH:MM, or DD/MM/YYYY HH:MM"},
                "end":         {"type": "STRING",  "description": "End date/time (optional — defaults to start + 1 hour)"},
                "description": {"type": "STRING",  "description": "Event notes or description"},
                "location":    {"type": "STRING",  "description": "Event location"},
                "event_id":    {"type": "STRING",  "description": "Event ID (first 8 chars from list) for edit/delete"},
                "days_ahead":  {"type": "INTEGER", "description": "Days to look ahead for list (default: 7)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "spotify_control",
        "description": (
            "Control total de Spotify: reproducir, pausar, siguiente, anterior, volumen, "
            "buscar canciones/artistas/álbumes/playlists, aleatorio, repetir, ver qué suena, "
            "guardar canciones, ver dispositivos. "
            "SIEMPRE llamar esta herramienta para CUALQUIER pedido relacionado con Spotify o música."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | pause | resume | next | previous | volume | shuffle | repeat | current | search | like | devices | playlist"},
                "query":  {"type": "STRING", "description": "Búsqueda para play/search: canción, artista, álbum o playlist"},
                "type":   {"type": "STRING", "description": "track | album | playlist | artist (default: track)"},
                "value":  {"type": "STRING", "description": "Valor para volume (0-100), shuffle (true/false), repeat (off/track/context)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "rgb_control",
        "description": (
            "Controla las luces RGB de periféricos y componentes de la PC (teclado, mouse, GPU, RAM, etc.). "
            "Requiere OpenRGB corriendo con servidor SDK activado. "
            "Usar para: cambiar color, apagar, brillo, efectos, arco iris."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "set_color | off | brightness | effect | rainbow | list"},
                "color":      {"type": "STRING", "description": "Color: nombre (rojo, azul, verde, blanco…) o hex #RRGGBB"},
                "brightness": {"type": "INTEGER", "description": "Brillo 0-100 (default: 100)"},
                "device":     {"type": "STRING", "description": "Filtro por nombre de dispositivo (opcional, aplica a todos si se omite)"},
                "effect":     {"type": "STRING", "description": "Nombre del efecto para la acción effect"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "scheduler",
        "description": (
            "Crea, lista, elimina o ejecuta automatizaciones programadas (tareas recurrentes). "
            "Ejemplos: backup diario, notificaciones, scripts automáticos. "
            "Usar para CUALQUIER pedido de 'todos los días a las X', 'cada semana', 'automatizar'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":           {"type": "STRING",  "description": "list | create | delete | enable | disable | run_now"},
                "name":             {"type": "STRING",  "description": "Nombre descriptivo de la tarea"},
                "frequency":        {"type": "STRING",  "description": "daily | weekly | interval | once"},
                "hour":             {"type": "INTEGER", "description": "Hora de ejecución (0-23)"},
                "minute":           {"type": "INTEGER", "description": "Minuto de ejecución (0-59)"},
                "weekday":          {"type": "STRING",  "description": "Día de la semana para frequency=weekly"},
                "interval_minutes": {"type": "INTEGER", "description": "Intervalo en minutos para frequency=interval"},
                "task_action":      {"type": "STRING",  "description": "backup | file_controller | notify | custom_script | browser_control"},
                "task_parameters":  {"type": "OBJECT",  "description": "Parámetros de la tarea (source, destination para backup, etc.)"},
                "task_id":          {"type": "STRING",  "description": "ID de la tarea (primeros 6 chars) para delete/enable/disable/run_now"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_drive",
        "description": (
            "Gestiona Google Drive: listar archivos, buscar, subir, descargar, crear carpetas, eliminar, compartir. "
            "SIEMPRE usar para cualquier pedido sobre Google Drive."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | search | upload | download | create_folder | delete | share | info"},
                "folder_id":   {"type": "STRING", "description": "ID de la carpeta (default: root)"},
                "file_id":     {"type": "STRING", "description": "ID del archivo para download/delete/share/info"},
                "path":        {"type": "STRING", "description": "Ruta local para upload"},
                "name":        {"type": "STRING", "description": "Nombre de la nueva carpeta"},
                "query":       {"type": "STRING", "description": "Término de búsqueda"},
                "destination": {"type": "STRING", "description": "Carpeta local de destino para download"},
                "email":       {"type": "STRING", "description": "Email para compartir"},
                "role":        {"type": "STRING", "description": "reader | writer | commenter"},
                "confirm":     {"type": "BOOLEAN", "description": "true para confirmar eliminación"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "gmail_control",
        "description": (
            "Gestiona Gmail: leer bandeja, leer correo, enviar, responder, buscar, archivar, eliminar. "
            "SIEMPRE usar para cualquier pedido sobre correo electrónico o Gmail."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "inbox | read | send | reply | search | archive | delete | mark_read | labels"},
                "count":      {"type": "INTEGER", "description": "Cantidad de correos a listar/buscar (default: 5)"},
                "message_id": {"type": "STRING",  "description": "ID del mensaje para read/reply/archive/delete/mark_read"},
                "to":         {"type": "STRING",  "description": "Destinatario para send"},
                "subject":    {"type": "STRING",  "description": "Asunto para send"},
                "body":       {"type": "STRING",  "description": "Cuerpo del correo para send/reply"},
                "query":      {"type": "STRING",  "description": "Búsqueda Gmail para search (ej: 'from:juan', 'subject:factura')"},
                "confirm":    {"type": "BOOLEAN", "description": "true para confirmar eliminación"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_maps",
        "description": (
            "Muestra rutas de navegación y mapas interactivos. "
            "Usar para: cómo llegar a un lugar, cuánto tarda, indicaciones paso a paso, "
            "buscar una dirección en el mapa. Abre mapa JARVIS en Chrome con la ruta marcada. "
            "SIEMPRE llamar para cualquier pedido de navegación, rutas o mapas."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "directions | search"},
                "origin":      {"type": "STRING", "description": "Punto de partida (dirección, ciudad, lugar)"},
                "destination": {"type": "STRING", "description": "Destino (dirección, ciudad, lugar)"},
                "mode":        {"type": "STRING", "description": "car (auto) | walk (caminando) | bike (bicicleta). Default: car"},
                "query":       {"type": "STRING", "description": "Lugar a buscar en el mapa (para action=search)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "rules_engine",
        "description": (
            "Motor de automatizaciones y alertas inteligentes. "
            "USAR SIEMPRE cuando el usuario pida: 'cuando diga X hacé Y', 'cada vez que diga X', "
            "'si digo X abrí/poné/hacé Y', 'quiero que cuando diga X...'. "
            "Soporta: phrase triggers (frase → acción), time triggers (hora → acción), alertas. "
            "Listar, crear, eliminar, habilitar/deshabilitar automaciones. "
            "CONDITION types: phrase (frase del usuario), time (hora del día), file_exists, always. "
            "ACTION types: open_app, spotify_play, browser, smart_home, composite (múltiples), notify, speak, run_script."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "list | list_phrases | create | delete | enable | disable | trigger | alert"},
                "name":       {"type": "STRING", "description": "Nombre de la automatización"},
                "rule_id":    {"type": "STRING", "description": "ID de la regla para delete/enable/disable/trigger"},
                "condition":  {
                    "type": "OBJECT",
                    "description": (
                        "Condición. phrase: {type:phrase, trigger:'texto exacto', match:contains|exact|startswith}. "
                        "time: {type:time, hour:8, minute:0, days:[monday,...]}. "
                        "file_exists: {type:file_exists, path:'...'}. always: {type:always}"
                    )
                },
                "action_def": {
                    "type": "OBJECT",
                    "description": (
                        "Acción a ejecutar. "
                        "open_app: {type:open_app, app_name:'Spotify'}. "
                        "spotify_play: {type:spotify_play, query:'Back in Black AC/DC'}. "
                        "browser: {type:browser, url:'https://...'}. "
                        "smart_home: {type:smart_home, device:'living', action:'on'}. "
                        "composite: {type:composite, actions:[{...},{...}]}. "
                        "notify: {type:notify, message:'...'}. speak: {type:speak, message:'...'}. "
                        "run_script: {type:run_script, command:'...'}."
                    )
                },
                "message":    {"type": "STRING", "description": "Mensaje para action=alert"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "user_profile",
        "description": (
            "Perfil dinámico del usuario — hábitos, preferencias, historial de uso. "
            "Ver perfil, configurar preferencias, ver hábitos aprendidos, guardar notas personales. "
            "JARVIS aprende automáticamente los patrones del usuario."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "view | set_preference | set_name | add_note | notes | habits | reset"},
                "key":    {"type": "STRING", "description": "Clave de preferencia (ej: idioma, tema, ciudad)"},
                "value":  {"type": "STRING", "description": "Valor de la preferencia"},
                "name":   {"type": "STRING", "description": "Nombre del usuario"},
                "note":   {"type": "STRING", "description": "Nota personal a guardar"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "goals",
        "description": (
            "Sistema de objetivos persistentes a largo plazo. "
            "Crear metas, trackear progreso, marcar pasos completados. "
            "Usar para: metas personales, proyectos, hábitos, objetivos con deadline. "
            "SIEMPRE usar para pedidos de 'quiero lograr X', 'mi objetivo es', 'meta de'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "list | create | update_progress | complete | complete_step | add_step | delete | detail"},
                "goal_id":     {"type": "STRING",  "description": "ID del objetivo para update/complete/delete/detail"},
                "title":       {"type": "STRING",  "description": "Título del objetivo"},
                "description": {"type": "STRING",  "description": "Descripción detallada"},
                "deadline":    {"type": "STRING",  "description": "Fecha límite ISO (YYYY-MM-DD)"},
                "progress":    {"type": "INTEGER", "description": "Progreso 0-100"},
                "steps":       {"type": "ARRAY",   "items": {"type": "STRING"}, "description": "Lista de pasos del objetivo"},
                "step":        {"type": "STRING",  "description": "Texto del nuevo paso (add_step)"},
                "step_index":  {"type": "INTEGER", "description": "Índice del paso a completar (0-based)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "git_control",
        "description": (
            "Integración completa con Git: status, log, diff, commit automático, "
            "branches, pull, push, stash, análisis de cambios. "
            "Usar para CUALQUIER pedido relacionado con Git o control de versiones."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "status | log | diff | commit | add | branches | branch_create | checkout | pull | push | stash | analyze"},
                "repo_path":   {"type": "STRING",  "description": "Ruta al repositorio Git"},
                "message":     {"type": "STRING",  "description": "Mensaje del commit"},
                "branch_name": {"type": "STRING",  "description": "Nombre de la rama"},
                "remote":      {"type": "STRING",  "description": "Remote (default: origin)"},
                "n":           {"type": "INTEGER", "description": "Número de commits para log"},
                "file":        {"type": "STRING",  "description": "Archivo específico para diff"},
                "staged":      {"type": "BOOLEAN", "description": "Mostrar diff staged"},
                "add_all":     {"type": "BOOLEAN", "description": "Agregar todos los archivos antes del commit (default: true)"},
                "files":       {"type": "ARRAY",   "items": {"type": "STRING"}, "description": "Archivos para add"},
                "sub":         {"type": "STRING",  "description": "Subcomando para stash: push|pop|list"},
            },
            "required": ["action", "repo_path"]
        }
    },
    {
        "name": "codebase",
        "description": (
            "Indexación y búsqueda inteligente de proyectos de código. "
            "Indexar proyectos, buscar en archivos, encontrar símbolos (funciones/clases), "
            "generar documentación automática, búsqueda avanzada de código. "
            "Usar para: 'buscar en mi proyecto', 'dónde está la función X', 'generar docs', 'indexar mi código'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "index | list | info | search | find_symbol | generate_docs | remove"},
                "path":      {"type": "STRING", "description": "Ruta del proyecto a indexar"},
                "name":      {"type": "STRING", "description": "Nombre del proyecto (default: nombre de carpeta)"},
                "project":   {"type": "STRING", "description": "Nombre del proyecto para info/search/find_symbol"},
                "query":     {"type": "STRING", "description": "Texto a buscar en el código"},
                "symbol":    {"type": "STRING", "description": "Nombre de función/clase a buscar"},
                "file_path": {"type": "STRING", "description": "Ruta del archivo para generate_docs"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "notion_control",
        "description": (
            "Integración completa con Notion: buscar páginas, leer contenido, crear páginas, "
            "agregar contenido, consultar bases de datos, actualizar y archivar páginas. "
            "Usar para: 'buscar en Notion', 'crear una página en Notion', 'leer mi nota de Notion', "
            "'agregar a mi base de datos de Notion', 'qué tengo guardado en Notion sobre X'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "search | read | create | append | query | update | archive | setup"},
                "query":       {"type": "STRING",  "description": "Texto a buscar (action=search)"},
                "page_id":     {"type": "STRING",  "description": "ID de la página de Notion"},
                "database_id": {"type": "STRING",  "description": "ID de la base de datos de Notion"},
                "parent_id":   {"type": "STRING",  "description": "ID de la página padre o database donde crear"},
                "title":       {"type": "STRING",  "description": "Título de la nueva página"},
                "content":     {"type": "STRING",  "description": "Contenido de la página (párrafos separados por \\n)"},
                "block_type":  {"type": "STRING",  "description": "Tipo de bloque al agregar: paragraph | bulleted_list_item | numbered_list_item | to_do | heading_1 | heading_2 | quote"},
                "count":       {"type": "INTEGER", "description": "Cantidad máxima de resultados (default: 10)"},
                "archived":    {"type": "BOOLEAN", "description": "Si archivar la página (action=update)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "knowledge_base",
        "description": (
            "Segundo cerebro / base de conocimiento personal. "
            "Guardar notas, ideas, snippets de código, referencias, hechos, preguntas. "
            "Buscar en el conocimiento guardado, exportar. "
            "Usar para: 'recordá que...', 'guardá esta idea', 'anotá este código', 'buscar en mis notas'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "add/save/store | search/find | list | get/read/view | update | delete | stats | export"},
                "title":    {"type": "STRING", "description": "Título de la entrada"},
                "content":  {"type": "STRING", "description": "Contenido o texto a guardar"},
                "type":     {"type": "STRING", "description": "note | idea | snippet | reference | fact | task | question"},
                "tags":     {"type": "STRING", "description": "Tags separados por coma (ej: python, jarvis, idea)"},
                "query":    {"type": "STRING", "description": "Búsqueda en la base de conocimiento"},
                "entry_id": {"type": "STRING", "description": "ID de la entrada para get/update/delete"},
                "path":     {"type": "STRING", "description": "Ruta para exportar (action=export)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "social_media",
        "description": (
            "Controla redes sociales: Twitter/X, Instagram, TikTok y LinkedIn. "
            "Twitter: publicar tweets, ver timeline, buscar, like, retweet, ver perfil. "
            "Instagram: publicar fotos, subir historias, enviar DMs, ver feed, like, comentar. "
            "TikTok: subir videos, ver perfil/stats, tendencias. "
            "LinkedIn: publicar posts, ver perfil, ver feed, enviar mensajes. "
            "SIEMPRE usar para cualquier pedido de redes sociales. "
            "Para WhatsApp usar la herramienta 'whatsapp'. "
            "Usá action=setup para ver cómo configurar las credenciales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "twitter | instagram | tiktok | linkedin | setup"},
                "action":   {"type": "STRING", "description": (
                    "Twitter: tweet, delete_tweet, like, retweet, timeline, search_tweets, my_tweets, profile | "
                    "Instagram: post/upload_photo, story, send_dm, feed, profile, like, comment | "
                    "TikTok: upload/publicar, profile/perfil, trending | "
                    "LinkedIn: post/publicar, profile/perfil, send_message/mensaje, feed"
                )},
                "text":       {"type": "STRING", "description": "Texto del tweet/post/comentario/mensaje"},
                "content":    {"type": "STRING", "description": "Contenido del post (LinkedIn/TikTok)"},
                "tweet_id":   {"type": "STRING", "description": "ID del tweet para like/retweet/delete"},
                "media_id":   {"type": "STRING", "description": "ID del post de Instagram para like/comment"},
                "username":   {"type": "STRING", "description": "Usuario para DM/perfil (Instagram, TikTok, LinkedIn)"},
                "receiver":   {"type": "STRING", "description": "Destinatario del DM de Instagram"},
                "image_path": {"type": "STRING", "description": "Ruta imagen para Instagram/LinkedIn"},
                "video_path": {"type": "STRING", "description": "Ruta del video para TikTok"},
                "caption":    {"type": "STRING", "description": "Descripción/caption de la foto o video"},
                "query":      {"type": "STRING", "description": "Búsqueda de tweets"},
                "count":      {"type": "INTEGER", "description": "Cantidad de resultados (default: 5)"},
            },
            "required": ["platform", "action"]
        }
    },
    {
        "name": "windows_settings",
        "description": (
            "Control TOTAL de configuraciones de Windows. "
            "Usar para CUALQUIER pedido relacionado con configuración del sistema. "
            "Categorías disponibles:\n"
            "• display: brillo, resolución, frecuencia, escala, modo oscuro/noche, HDR, orientación, monitores\n"
            "• audio: volumen, mute, dispositivos de audio/micrófono, mezclador\n"
            "• network: WiFi (listar/conectar/desconectar/on/off), IP, DNS, flush_dns, modo avión, Bluetooth, proxy\n"
            "• power: plan energía, suspender, hibernar, batería, timeouts, inicio rápido\n"
            "• system: info del sistema, nombre PC, fecha/hora, zona horaria, reiniciar, apagar, bloquear, variables de entorno\n"
            "• personalization: fondo de pantalla, tema, transparencia, barra de tareas, protector de pantalla\n"
            "• apps: listar apps, desinstalar, apps de inicio, aplicaciones predeterminadas\n"
            "• security: Windows Defender, firewall, UAC, BitLocker, usuarios del sistema\n"
            "• input: velocidad mouse, doble clic, scroll, botones, velocidad teclado, idioma\n"
            "• storage: discos, espacio, limpieza de archivos temporales, papelera, defrag, chkdsk\n"
            "• services: listar/iniciar/detener/reiniciar servicios de Windows, procesos, kill\n"
            "• privacy: cámara/micrófono privacidad, ubicación, telemetría, notificaciones, portapapeles\n"
            "• registry: leer, escribir, eliminar claves del registro, exportar\n"
            "• accessibility: lupa, narrador, alto contraste, teclado en pantalla\n"
            "• open_settings: abrir panel específico de Configuración de Windows\n"
            "SIEMPRE llamar para cualquier pedido de configuración, ajuste o control del sistema Windows."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "La acción a realizar. Ejemplos por categoría:\n"
                        "display: get_brightness | set_brightness | get_resolution | set_resolution | "
                        "set_refresh_rate | get_scaling | set_scaling | night_light_on | night_light_off | "
                        "hdr_on | hdr_off | set_orientation | list_monitors | open\n"
                        "audio: get_volume | set_volume | mute | unmute | toggle_mute | list_devices | "
                        "set_device | get_mic_volume | set_mic_volume | open\n"
                        "network: list_wifi | connect_wifi | disconnect_wifi | wifi_on | wifi_off | "
                        "get_ip | set_dns | flush_dns | airplane_on | airplane_off | "
                        "bluetooth_on | bluetooth_off | set_proxy | disable_proxy | open\n"
                        "power: get_plan | set_plan | list_plans | sleep | hibernate | battery_status | "
                        "set_sleep_timeout | set_screen_timeout | fast_startup_on | fast_startup_off | open\n"
                        "system: info | get_hostname | set_hostname | get_datetime | set_datetime | "
                        "set_timezone | restart | shutdown | lock | get_env | set_env | delete_env | open\n"
                        "personalization: set_wallpaper | get_wallpaper | dark_mode | light_mode | "
                        "transparency_on | transparency_off | taskbar_position | screensaver | open\n"
                        "apps: list | uninstall | startup_apps | set_default | open\n"
                        "security: defender_scan | defender_status | firewall_on | firewall_off | "
                        "firewall_status | uac_level | bitlocker_status | list_users | add_user | open\n"
                        "input: get_mouse_speed | set_mouse_speed | swap_buttons | get_keyboard_speed | "
                        "set_keyboard_speed | list_languages | add_language | open\n"
                        "storage: list_drives | disk_usage | cleanup | empty_trash | clean_temp | "
                        "defrag | chkdsk | open\n"
                        "services: list | start | stop | restart | status | list_processes | kill_process | open\n"
                        "privacy: camera_on | camera_off | mic_on | mic_off | location_on | location_off | "
                        "telemetry_level | notifications_on | notifications_off | clipboard_history_on | "
                        "clipboard_history_off | open\n"
                        "registry: read | write | delete | export\n"
                        "accessibility: magnifier_on | magnifier_off | narrator_on | narrator_off | "
                        "high_contrast_on | high_contrast_off | osk_on | open\n"
                        "open_settings: <nombre del panel, ej: display, sound, wifi, bluetooth, apps>"
                    )
                },
                "value":    {"type": "STRING",  "description": "Valor para la acción (ej: 80 para brillo, 'Dark' para tema, SSID para wifi, etc.)"},
                "value2":   {"type": "STRING",  "description": "Segundo valor cuando se necesitan dos parámetros (ej: contraseña de WiFi, valor de registro)"},
                "name":     {"type": "STRING",  "description": "Nombre del servicio, proceso, usuario, app, o variable de entorno"},
                "hive":     {"type": "STRING",  "description": "Para registry: HKLM | HKCU | HKCR | HKU | HKCC"},
                "key":      {"type": "STRING",  "description": "Para registry: ruta de la clave del registro"},
                "reg_name": {"type": "STRING",  "description": "Para registry: nombre del valor del registro"},
                "reg_type": {"type": "STRING",  "description": "Para registry: REG_SZ | REG_DWORD | REG_BINARY | REG_EXPAND_SZ"},
                "path":     {"type": "STRING",  "description": "Ruta de archivo (para wallpaper, export registry, etc.)"},
                "monitor":  {"type": "INTEGER", "description": "Índice del monitor (0, 1, 2…)"},
                "width":    {"type": "INTEGER", "description": "Ancho de resolución"},
                "height":   {"type": "INTEGER", "description": "Alto de resolución"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "image_generation",
        "description": (
            "Genera imágenes con inteligencia artificial a partir de una descripción en texto. "
            "Usa Pollinations.ai (gratis, open-source, sin API key) o Gemini. "
            "SIEMPRE llamar cuando el usuario pide 'generame una imagen', 'crea una foto de', "
            "'dibujame', 'haceme una imagen', 'quiero una foto de', o 'mostrame', etc. "
            "Después de generar, la imagen se muestra automáticamente en el widget de JARVIS."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":       {"type": "STRING",  "description": "Descripción detallada de la imagen a generar"},
                "count":        {"type": "INTEGER", "description": "Cantidad de imágenes (1-4, default: 1)"},
                "aspect_ratio": {"type": "STRING",  "description": "Relación de aspecto: 1:1 | 4:3 | 3:4 | 16:9 | 9:16 (default: 1:1)"},
                "save_path":    {"type": "STRING",  "description": "Carpeta de guardado (default: ~/Pictures/JARVIS_Generadas)"},
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "smart_home",
        "description": (
            "Controla las luces y dispositivos inteligentes del hogar. "
            "Soporta Tuya/Smart Life, Philips Hue, LIFX y Yeelight. "
            "SIEMPRE llamar para: encender/apagar luces, cambiar color, brillo, temperatura de color, "
            "activar escenas, consultar estado. "
            "Si no hay dispositivos configurados, usar action=setup para ver instrucciones."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "on | off | toggle | color | brightness | temperature | scene | status | list | setup"},
                "device":      {"type": "STRING",  "description": "Nombre o sala del dispositivo (ej: 'sala', 'cuarto', 'lampara principal'). Omitir = todos."},
                "color":       {"type": "STRING",  "description": "Color: nombre (rojo, azul, blanco, cálido…) o hex #RRGGBB"},
                "value":       {"type": "INTEGER", "description": "Valor numérico para brightness (1-100) o temperatura Kelvin (1700-9000)"},
                "brightness":  {"type": "INTEGER", "description": "Brillo 1-100 (alternativa a value)"},
                "scene":       {"type": "STRING",  "description": "Nombre de la escena: relajar, leer, trabajar, noche, fiesta"},
                "protocol":    {"type": "STRING",  "description": "tuya | hue | lifx | yeelight. Omitir = usa el configurado por defecto."},
                "group":       {"type": "STRING",  "description": "Nombre del grupo/sala en Philips Hue"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_monitor",
        "description": (
            "Monitorea el rendimiento del sistema en tiempo real: CPU, RAM, GPU, discos, "
            "red, temperatura, batería, procesos activos, uptime. "
            "Usar para: '¿cómo está la PC?', 'qué proceso consume más', 'temperatura del CPU', "
            "'cuánta RAM libre tengo', 'matar proceso X', 'resumen de rendimiento'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",  "description": "cpu | ram | disk | network | gpu | temperature | battery | uptime | processes | kill | report"},
                "sort_by":  {"type": "STRING",  "description": "Para processes: cpu (default) | ram"},
                "count":    {"type": "INTEGER", "description": "Para processes: cantidad a mostrar (default: 10)"},
                "name":     {"type": "STRING",  "description": "Para kill: nombre o PID del proceso"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "document_creator",
        "description": (
            "Crea documentos Word (.docx) o Excel (.xlsx) profesionales con portada, índice, "
            "normas APA 7 / Chicago / MLA / profesional, cabeceras, pies de página, "
            "estilos académicos, callout boxes, tablas y referencias. "
            "Usar para: documentos de investigación, reportes, trabajos académicos, cartas, "
            "presupuestos, presentaciones de contenido, cualquier archivo estructurado. "
            "SIEMPRE usar content con el texto completo en markdown extendido. "
            "SIEMPRE llamar esta herramienta — nunca solo decir que lo creaste."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "word | excel | text. Para documentos académicos/profesionales usar 'word'."
                },
                "title": {
                    "type": "STRING",
                    "description": "Título del documento (también usado como nombre de archivo)"
                },
                "norm": {
                    "type": "STRING",
                    "description": (
                        "Norma de formato: "
                        "apa o apa7 — Times New Roman 12pt, doble espacio, márgenes 2.54cm, headings APA 7 | "
                        "professional — Calibri, headings azules con línea, estilo corporativo | "
                        "academic — Times New Roman, estilo académico general | "
                        "chicago | mla. Default: professional"
                    )
                },
                "cover": {
                    "type": "STRING",
                    "description": (
                        "JSON con datos de la portada. Campos disponibles: "
                        "institution (universidad/empresa), title (título), subtitle, "
                        "authors o author (nombre(s) del autor), course (materia), "
                        "professor o instructor, department, date. "
                        'Ejemplo: {"institution":"UNAM","title":"Métodos Numéricos",'
                        '"authors":"Juan Pérez","course":"Ing. Civil","date":"Junio 2026"}'
                    )
                },
                "content": {
                    "type": "STRING",
                    "description": (
                        "Contenido completo en markdown extendido. Sintaxis disponible:\n"
                        "# Título sección (H1)\n"
                        "## Subtítulo (H2)\n"
                        "### Sub-subtítulo (H3)\n"
                        "Párrafo normal (texto justificado)\n"
                        "- Elemento de lista con viñeta\n"
                        "1. Elemento de lista numerada\n"
                        "> Cita en bloque (indentada, cursiva)\n"
                        "**negrita** _cursiva_ ***negrita+cursiva***\n"
                        "[BOX title=\"Título\"]texto del recuadro destacado[/BOX]\n"
                        "[TABLE]Col1|Col2\nFila1A|Fila1B\nFila2A|Fila2B[/TABLE]\n"
                        "[ABSTRACT]texto del resumen[/ABSTRACT]\n"
                        "[REFERENCES]\nAutor, A. (2024). Título. Editorial.\n[/REFERENCES]\n"
                        "[TOC] — inserta tabla de contenidos\n"
                        "--- — salto de página"
                    )
                },
                "header": {
                    "type": "STRING",
                    "description": "Texto para la cabecera de cada página. Ej: 'Métodos Numéricos | Tema 6'"
                },
                "toc": {
                    "type": "BOOLEAN",
                    "description": "Si incluir tabla de contenidos automática al inicio (default: false)"
                },
                "sheets": {
                    "type": "ARRAY",
                    "description": "Para Excel: lista de hojas. Cada objeto: {name, headers[], rows[][]}",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name":    {"type": "STRING"},
                            "headers": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "rows":    {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "STRING"}}}
                        }
                    }
                },
                "save_path": {
                    "type": "STRING",
                    "description": "Carpeta donde guardar (desktop, documentos, o ruta absoluta). Default: Escritorio"
                }
            },
            "required": ["action", "title", "content"]
        }
    },
    {
        "name": "tiktok_analyzer",
        "description": (
            "Analiza un perfil público de TikTok dado su URL. "
            "Extrae el nombre, bio, seguidores, y para cada video reciente: "
            "vistas, likes, comentarios y guardados. "
            "Siempre usar cuando el usuario pida analizar un perfil de TikTok "
            "o consultar estadísticas de videos de TikTok."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "profile_url": {"type": "STRING", "description": "URL completa del perfil de TikTok (ej: https://www.tiktok.com/@usuario)"},
                "max_videos":  {"type": "INTEGER", "description": "Cantidad máxima de videos a analizar (default: 8)"},
            },
            "required": ["profile_url"]
        }
    },
    {
        "name": "arca_invoice",
        "description": (
            "Genera comprobantes digitales electrónicos válidos ante ARCA (ex AFIP). "
            "Para Argentina. Soporta Factura A, B, C, Nota de Crédito, Nota de Débito. "
            "Puede operar offline (comprobante local) o conectarse con ARCA si hay certificado. "
            "SIEMPRE usar cuando el usuario pida: 'generame una factura', 'haceme un comprobante', "
            "'necesito una factura A/B/C', 'emití una nota de crédito', o similar. "
            "Usar action='listar' para mostrar los tipos disponibles."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":         {"type": "STRING", "description": "generar | listar | historial"},
                "tipo":           {"type": "INTEGER", "description": "1=Factura A, 5=Factura C (default), 6=Factura B, 3=NC A, 8=NC B, etc. Usá action=listar para ver todos."},
                "razon_social":   {"type": "STRING", "description": "Razón social del receptor (obligatorio para Factura A/B)"},
                "cuit_receptor":  {"type": "STRING", "description": "CUIT del receptor (obligatorio para Factura A/B)"},
                "domicilio":      {"type": "STRING", "description": "Domicilio del receptor (opcional)"},
                "detalle":        {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"descripcion": {"type": "STRING"}, "precio": {"type": "NUMBER"}, "cantidad": {"type": "INTEGER"}}}, "description": "Lista de productos/servicios: [{'descripcion':'...', 'precio':0.0, 'cantidad':1}]"},
                "importe_neto":   {"type": "NUMBER", "description": "Importe neto gravado (se calcula del detalle si no se especifica)"},
                "importe_iva":    {"type": "NUMBER", "description": "Importe de IVA (se calcula al 21% si no se especifica)"},
                "iva_pct":        {"type": "NUMBER", "description": "Porcentaje de IVA (default: 21.0). 0 para exento."},
                "fecha":          {"type": "STRING", "description": "Fecha del comprobante YYYY-MM-DD (default: hoy)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "accessibility",
        "description": (
            "Modulo de accesibilidad universal. "
            "Incluye: task_simplify (descomponer tareas complejas en pasos simples), "
            "emotional (regulacion emocional y analisis de tono de voz), "
            "routine (rutinas diarias gamificadas con racha y progreso), "
            "eye_tracking (control por seguimiento ocular con webcam), "
            "micro_movement (navegacion por movimientos de cabeza), "
            "speech_config (ajustar tolerancia del reconocimiento de voz). "
            "Usar cuando el usuario pida: 'simplificame esto', 'ayudame con mi rutina', "
            "'necesito organizarme', 'activar seguimiento ocular', 'ajusta la tolerancia de voz', "
            "'ejercicio de respiracion', 'complete mi tarea', 'agregar rutina'. "
            "SIEMPRE ofrecer alternativas multimodales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "task_simplify — descomponer texto en pasos simples | "
                        "emotional — intervencion emocional | "
                        "routine — gestion de rutinas gamificadas | "
                        "eye_tracking — control ocular | "
                        "micro_movement — micromovimientos | "
                        "speech_config — tolerancia de voz | "
                        "feedback — feedback visual/haptico | "
                        "config — ver o cambiar configuracion"
                    )
                },
                "text":     {"type": "STRING", "description": "Texto a simplificar (para task_simplify)"},
                "format":   {"type": "STRING", "description": "Formato: steps (default) | summary | explain"},
                "name":     {"type": "STRING", "description": "Nombre de rutina (para routine add/complete)"},
                "setting":  {"type": "STRING", "description": "Clave de configuracion a ver o cambiar"},
                "value":    {"type": "STRING", "description": "Valor para la configuracion"},
                "level":    {"type": "NUMBER", "description": "Nivel de tolerancia (0.1-1.0) o sensibilidad"},
                "stress_level": {"type": "NUMBER", "description": "Nivel de estres estimado (0.0-1.0)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_vision",
        "description": (
            "JARVIS puede VER la pantalla del usuario. Captura lo que está en el monitor "
            "y usa IA (Gemini Vision) para describirlo, responder preguntas, leer texto, "
            "o dar ayuda contextual basada en lo que se está mostrando.\n"
            "SIEMPRE usar cuando el usuario diga: '¿qué estoy viendo?', '¿qué hay en mi pantalla?', "
            "'¿qué dice ahí?', 'ayúdame con esto' (señalando la pantalla), 'leé lo que hay en pantalla', "
            "'¿podés ver mi pantalla?', 'describí lo que tengo abierto', etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "describe=describir qué hay en pantalla | question=responder pregunta sobre la pantalla | help=dar ayuda contextual | read=leer todo el texto visible"
                },
                "question": {
                    "type": "STRING",
                    "description": "Pregunta o tarea específica sobre lo que se ve en pantalla (para action=question/help)"
                },
                "monitor": {
                    "type": "INTEGER",
                    "description": "0=toda la pantalla (default), 1=monitor principal, 2=segundo monitor"
                },
            },
            "required": ["action"]
        }
    },

    {
        "name": "morning_brief",
        "description": (
            "Genera el informe matutino inteligente de JARVIS. "
            "Incluye saludo personalizado, hora, fecha, clima actual, objetivos activos y consejo del día. "
            "Usar cuando el usuario pida: 'informe del día', 'brief matutino', 'qué hay hoy', "
            "'resumen del día', 'buenos días JARVIS', o al iniciar el día."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Si True, genera el informe aunque ya se haya dado hoy."
                }
            },
            "required": []
        }
    },
    {
        "name": "vision_guardian",
        "description": (
            "Controla el Guardian de Visión Ambiental de JARVIS — monitoreo proactivo de pantalla. "
            "Analiza la pantalla periódicamente con IA y ofrece ayuda contextual cuando detecta algo relevante. "
            "Usar cuando el usuario diga: 'activa el guardian', 'desactiva el guardian', "
            "'vigila mi pantalla', 'deja de vigilar', 'analiza mi pantalla ahora', "
            "'estado del guardian', 'cambia el intervalo'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "enable", "disable", "check_now", "set_interval"],
                    "description": "Acción: status | enable | disable | check_now | set_interval"
                },
                "seconds": {
                    "type": "integer",
                    "description": "Para set_interval: segundos entre análisis (30-600)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "accessibility_overlay",
        "description": (
            "Muestra, oculta o alterna la barra flotante de accesibilidad JARVIS sobre el escritorio. "
            "USAR cuando el usuario diga: 'mostrar barra de accesibilidad', 'abrir panel de accesibilidad', "
            "'activar barra para ciegos', 'cerrar barra', 'ocultar barra de accesibilidad', "
            "'alternar barra', 'barra de accesibilidad'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "show — mostrar | hide — cerrar | toggle — alternar | status — estado actual"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "openrouter_agent",
        "description": (
            "Agente de REDACCIÓN Y TEXTO GENERAL — usa DeepSeek-Chat (V3), rápido y fluido. "
            "USA PARA: redactar textos, cartas, correos, ensayos, resúmenes, traducciones, "
            "explicaciones largas, recetas, guiones, ideas creativas, respuestas extensas. "
            "REGLA: si la respuesta que necesitás supera 3 frases propias → usá este tool. "
            "NO usar para matemáticas complejas, código difícil ni problemas que requieran razonar paso a paso. "
            "Ejemplos: 'redacta una carta', 'explícame qué es X', 'escribe un correo', 'resume esto', "
            "'dame ideas para', 'traduce este texto'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "El texto o instrucción completa para redactar o responder"
                },
                "model": {
                    "type": "STRING",
                    "description": "Opcional. Deja vacío para usar el modelo por defecto (deepseek-chat)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "deepseek_agent",
        "description": (
            "Agente de RAZONAMIENTO PROFUNDO — usa DeepSeek-R1, piensa paso a paso antes de responder. "
            "USA PARA: matemáticas, lógica, código complejo, algoritmos, análisis estratégicos, "
            "debugging difícil, decisiones con múltiples variables, problemas que requieren razonar encadenado. "
            "MÁS LENTO que openrouter_agent pero MUCHO MÁS PRECISO en problemas complejos. "
            "NUNCA usar para redacción simple, preguntas generales ni conversación. "
            "Ejemplos: 'resuelve esta ecuación', 'encuentra el bug en este código', "
            "'analiza las pros y contras de', 'razona paso a paso por qué', "
            "'dame una estrategia óptima para', 'usa deepseek para pensar esto'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "La pregunta o tarea completa para DeepSeek-R1"
                },
                "system_prompt": {
                    "type": "STRING",
                    "description": "Opcional. Contexto o rol especial para el razonamiento (ej: 'eres un experto en finanzas')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "deep_research",
        "description": (
            "Genera un DOCUMENTO LARGO de investigación (10+ páginas, miles de palabras) "
            "sobre cualquier tema, en formato Word profesional con portada, índice (TOC), "
            "secciones desarrolladas a profundidad, referencias y formato APA/professional. "
            "USAR cuando el usuario pida: 'investigación', 'reporte de N páginas', "
            "'documento extenso/largo/detallado/profundo', 'tesis', 'monografía', "
            "'ensayo largo', o cualquier solicitud que claramente exceda lo que un agente "
            "normal puede generar de una sola pasada (>3 páginas). "
            "Corre en SEGUNDO PLANO — devuelve un task_id inmediatamente y notifica al terminar. "
            "Genera contenido por secciones independientes (sin límite de 1500 tokens del openrouter_agent), "
            "produciendo documentos genuinamente largos. "
            "NO usar para resúmenes cortos, respuestas simples, ni explicaciones de 1-2 párrafos "
            "(eso es openrouter_agent). "
            "Ejemplos: 'hazme un reporte de 20 páginas sobre la IA en la economía', "
            "'redacta una investigación profunda sobre métodos numéricos', "
            "'genera un ensayo largo sobre el cambio climático'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {
                    "type": "STRING",
                    "description": "Tema central de la investigación, lo más descriptivo posible"
                },
                "target_pages": {
                    "type": "INTEGER",
                    "description": "Número de páginas objetivo del documento final (3-60). Default 15."
                },
                "title": {
                    "type": "STRING",
                    "description": "Título corto para el nombre de archivo (sin .docx). Si no se da, se genera del topic."
                },
                "norm": {
                    "type": "STRING",
                    "description": (
                        "Norma de formato. SIEMPRE usar 'professional' por defecto a menos que "
                        "el usuario pida explícitamente APA, Chicago, MLA o académico. "
                        "El formato 'professional' tiene portada con título azul grande, "
                        "callouts coloreados, tablas y referencias bonitas — es lo que el usuario espera."
                    ),
                    "enum": ["professional", "apa7", "academic"]
                },
                "save_path": {
                    "type": "STRING",
                    "description": "Carpeta destino. Default 'desktop'."
                },
                "cover": {
                    "type": "STRING",
                    "description": (
                        "JSON con metadatos de portada: "
                        '{"institution":"...","title":"...","authors":"...","course":"...","date":"..."}. '
                        "Si no se da, se genera mínima con el título."
                    )
                },
                "style_hint": {
                    "type": "STRING",
                    "description": "Estilo: 'académico profesional' (default), 'ensayo', 'técnico', 'divulgativo'"
                },
                "background": {
                    "type": "BOOLEAN",
                    "description": (
                        "true (default y RECOMENDADO) = corre en segundo plano, devuelve task_id. "
                        "false = bloquea hasta terminar (puede tardar varios minutos)."
                    )
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "terminal_agent",
        "description": (
            "Ejecuta CUALQUIER comando en la terminal de Windows (PowerShell o CMD). "
            "USAR LIBREMENTE como recurso general para CUALQUIER tarea del sistema operativo: "
            "instalar/desinstalar programas (winget, choco, pip), consultar información del sistema, "
            "ejecutar scripts, manejar archivos y carpetas, configurar redes, descargar archivos, "
            "compilar código, matar procesos, gestionar servicios, y CUALQUIER otra operación. "
            "Si no sabés cómo hacer algo con las herramientas existentes, SIEMPRE intentá resolverlo "
            "con un comando de terminal antes de decir que no podés. "
            "Es tu recurso de último recurso universal."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "El comando exacto a ejecutar"
                },
                "shell": {
                    "type": "STRING",
                    "description": "Shell a usar: powershell (default) o cmd"
                },
                "timeout": {
                    "type": "INTEGER",
                    "description": "Timeout en segundos (default: 120, max: 600)"
                },
                "working_directory": {
                    "type": "STRING",
                    "description": "Directorio de trabajo para el comando (opcional)"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "native_ui",
        "description": (
            "Automatización de Interfaz Nativa de Windows (UI Automation). "
            "USAR para listar, enfocar, escribir o hacer clic en ventanas de forma 100% precisa, saltándose la visión. "
            "Esto EVITA errores de cuota (Error 429) y permite simulación exacta de teclado/mouse."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Acción a realizar: list_windows | focus_window | type_in_window | click_center"
                },
                "window_title": {
                    "type": "STRING",
                    "description": "El nombre (o parte del nombre) de la ventana destino. (Ej: 'WhatsApp', 'Chrome')"
                },
                "text": {
                    "type": "STRING",
                    "description": "El texto a escribir (solo si action es type_in_window)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "tool_creator",
        "description": (
            "Permite a JARVIS programar e instalar sus propias herramientas. "
            "ÚSALO SIEMPRE que el usuario te pida que aprendas a hacer algo nuevo, o si necesitas una funcionalidad que no tienes preinstalada. "
            "Escribirás el código Python y se instalará automáticamente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool_name": {
                    "type": "STRING",
                    "description": "Nombre de la herramienta en snake_case"
                },
                "description": {
                    "type": "STRING",
                    "description": "Descripción clara de la herramienta y para qué sirve"
                },
                "parameters_schema": {
                    "type": "STRING",
                    "description": "El bloque de 'properties' del JSON schema en formato string válido. Ej: '{\"accion\": {\"type\": \"STRING\"}}'"
                },
                "python_code": {
                    "type": "STRING",
                    "description": "Código Python con la función def <tool_name>(parameters: dict, player=None, speak=None) -> str:"
                }
            },
            "required": ["tool_name", "description", "parameters_schema", "python_code"]
        }
    },
    {
        "name": "proactive_automation",
        "description": (
            "Gestiona reglas complejas basadas en el uso y hábitos del sistema operativo "
            "para optimizar el rendimiento y automatizar recordatorios proactivos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "add_rule (añadir regla) | list_rules (listar) | delete_rule (eliminar) | trigger_check (evaluar reglas activas)"
                },
                "rule_name": {
                    "type": "STRING",
                    "description": "Nombre identificativo de la regla de automatización"
                },
                "trigger": {
                    "type": "STRING",
                    "description": "Disparador: cpu_high | ram_high | time_of_day | app_open"
                },
                "trigger_value": {
                    "type": "STRING",
                    "description": "Valor del disparador (ej. '85' para 85% cpu, '22:00' para hora, 'chrome.exe' para app)"
                },
                "action_to_take": {
                    "type": "STRING",
                    "description": "Acción a ejecutar (ej. 'optimize_ram', 'mute_system', 'run_script')"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "unified_communications",
        "description": (
            "Gestión unificada de comunicaciones. Permite leer, enviar y organizar mensajes "
            "y notificaciones en WhatsApp, Telegram, Discord y Gmail desde esta única interfaz."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {
                    "type": "STRING",
                    "description": "Plataforma de comunicación: whatsapp | telegram | discord | gmail"
                },
                "action": {
                    "type": "STRING",
                    "description": "send_message (enviar mensaje)"
                },
                "recipient": {
                    "type": "STRING",
                    "description": "Destinatario: número telefónico para WhatsApp, ID de chat o token para Telegram, Webhook URL para Discord, o email para Gmail"
                },
                "message": {
                    "type": "STRING",
                    "description": "Contenido del mensaje a enviar"
                },
                "subject": {
                    "type": "STRING",
                    "description": "Asunto del correo (solo aplica para Gmail)"
                },
                "token": {
                    "type": "STRING",
                    "description": "Token de Bot opcional para Telegram"
                }
            },
            "required": ["platform", "action", "recipient", "message"]
        }
    },
    {
        "name": "smart_file_organizer",
        "description": (
            "Análisis y organización inteligente de archivos. Clasifica por categorías, "
            "detecta duplicados reales mediante hash MD5 y analiza espacio disponible en disco."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "organize (clasificar por tipo) | find_duplicates (buscar duplicados MD5) | disk_space (analizar espacio)"
                },
                "directory": {
                    "type": "STRING",
                    "description": "Ruta absoluta del directorio a analizar. Por defecto usa la carpeta Descargas."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "contextual_control",
        "description": (
            "Control contextual de entorno. Ajusta dinámicamente volumen, brillo, plan de energía "
            "y estado de Focus Assist (No Molestar) basándose en la ventana activa o comandos manuales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "adjust_context (auto-ajustar por ventana activa) | set_volume (fijar volumen) | set_brightness (fijar brillo) | set_power_plan (energía) | set_dnd (no molestar)"
                },
                "volume": {
                    "type": "INTEGER",
                    "description": "Nivel de volumen maestro (0-100)"
                },
                "brightness": {
                    "type": "INTEGER",
                    "description": "Nivel de brillo de la pantalla (0-100)"
                },
                "power_plan": {
                    "type": "STRING",
                    "description": "Plan de energía de Windows: balanced | high_performance | power_saver"
                },
                "state": {
                    "type": "STRING",
                    "description": "Estado de No Molestar (Focus Assist): on | off | alarms"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "auto_programmer",
        "description": (
            "Suite de desarrollo y auto-programación autónoma avanzada. Permite a JARVIS escribir "
            "código Python para nuevas herramientas, validar sintaxis con py_compile, correr tests sintácticos "
            "en un sandbox con traceback detallado, corregir errores e inyectar plugins en caliente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "create_tool (crear/actualizar) | fix_tool (corregir error) | test_tool (probar en sandbox) | list_tools (listar creadas)"
                },
                "tool_name": {
                    "type": "STRING",
                    "description": "Nombre de la herramienta en snake_case"
                },
                "description": {
                    "type": "STRING",
                    "description": "Descripción clara de la herramienta y su uso"
                },
                "parameters_schema": {
                    "type": "STRING",
                    "description": "JSON de propiedades de parámetros. Ej: '{\"param\": {\"type\": \"STRING\"}}'"
                },
                "python_code": {
                    "type": "STRING",
                    "description": "Código Python con la función def <tool_name>(parameters: dict, player=None) -> str:"
                },
                "test_parameters": {
                    "type": "OBJECT",
                    "description": "Parámetros mock de prueba para evaluar la ejecución de la función en el sandbox"
                }
            },
            "required": ["action", "tool_name"]
        }
    },
    {
        "name": "self_edit",
        "description": (
            "Auto-edición de código: JARVIS puede leer, modificar, crear y gestionar sus propios archivos de código fuente. "
            "Crea backups automáticos antes de cada cambio. "
            "USAR cuando el usuario pida: 'editá tu código', 'cambiá tu prompt', 'agregá esta función', "
            "'modificá tu comportamiento', 'mejorate', 'aprendé a hacer X editando tu código', "
            "o cuando JARVIS necesite auto-mejorarse, corregir bugs propios o agregar capacidades. "
            "Puede editar: main.py, core/prompt.txt, actions/*.py, config/*, o cualquier archivo del proyecto."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "read_file — leer un archivo del proyecto | "
                        "edit_file — buscar y reemplazar texto en un archivo (requiere target y replacement) | "
                        "append_file — agregar contenido al final de un archivo | "
                        "create_file — crear o sobrescribir un archivo | "
                        "list_files — listar archivos de un directorio | "
                        "list_backups — ver backups disponibles | "
                        "restore_backup — restaurar un backup anterior"
                    )
                },
                "file": {
                    "type": "STRING",
                    "description": "Ruta del archivo relativa al proyecto (ej: 'main.py', 'actions/terminal_agent.py', 'core/prompt.txt')"
                },
                "target": {
                    "type": "STRING",
                    "description": "Para edit_file: el texto EXACTO a buscar (incluyendo espacios e indentación)"
                },
                "replacement": {
                    "type": "STRING",
                    "description": "Para edit_file: el texto que reemplazará al target"
                },
                "content": {
                    "type": "STRING",
                    "description": "Para append_file/create_file: el contenido a escribir"
                },
                "directory": {
                    "type": "STRING",
                    "description": "Para list_files: directorio a listar (default: raíz del proyecto)"
                },
                "backup_name": {
                    "type": "STRING",
                    "description": "Para restore_backup: nombre del archivo .bak a restaurar"
                }
            },
            "required": ["action"]
        }
    },
]

# Cargar herramientas dinámicas creadas por tool_creator
try:
    _custom_tools_path = BASE_DIR / "actions" / "custom_tools.json"
    if _custom_tools_path.exists():
        _custom_tools = json.loads(_custom_tools_path.read_text(encoding="utf-8"))
        if isinstance(_custom_tools, list):
            for _t in _custom_tools:
                if _t.get("name") not in [td["name"] for td in TOOL_DECLARATIONS]:
                    TOOL_DECLARATIONS.append(_t)
except Exception as _e:
    pass

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.is_sleeping    = False
        # Cargar sensibilidad del micrófono (puerta de ruido) de la configuración
        cfg_keys = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg_keys = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        self.noise_gate_threshold = float(cfg_keys.get("mic_sensitivity", 0.003))
        self.last_speech_time     = 0.0
        self._is_transmitting_turn = False

        self.vosk_recognizer = None
        try:
            import vosk
            if os.path.exists("config/vosk_model"):
                model = vosk.Model("config/vosk_model")
                self.vosk_recognizer = vosk.KaldiRecognizer(model, 16000)
                print("[JARVIS] Modelo Vosk cargado para Modo Suspensión.")
        except Exception as e:
            print(f"[JARVIS] No se pudo cargar Vosk: {e}")
        self.audio_in_queue = None
        # Iniciar scheduler y motor de reglas en background al arrancar JARVIS
        start_runner(player=ui, speak=None)
        start_rules_runner(player=ui, speak=None)

        # Wake word — se inicia SOLO cuando JARVIS entra en suspensión,
        # para no competir con el micrófono de la sesión Gemini Live activa.
        self._wake_word_available = False
        try:
            import core.wake_word as _ww_mod  # noqa: F401 — solo verificar disponibilidad
            self._wake_word_available = True
        except Exception:
            pass

        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_stop_command = self._on_stop_pressed
        self.ui.on_config_saved = self._apply_config
        self.ui.on_file_analyze = self._on_file_analyze
        self._turn_done_event: asyncio.Event | None = None
        self._api_1011_tool: str | None = None   # tracks tool name when 1011 hits
        self._reconnect_event: asyncio.Event | None = None
        self._first_connect = True  # flag for auto morning brief + guardian start

        # ── Activity panel (PyQt) ────────────────────────────────────────────
        self.activity_panel = None
        if _ActivityPanel is not None:
            try:
                self.activity_panel = _ActivityPanel(parent=None)
                _position_panel(self.activity_panel)
                # No mostrar al inicio — el usuario lo abre con un comando
                _jlog_info("Activity panel inicializado", category="system")
            except Exception as e:
                _jlog_error("Activity panel no se pudo crear", exc=e)

        # ── Hotkey global Ctrl+Alt+J ─────────────────────────────────────────
        def _on_attention_hotkey():
            try:
                _jlog_info("Hotkey de atención activado", category="audio")
                # Forzar que JARVIS escuche: si está dormido, despertarlo
                if getattr(self, "is_sleeping", False):
                    self.is_sleeping = False
                # Inyectar un ping para que responda
                self._inject_text("(El usuario pulsó el atajo de atención. Diga 'Sí, señor.' brevemente y espere instrucciones.)")
            except Exception as e:
                _jlog_error("Fallo en handler de hotkey", exc=e)
        try:
            _register_hotkey(_on_attention_hotkey, combo="ctrl+alt+j")
        except Exception:
            pass

        # ── Notificación de fin de tarea (task_queue) ────────────────────────
        def _on_task_done(task):
            try:
                if task.status == "done":
                    self._inject_text(
                        f"(Tarea en segundo plano completada: '{task.title}'. "
                        f"Notifíquele al usuario de manera breve.)"
                    )
                elif task.status == "failed":
                    self._inject_text(
                        f"(Tarea '{task.title}' falló: {task.error}. Reporte al usuario.)"
                    )
            except Exception:
                pass
        try:
            _task_set_notify(_on_task_done)
        except Exception:
            pass

        # ── Motor proactivo: sugerencias basadas en patrones ─────────────────
        try:
            from core.proactive_engine import start_loop as _proactive_start
            def _on_proactive_suggestion(suggestion):
                try:
                    # No interrumpir si JARVIS está hablando o el usuario en turno
                    if getattr(self, "_is_speaking", False) or getattr(self, "_is_transmitting_turn", False):
                        return
                    self._inject_text(
                        f"(Sugerencia proactiva interna basada en patrones del usuario, score={suggestion.score}: "
                        f"\"{suggestion.message}\" — usa esto solo si el momento es apropiado, "
                        "y de manera breve. NO repitas la sugerencia si el usuario está claramente ocupado.)"
                    )
                except Exception:
                    pass
            _proactive_start(_on_proactive_suggestion, interval_s=900)   # cada 15min
            _jlog_info("Motor proactivo iniciado", category="system")
        except Exception as e:
            _jlog_error("No se pudo iniciar motor proactivo", exc=e)

        _jlog_session("init_complete")

    def _inject_text(self, text: str):
        """Thread-safe injection of a text message into the current live session."""
        if self._loop and self.session and not self._is_speaking:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )

    def _on_file_analyze(self, content: str, filename: str, path: str):
        """
        Called when the user clicks '📖 Analizar con JARVIS' in Files Drop.
        Injects the file content into the live Gemini session so JARVIS can
        read and respond to it.
        """
        if not self._loop or not self.session:
            self.ui.write_log("⚠ JARVIS no está conectado. Intenta de nuevo en un momento.")
            return

        # ── Image files: send as inline_data ─────────────────────────────────
        if content.startswith("__IMAGE_B64__"):
            try:
                _, rest    = content.split("__IMAGE_B64__", 1)
                mime, b64  = rest.split("::", 1)
                import base64
                img_bytes  = base64.b64decode(b64)
                text_part  = {"text": f"Analiza esta imagen que acabo de soltar: '{filename}'."}
                image_part = {"inline_data": {"mime_type": mime, "data": b64}}
                asyncio.run_coroutine_threadsafe(
                    self.session.send_client_content(
                        turns={"parts": [text_part, image_part]},
                        turn_complete=True
                    ),
                    self._loop
                )
                self.ui.write_log(f"🖼 Imagen '{filename}' enviada a Gemini Vision.")
            except Exception as e:
                self.ui.write_log(f"⚠ Error enviando imagen: {e}")
            return

        # ── Text / document files ─────────────────────────────────────────────
        # Build a clear instruction so Gemini knows what to do
        prompt = (
            f"El usuario acaba de soltar el archivo '{filename}' en la interfaz. "
            f"A continuación está su contenido completo. Léelo, entiéndelo y "
            f"espera instrucciones del usuario sobre qué hacer con él "
            f"(resumir, analizar, editar, responder preguntas, etc.).\n\n"
            f"{content}"
        )
        self._inject_text(prompt)
        self.ui.write_log(f"📖 '{filename}' enviado a JARVIS ({len(content):,} chars). "
                          f"Di qué quieres hacer con él.")

    def _apply_config(self, cfg: dict):
        """Called from UI thread when user saves settings. Triggers session reconnect."""
        global _cached_api_key
        _cached_api_key = None  # Invalidate cached key so new one is loaded on reconnect
        
        # Actualizar dinámicamente la puerta de ruido sin reiniciar
        self.noise_gate_threshold = float(cfg.get("mic_sensitivity", 0.003))
        
        print("[JARVIS] ⚙️ Config actualizada — reconectando sesión...")
        self.ui.write_log("SYS: Aplicando nueva configuración...")
        if self._reconnect_event and self._loop:
            self._loop.call_soon_threadsafe(self._reconnect_event.set)

    async def _watch_reconnect(self):
        """Task that triggers a graceful reconnect when config changes."""
        if self._reconnect_event:
            await self._reconnect_event.wait()
            raise RuntimeError("Config changed — reconnect requested")

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return

        if getattr(self, "is_sleeping", False):
            # Check if text contains wake word or despierta
            text_lower = text.lower()
            if any(w in text_lower for w in ["despierta", "despiertate", "despiértate", "despertar", "jarvis", "wake up"]):
                self.is_sleeping = False
                self.ui.set_state("LISTENING")
                self.ui.write_log("SYS: 🟢 ¡Despierto por comando de texto!")
                # Play sound
                try:
                    import winsound
                    winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                except: pass
            else:
                self.ui.write_log("SYS: 💤 Jarvis está en modo suspensión. Di 'JARVIS' o escribe 'despierta' para despertarlo.")
                return

        # Audio file: process with Gemini Vision (not the realtime audio session)
        if text.startswith("[AUDIO_FILE]"):
            m = re.search(r'path=([^\s|]+)', text)
            if m:
                asyncio.run_coroutine_threadsafe(
                    self._process_audio_file(m.group(1)), self._loop
                )
            return

        # Check phrase triggers — if one fires, don't also send to Gemini
        if self._fire_phrase_triggers(text):
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _process_audio_file(self, path: str):
        """Transcribe and analyze an audio file via Gemini (separate from realtime session)."""
        try:
            p = Path(path)
            if not p.exists():
                self.ui.write_log(f"❌ Archivo no encontrado: {path}")
                return

            self.ui.set_state("THINKING")
            self.ui.write_log(f"🎵 Procesando audio: {p.name}…")

            data = p.read_bytes()
            ext  = p.suffix.lower().lstrip(".")
            mime_map = {
                "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
                "ogg": "audio/ogg",  "flac": "audio/flac", "aac": "audio/aac",
                "wma": "audio/x-ms-wma", "opus": "audio/opus", "webm": "audio/webm",
            }
            mime = mime_map.get(ext, "audio/mpeg")

            loop = asyncio.get_event_loop()

            def _analyze():
                client = genai.Client(api_key=_get_api_key())
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Content(parts=[
                            types.Part(text=(
                                f"El usuario adjuntó un archivo de audio: '{p.name}'.\n"
                                "1. Transcribí el contenido del audio.\n"
                                "2. Si es música, identificá la canción/artista si podés.\n"
                                "3. Describí brevemente qué contiene.\n"
                                "Respondé en español."
                            )),
                            types.Part(
                                inline_data=types.Blob(data=data, mime_type=mime)
                            ),
                        ])
                    ],
                )
                return resp.text.strip()

            result = await loop.run_in_executor(_TOOL_EXECUTOR, _analyze)
            self.ui.write_log(f"JARVIS: {result}")

            # Feed result back into the realtime session so JARVIS can speak it
            if self.session:
                await self.session.send_client_content(
                    turns={"parts": [{"text": f"[RESULTADO AUDIO '{p.name}']\n{result}"}]},
                    turn_complete=True
                )

        except Exception as e:
            traceback.print_exc()
            self.ui.write_log(f"❌ Error procesando audio: {e}")
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def _fire_phrase_triggers(self, user_text: str) -> bool:
        """
        Check phrase-based automations. Returns True if any trigger fired
        (caller should skip sending the text to Gemini in that case).
        """
        text_lower = user_text.lower()

        # ── Accessibility quick triggers ──────────────────────────────────────
        if any(p in text_lower for p in ["activar seguimiento ocular", "iniciar eye tracking",
                                          "activar control ocular", "encender seguimiento de ojos"]):
            if eye_tracking:
                result = eye_tracking({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener seguimiento ocular", "apagar eye tracking",
                                          "desactivar control ocular"]):
            if eye_tracking:
                result = eye_tracking({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["activar detector de movimientos", "iniciar movimiento",
                                          "activar micromovimientos", "encender control por cabeza"]):
            if micro_movement:
                result = micro_movement({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener detector de movimientos", "apagar micromovimientos"]):
            if micro_movement:
                result = micro_movement({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["simplifica", "simplificar", "dividir en pasos"]):
            for phrase in ["simplifica ", "simplificar ", "dividir en pasos "]:
                if phrase in text_lower:
                    task_text = user_text[len(phrase):].strip()
                    if task_text:
                        if task_simplify:
                            result = task_simplify(task_text)
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ [Simplificado]\n" + result[:300])
                        return True

        if "agregar rutina" in text_lower or "nueva rutina" in text_lower:
            for phrase in ["agregar rutina ", "nueva rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "add", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "completar rutina" in text_lower or "terminar rutina" in text_lower:
            for phrase in ["completar rutina ", "terminar rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "complete", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "mis rutinas" in text_lower or "ver rutinas" in text_lower or "listar rutinas" in text_lower:
            if routine_gamify:
                result = routine_gamify({"action": "list"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ [Rutinas]\n" + result)
            return True

        # ── User-defined phrase automations ───────────────────────────────────
        try:
            triggered = check_phrase_triggers(user_text)
            if triggered:
                for rule in triggered:
                    action = rule.get("action", {})
                    name   = rule.get("name", "?")
                    self.ui.write_log(f"⚡ Automatización: {name}")
                    threading.Thread(
                        target=_rules_run_action, args=(action,), daemon=True
                    ).start()
                return True  # phrase fired → don't also send to Gemini
        except Exception as e:
            print(f"[JARVIS] phrase trigger error: {e}")

        return False

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"I'm afraid {tool_name} ran into a problem, sir. {short}")

    def _on_stop_pressed(self):
        """Llamado desde el hilo de la UI al presionar DETENER o ESC."""
        self._stop_requested.set()
        self.set_speaking(False)
        self.ui.write_log("SYS: ⛔ Respuesta detenida.")
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._drain_audio_queue(), self._loop)

    async def _drain_audio_queue(self):
        """Vacía la cola de audio para cortar la reproducción de inmediato."""
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
        self.set_speaking(False)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        sys_prompt = _load_system_prompt()

        # Refresh timezone from config each reconnect
        _load_tz()
        now      = datetime.now(_BA_TZ)
        time_str = now.strftime("%A, %d %B %Y — %I:%M:%S %p")
        utc_off  = now.strftime("%z")
        tz_name  = str(_BA_TZ)
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Timezone: {tz_name} (UTC{utc_off})\n"
            f"The current Unix timestamp is: {int(now.timestamp())}\n"
            f"Use this information to calculate exact times for reminders, scheduling, and answering time-related questions.\n\n"
        )

        # Rich memory context (long-term + session history + recent turns)
        rich_memory = get_context_block()
        # Also keep backward compat with old memory_manager for habits/notes
        old_mem = load_memory()
        old_mem_str = format_memory_for_prompt(old_mem)

        parts = [time_ctx]
        if rich_memory:
            parts.append(rich_memory)
        elif old_mem_str:
            # Fallback if engine has nothing yet
            parts.append(old_mem_str)

        # ── Correcciones aprendidas (feedback de turnos previos) ──────────────
        try:
            from core.correction_learner import format_corrections_for_prompt
            corr = format_corrections_for_prompt(limit=10)
            if corr:
                parts.append(corr)
        except Exception:
            pass

        # ── Contexto inmediato pre-reconexión (si aplica) ─────────────────────
        try:
            from core.session_buffer import format_for_reinjection, is_recent_reconnect_context
            if is_recent_reconnect_context() and not self._first_connect:
                ctx = format_for_reinjection()
                if ctx:
                    parts.append(ctx)
        except Exception:
            pass

        # ── Estado emocional del usuario (hint dinámico) ──────────────────────
        try:
            from core.emotion_detector import current_prompt_hint
            ehint = current_prompt_hint()
            if ehint:
                parts.append(ehint)
        except Exception:
            pass

        # ── Estado del modo focus ─────────────────────────────────────────────
        try:
            from core.focus_mode import status as _focus_status
            fs = _focus_status()
            if fs["active"]:
                parts.append(
                    f"[MODO CONCENTRACIÓN ACTIVO — {fs['remaining_min']}min restantes"
                    + (f" ({fs['reason']})" if fs["reason"] else "")
                    + "]\n  → Suprime sugerencias proactivas. Responde breve. "
                    "Solo interrumpe el silencio si el usuario inicia turno o hay emergencia."
                )
        except Exception:
            pass

        parts.append(sys_prompt)

        # Build SpeechConfig — try to set speaking rate for faster delivery
        _voice_name = _get_jarvis_voice()
        _speech_cfg = None
        try:
            _speech_cfg = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_voice_name
                    )
                )
            )
        except Exception:
            _speech_cfg = None

        cfg_kwargs: dict = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
        )
        if _speech_cfg:
            cfg_kwargs["speech_config"] = _speech_cfg

        # Speaking rate: try output_audio_config (newer SDK versions)
        try:
            cfg_kwargs["output_audio_config"] = types.OutputAudioConfig(
                audio_encoding="LINEAR16",
                speaking_rate=1.15,   # 15% faster — crisp, natural pace
            )
        except Exception:
            pass

        # Temperature directly on LiveConnectConfig (not via deprecated generation_config)
        # Low value = consistent voice tone across reconnects
        try:
            cfg_kwargs["temperature"] = 0.2
        except Exception:
            pass

        # ── VAD: faster end-of-speech detection → lower perceived latency ────
        # Try typed objects first; fall back to raw dict (SDK version resilience)
        _vad_applied = False
        try:
            cfg_kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                    end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                    prefix_padding_ms=60,
                    silence_duration_ms=350,
                )
            )
            _vad_applied = True
            print("[JARVIS] VAD config aplicado (typed)")
        except Exception:
            pass

        if not _vad_applied:
            try:
                cfg_kwargs["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                        "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                        "prefix_padding_ms": 100,
                        "silence_duration_ms": 500,
                    }
                }
                print("[JARVIS] VAD config aplicado (dict)")
            except Exception:
                print("[JARVIS] VAD config no aplicado")

        # ── Context compression: prevent session degradation over time ────────
        try:
            cfg_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                trigger_tokens=12000,
                sliding_window=types.SlidingWindow(target_tokens=6000),
            )
        except Exception:
            pass

        # ── Thinking budget: disable model reasoning for lowest latency ─────────
        # Set directly on LiveConnectConfig (generation_config field is deprecated)
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

        return types.LiveConnectConfig(**cfg_kwargs)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        # Tiempo inicial para medir duración
        _tool_t0 = time.time()
        _jlog_tool(name, args=args, success=True, result_preview="[started]")

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")
        # Show active tool in header indicator
        try:
            self.ui.set_active_tool(name)
        except Exception:
            pass
        # Sync con activity panel
        try:
            if getattr(self, "activity_panel", None):
                self.activity_panel.set_current_tool(name)
        except Exception:
            pass



        if name == "activate_protocol":
            protocol_name = args.get("protocol_name", "")
            try:
                from core.protocols import get_protocol
                instructions = get_protocol(protocol_name)
                if instructions:
                    return types.FunctionResponse(
                        id=fc.id, name=name,
                        response={"result": f"Protocolo '{protocol_name}' encontrado. INSTRUCCIONES DEL USUARIO (DEBES EJECUTARLAS INMEDIATAMENTE USANDO TUS HERRAMIENTAS): {instructions}"}
                    )
                else:
                    return types.FunctionResponse(
                        id=fc.id, name=name,
                        response={"result": f"No se encontró el protocolo llamado '{protocol_name}'."}
                    )
            except Exception as e:
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": f"Error loading protocol: {e}"}
                )

        if name == "shutdown_jarvis":
            self.ui.write_log("SYS: Apagando JARVIS...")
            # Must quit from Qt main thread — signals are thread-safe
            self.ui._win._shutdown_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Apagando JARVIS. ¡Hasta luego, señor!"}
            )

        if name == "pair_programming":
            if pair_programming:
                self.ui.write_log("🧑‍💻 Pair programming...")
                # Pasar la propia instancia para que el módulo acceda al activity_panel
                r = pair_programming(parameters=args, player=self)
                result = r or "Acción de pair programming completada."
            else:
                result = "Módulo pair_programming no disponible."
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "focus_mode":
            try:
                from core.focus_mode import enable, disable, status as focus_status
                action = (args.get("action") or "status").lower()
                if action == "enable":
                    dur = int(args.get("duration_minutes", 60))
                    reason = args.get("reason", "")
                    st = enable(duration_minutes=dur, reason=reason)
                    result = (
                        f"Modo concentración activado por {st['remaining_min']} minutos"
                        + (f" — {reason}." if reason else ".")
                        + " Estaré en silencio salvo emergencias, señor."
                    )
                elif action == "disable":
                    disable()
                    result = "Modo concentración desactivado. Vuelvo a estar atento."
                else:
                    st = focus_status()
                    if st["active"]:
                        result = f"Modo concentración activo, quedan {st['remaining_min']} minutos."
                    else:
                        result = "Modo concentración inactivo."
            except Exception as e:
                result = f"Error en focus_mode: {e}"
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "task_status":
            action = (args.get("action") or "summary").lower()
            if action == "list":
                tasks = _task_list(limit=10)
                if not tasks:
                    result = "No hay tareas en curso ni recientes, señor."
                else:
                    lines = [f"- {t.title} [{t.status}] {int(t.duration_s())}s"
                             for t in tasks]
                    result = "Estado de tareas:\n" + "\n".join(lines)
            else:
                result = _task_voice_summary()
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "show_activity_panel":
            show = bool(args.get("show", True))
            try:
                if self.activity_panel is not None:
                    if show:
                        self.activity_panel.show()
                        result = "Panel de actividad mostrado, señor."
                    else:
                        self.activity_panel.hide()
                        result = "Panel ocultado."
                else:
                    result = "El panel de actividad no está disponible en este sistema."
            except Exception as e:
                result = f"Error con el panel: {e}"
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "usage_dashboard":
            try:
                from core.usage_dashboard import collect_stats, format_text, format_html
                action_kind = (args.get("action") or "text").lower()
                stats = collect_stats()
                if action_kind == "html":
                    html = format_html(stats)
                    # Mostrar como holograma
                    self.ui._win._holo_sig.emit("", html)
                    result = "Dashboard mostrado en el holograma, señor."
                else:
                    result = format_text(stats)
            except Exception as e:
                result = f"Error generando dashboard: {e}"
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "system_diagnostics":
            try:
                stats = memory_stats()
                from core.jarvis_logger import get_stats as _log_stats
                from core.quota_manager import get_status as _quota_status
                _log_stats()  # warm
                quota = _quota_status()
                provider_parts = []
                for p, s in quota.items():
                    provider_parts.append(f"{p}({s.get('status','?')})")
                lines = [
                    f"MEMORIA: {stats.get('long_term_entries',0)} hechos, "
                    f"{stats.get('recent_turns',0)} turnos recientes, "
                    f"{stats.get('total_turns_logged',0)} turnos totales",
                    f"PROVEEDORES: {', '.join(provider_parts)}",
                ]
                result = "Diagnóstico:\n" + "\n".join(lines)
            except Exception as e:
                result = f"Error en diagnóstico: {e}"
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "show_hologram":
            url = args.get("url", "")
            html = args.get("html", "")
            
            # Use Qt thread-safe signal instead of call_soon_threadsafe
            self.ui._win._holo_sig.emit(url, html)
            
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Widget holográfico mostrado al usuario con éxito."}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                # Save to both old memory_manager (compat) and new engine
                update_memory({category: {key: {"value": value}}})
                engine_remember(category, key, value, source="jarvis_explicit")
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Memory saved."}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "get_current_time":
                from datetime import datetime
                _load_tz()
                now = datetime.now(_BA_TZ)
                time_str = now.strftime("%A, %d %B %Y — %I:%M:%S %p")
                result = f"La hora actual exacta es: {time_str}"
                
            elif name == "open_app":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "sleep_mode":
                self.is_sleeping = True
                self.ui.write_log("SYS: 💤 Entrando en suspensión local.")
                self.ui.set_state("MUTED")
                # Immediately empty the audio in queue to stop any playing/queued audio
                if self.audio_in_queue:
                    while not self.audio_in_queue.empty():
                        try:
                            self.audio_in_queue.get_nowait()
                        except Exception:
                            break
                self.set_speaking(False)
                # Arrancar wake word AHORA que el micrófono quedó libre
                if getattr(self, "_wake_word_available", False):
                    try:
                        from core.wake_word import start_wake_word
                        def _on_wake():
                            if getattr(self, "is_sleeping", False):
                                # Detener wake word antes de retomar el micrófono
                                try:
                                    from core.wake_word import stop_wake_word
                                    stop_wake_word()
                                except Exception:
                                    pass
                                self.is_sleeping = False
                                self.ui.set_state("LISTENING")
                                self.ui.write_log("🎙 Wake word detectada — JARVIS activo")
                        start_wake_word(on_wake=_on_wake)
                    except Exception as _we:
                        print(f"[WakeWord] No se pudo iniciar: {_we}")
                result = "Entrando en suspensión absoluta. Cortando transmisión a la nube hasta escuchar 'JARVIS'."

            elif name == "weather_report":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "visual_click":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: visual_click(parameters=args, player=self.ui))
                result = r or "Done."



            elif name == "file_controller":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process" or name == "screen_vision":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: screen_vision(parameters=args, player=self.ui))
                result = r or "No pude analizar la imagen/pantalla."

            elif name == "computer_settings":
                action = args.get("action", "")
                if action == "volume":
                    val = args.get("value", "")
                    try:
                        import pyautogui
                        # Si es un número absoluto (ej: '50')
                        if str(val).isdigit():
                            target = int(val)
                            try:
                                from ctypes import cast, POINTER
                                from comtypes import CoInitialize, CoUninitialize
                                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                                CoInitialize()
                                devices = AudioUtilities.GetSpeakers()
                                interface = devices.Activate(IAudioEndpointVolume._iid_, 1, None)
                                volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
                                # Rango 0.0 a 1.0
                                scalar_vol = max(0.0, min(1.0, target / 100.0))
                                volume_ctrl.SetMasterVolumeLevelScalar(scalar_vol, None)
                                CoUninitialize()
                                result = f"Volumen ajustado al {target}%."
                            except Exception as e:
                                result = f"Error ajustando volumen absoluto: {e}"
                        else:
                            # Comando relativo: up, down, mute
                            if "up" in val.lower() or "subir" in val.lower():
                                pyautogui.press("volumeup", presses=5)
                                result = "Volumen subido."
                            elif "down" in val.lower() or "bajar" in val.lower():
                                pyautogui.press("volumedown", presses=5)
                                result = "Volumen bajado."
                            elif "mute" in val.lower() or "silenciar" in val.lower():
                                pyautogui.press("volumemute")
                                result = "Volumen silenciado."
                            else:
                                result = f"Acción de volumen no reconocida: {val}"
                    except Exception as ve:
                        result = f"Error en control de volumen: {ve}"
                else:
                    if action in ["window_minimize", "minimize"]:
                        if gw:
                            try:
                                window = gw.getActiveWindow()
                                if window: window.minimize()
                                result = "Ventana minimizada."
                            except Exception as e:
                                result = f"Error al minimizar: {e}"
                        else:
                            result = "Librería pygetwindow no disponible."
                    elif action in ["window_maximize", "maximize"]:
                        if gw:
                            try:
                                window = gw.getActiveWindow()
                                if window: window.maximize()
                                result = "Ventana maximizada."
                            except Exception as e:
                                result = f"Error al maximizar: {e}"
                        else:
                            result = "Librería pygetwindow no disponible."
                    else:
                        r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                        result = r or "Done."

            elif name == "desktop_control":
                if desktop_control is None:
                    result = "Módulo desktop_control no disponible."
                else:
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: desktop_control(parameters=args, player=self.ui))
                    result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and getattr(self.ui, "current_file_path", ""):
                    args["file_path"] = self.ui.current_file_path
                r = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "app_macro":
                from actions.app_macro import app_macro
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: app_macro(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                if game_updater is None:
                    result = "Módulo game_updater no disponible. Usa open_app para abrir Steam o Epic."
                else:
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                    result = r or "Done."

            elif name == "flight_finder":
                if flight_finder is None:
                    result = "Módulo flight_finder no disponible."
                else:
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: flight_finder(parameters=args, player=self.ui))
                    result = r or "Done."

            elif name == "google_calendar":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: google_calendar(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "spotify_control":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: spotify_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "rgb_control":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: rgb_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "scheduler":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: scheduler(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "google_drive":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: google_drive(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "google_maps":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: google_maps(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "gmail_control":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: gmail_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "rules_engine":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: rules_engine(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "user_profile":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: user_profile(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "goals":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: goals(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "git_control":
                if git_control is None:
                    result = "Módulo git_control no disponible."
                else:
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: git_control(parameters=args, player=self.ui))
                    result = r or "Done."

            elif name == "codebase":
                if codebase is None:
                    result = "Módulo codebase no disponible."
                else:
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: codebase(parameters=args, player=self.ui))
                    result = r or "Done."

            elif name == "knowledge_base":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: knowledge_base(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "whatsapp":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: whatsapp(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "netflix_control":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: netflix_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "social_media":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: social_media(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "windows_settings":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: windows_settings(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "document_creator":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: document_creator(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "image_generation":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: image_generation(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "smart_home":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: smart_home(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_monitor":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: system_monitor(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "tiktok_analyzer":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: tiktok_analyzer(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "arca_invoice":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: arca_invoice(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "accessibility":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: accessibility(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "notion_control":
                if notion_control is None:
                    result = "Módulo Notion no disponible."
                else:
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: notion_control(parameters=args, player=self.ui))
                    result = r or "Done."

            elif name == "morning_brief":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: morning_brief(parameters=args, player=self.ui))
                result = r or "Aquí está tu informe del día."

            elif name == "vision_guardian":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: vision_guardian(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "screen_reader":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: screen_reader(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "accessibility_overlay":
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: accessibility_overlay(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "openrouter_agent":
                if openrouter_agent:
                    # Se delega la tarea a OpenRouter
                    self.ui.write_log("🤖 Delegando tarea a OpenRouter...")
                    r = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: openrouter_agent(
                            query=args.get("query", ""),
                            model=args.get("model", "google/gemini-2.5-flash")
                        )
                    )
                    result = r or "Error al procesar con OpenRouter."
                else:
                    result = "Módulo openrouter_agent no encontrado."

            elif name == "deepseek_agent":
                if deepseek_agent:
                    self.ui.write_log("🧠 DeepSeek-R1 pensando...")
                    r = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: deepseek_agent(
                            query=args.get("query", ""),
                            system_prompt=args.get("system_prompt", None)
                        )
                    )
                    result = r or "Error al procesar con DeepSeek."
                else:
                    result = "Módulo deepseek_agent no disponible."

            elif name == "deep_research":
                if deep_research:
                    self.ui.write_log("📚 Iniciando investigación profunda en segundo plano...")
                    r = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: deep_research(parameters=args, player=self.ui)
                    )
                    result = r or "Investigación encolada."
                else:
                    result = "Módulo deep_research no disponible."

            elif name == "terminal_agent":
                if terminal_agent:
                    self.ui.write_log("⚠️ Ejecutando en Terminal...")
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: terminal_agent(parameters=args, player=self.ui))
                    result = r or "Comando ejecutado."
                else:
                    result = "Módulo terminal_agent no encontrado."

            elif name == "native_ui":
                if native_ui:
                    self.ui.write_log("💻 UI Nativa en acción...")
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: native_ui(parameters=args, player=self.ui))
                    result = r or "Acción de UI completada."
                else:
                    result = "Módulo native_ui no encontrado."

            elif name == "jarvis_ui_control":
                action_ui = args.get("action", "").lower()
                widget_name = args.get("widget", "").lower()
                if action_ui == "minimize":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showMinimized"):
                            QMetaObject.invokeMethod(self.ui._win, "showMinimized", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "iconify"):
                            self.ui.root.after(0, self.ui.root.iconify)
                        result = "Interfaz de usuario minimizada."
                    except Exception as ui_e:
                        result = f"Error al minimizar: {ui_e}"
                elif action_ui == "restore":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                            QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                            QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                            def _restore():
                                self.ui.root.deiconify()
                                self.ui.root.attributes("-topmost", True)
                                self.ui.root.attributes("-topmost", False)
                            self.ui.root.after(0, _restore)
                        result = "Interfaz de usuario restaurada."
                    except Exception as ui_e:
                        result = f"Error al restaurar: {ui_e}"
                elif action_ui == "hide_all":
                    self.ui.write_log("__hide__")
                    result = "Todos los widgets ocultados."
                elif action_ui in ("show", "hide", "toggle"):
                    if widget_name == "main_window" or not widget_name:
                        if action_ui == "show":
                            try:
                                if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                                    QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                                    QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                                elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                                    def _restore():
                                        self.ui.root.deiconify()
                                        self.ui.root.attributes("-topmost", True)
                                        self.ui.root.attributes("-topmost", False)
                                    self.ui.root.after(0, _restore)
                                result = "Interfaz de usuario restaurada."
                            except Exception as ui_e:
                                result = f"Error al restaurar: {ui_e}"
                        else:
                            self.ui.write_log("__hide__")
                            result = "Todos los widgets ocultados."
                    else:
                        cmd = "__widget_show__" if action_ui in ("show", "toggle") else "__widget_close__"
                        self.ui.write_log(f"{cmd}:{widget_name}")
                        result = f"Widget '{widget_name}' {'mostrado' if 'show' in cmd else 'ocultado'}."
                else:
                    result = f"Acción de UI desconocida: {action_ui}"

            else:
                # Intento de cargar herramienta dinámica (tool_creator u otras)
                import importlib
                import inspect
                try:
                    module = importlib.import_module(f"actions.{name}")
                    func = getattr(module, name)
                    sig = inspect.signature(func)
                    kwargs = {"parameters": args, "player": self.ui}
                    if "speak" in sig.parameters: kwargs["speak"] = self.speak
                    r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: func(**kwargs))
                    result = r or f"Herramienta {name} ejecutada."
                except Exception as dyn_e:
                    result = f"Unknown tool: {name}. (Dynamic load failed: {dyn_e})"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        # Record action for habit learning (fire-and-forget, non-blocking)
        if record_action:
            threading.Thread(target=lambda: record_action(name, args), daemon=True).start()

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        # Clear active tool indicator
        try:
            self.ui.set_active_tool("")
        except Exception:
            pass
        try:
            if getattr(self, "activity_panel", None):
                self.activity_panel.set_current_tool("")
        except Exception:
            pass

        # Logging estructurado del resultado
        _dur_ms = int((time.time() - _tool_t0) * 1000)
        _jlog_tool(name, args=args, result_preview=str(result)[:200],
                   duration_ms=_dur_ms, success=True)

        # Auto-holograma contextual basado en el resultado
        try:
            from core.hologram_helpers import auto_hologram_from_tool_result
            holo_html = auto_hologram_from_tool_result(name, result, args)
            if holo_html:
                self.ui._win._holo_sig.emit("", holo_html)
        except Exception as _holo_err:
            _jlog_warn(f"auto-holograma falló para {name}: {_holo_err}")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic iniciado")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if getattr(self, "is_sleeping", False):
                if getattr(self, "vosk_recognizer", None):
                    audio_data = indata.tobytes()
                    if self.vosk_recognizer.AcceptWaveform(audio_data):
                        res = json.loads(self.vosk_recognizer.Result())
                        text = res.get("text", "")
                        if "jarvis" in text.lower():
                            self.is_sleeping = False
                            self.ui.set_state("LISTENING")
                            self.ui.write_log("SYS: 🟢 ¡Despierto!")
                            try:
                                import winsound
                                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                            except: pass
                return

            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                # Calculate RMS audio level for sphere visualization
                rms = 0.0
                try:
                    rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                    self.ui.set_audio_level(min(1.0, rms * 18))
                except Exception:
                    pass

                # Filtro de Puerta de Ruido Adaptativo (VAD local dinámico en tiempo real)
                import time
                now = time.time()
                threshold = getattr(self, "noise_gate_threshold", 0.003)
                
                # Inicializar y actualizar el piso de ruido dinámico (rolling minimum)
                if not hasattr(self, "_noise_floor_samples"):
                    self._noise_floor_samples = []
                    self._last_noise_floor_update = now
                
                # Tomar muestra cada 100ms
                if now - getattr(self, "_last_noise_floor_update", 0.0) > 0.1:
                    self._noise_floor_samples.append(rms)
                    self._last_noise_floor_update = now
                    # Mantener últimas 50 muestras (~5 segundos)
                    if len(self._noise_floor_samples) > 50:
                        self._noise_floor_samples.pop(0)
                    
                    # El ruido base ambiental es el mínimo RMS de los últimos 5s
                    self._ambient_noise_floor = min(self._noise_floor_samples)
                
                def _safe_put(q, item):
                    try:
                        q.put_nowait(item)
                    except Exception:
                        pass

                # Noise gate local: solo se aplica si threshold > 0.001
                # Con threshold bajo (<= 0.001) se envía todo el audio y Gemini
                # usa su propio VAD incorporado para detectar voz real.
                if threshold <= 0.001:
                    # Enviar siempre — VAD de Gemini filtra el silencio
                    loop.call_soon_threadsafe(
                        _safe_put, self.out_queue, {"data": indata.tobytes(), "mime_type": "audio/pcm"}
                    )
                else:
                    # Noise gate local para threshold alto configurado por el usuario
                    ambient_floor = getattr(self, "_ambient_noise_floor", 0.001)
                    dynamic_threshold = max(threshold, ambient_floor * 1.3)
                    if rms > dynamic_threshold:
                        self.last_speech_time = now
                    if now - getattr(self, "last_speech_time", 0.0) < 0.8:
                        loop.call_soon_threadsafe(
                            _safe_put, self.out_queue, {"data": indata.tobytes(), "mime_type": "audio/pcm"}
                        )
            elif jarvis_speaking:
                # When JARVIS is speaking, also update level (from playback perspective)
                try:
                    rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                    self.ui.set_audio_level(min(1.0, rms * 15))
                except Exception:
                    pass

        # Leer mic_device de config (0 = default del sistema)
        _mic_device = None
        try:
            _cfg = {}
            if API_CONFIG_PATH.exists():
                _cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            _dev_idx = int(_cfg.get("mic_device", -1))
            if _dev_idx >= 0:
                _mic_device = _dev_idx
        except Exception:
            pass

        try:
            _stream_kwargs: dict = dict(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            )
            if _mic_device is not None:
                _stream_kwargs["device"] = _mic_device
            with sd.InputStream(**_stream_kwargs):
                print(f"[JARVIS] 🎤 Mic stream open (device={_mic_device})")
                while True:
                    await asyncio.sleep(0.01)  # 10ms — máxima responsividad del mic
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            # Fallback: intentar con device default si el configurado falla
            if _mic_device is not None:
                print(f"[JARVIS] 🔄 Reintentando con device default...")
                try:
                    with sd.InputStream(
                        samplerate=SEND_SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=CHUNK_SIZE,
                        callback=callback,
                    ):
                        print("[JARVIS] 🎤 Mic stream open (default device)")
                        while True:
                            await asyncio.sleep(0.01)
                except Exception as e2:
                    print(f"[JARVIS] ❌ Mic fallback: {e2}")
                    raise
            else:
                raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv iniciado")
        out_buf, in_buf = [], []
        _first_chunk   = True
        _last_tool     = None   # track which tool was executing when error hit
        _tools_this_turn: list[str] = []   # tools called in current turn

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if not self._stop_requested.is_set() and not getattr(self, "is_sleeping", False):
                            self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                if _first_chunk:
                                    self.ui.clear_jarvis_response()
                                    _first_chunk = False
                                self.ui.stream_jarvis_chunk(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            self._stop_requested.clear()
                            if self._turn_done_event:
                                self._turn_done_event.set()
                            full_in  = " ".join(in_buf).strip()
                            full_out = " ".join(out_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Tú: {full_in}")
                                self._fire_phrase_triggers(full_in)
                            # ── Persist this turn to memory engine ────────────
                            if full_in or full_out:
                                import threading as _th
                                _th.Thread(
                                    target=record_turn,
                                    args=(full_in, full_out, list(_tools_this_turn)),
                                    daemon=True
                                ).start()
                                # Buffer volátil para recovery de contexto al reconectar
                                try:
                                    from core.session_buffer import push as _sb_push
                                    _sb_push(full_in, full_out)
                                except Exception:
                                    pass
                                # Detección de correcciones del usuario
                                try:
                                    from core.correction_learner import maybe_save_correction
                                    _th.Thread(
                                        target=maybe_save_correction,
                                        args=(full_in, full_out),
                                        daemon=True
                                    ).start()
                                except Exception:
                                    pass
                                # Detección de estado emocional del usuario
                                try:
                                    from core.emotion_detector import update_from_user_text
                                    update_from_user_text(full_in)
                                except Exception:
                                    pass
                            in_buf  = []
                            out_buf = []
                            _tools_this_turn = []
                            _first_chunk = True

                    if response.tool_call:
                        self.ui.clear_jarvis_response()
                        _first_chunk = True
                        fcs = response.tool_call.function_calls
                        for fc in fcs:
                            print(f"[JARVIS] 📞 {fc.name}")
                            _last_tool = fc.name
                            _tools_this_turn.append(fc.name)
                        async def _handle_tools(fcs_to_run):
                            nonlocal _last_tool
                            if len(fcs_to_run) > 1:
                                tasks = [asyncio.create_task(self._execute_tool(fc)) for fc in fcs_to_run]
                                fn_responses = list(await asyncio.gather(*tasks))
                            else:
                                fn_responses = [await self._execute_tool(fcs_to_run[0])]
                            try:
                                await self.session.send_tool_response(
                                    function_responses=fn_responses
                                )
                                _last_tool = None  # only clear AFTER successful send
                            except Exception as tool_err:
                                print(f"[JARVIS] ❌ send_tool_response failed: {tool_err}")
                                
                        # Ejecutar herramientas en background para no bloquear el receive del websocket
                        asyncio.create_task(_handle_tools(fcs))
        except Exception as e:
            msg  = str(e)
            code = getattr(e, "status_code", 0) or getattr(e, "code", 0) or 0
            # Detect 1011 (internal server error) regardless of exception type
            if code == 1011 or "1011" in msg or "Internal error" in msg:
                tool_info = f" durante '{_last_tool}'" if _last_tool else ""
                print(f"[JARVIS] ⚡ API 1011{tool_info} — reconectando...")
                self._api_1011_tool = _last_tool
            else:
                print(f"[JARVIS] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play iniciado")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=PLAY_CHUNK_SIZE,
        )
        stream.start()

        # Jitter buffer: accumulate a few chunks before playback to prevent underruns
        _jitter_buf: list[bytes] = []
        _JITTER_TARGET = 1  # ~20ms — start playback ASAP for low latency

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.05   # 50ms — faster turn-complete detection
                    )
                except asyncio.TimeoutError:
                    # Must check turn_done + empty BEFORE jitter guard,
                    # otherwise 1-2 stuck chunks in jitter_buf prevent
                    # ever reaching the turn_done check → infinite SPEAKING loop.
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        # Drain remaining jitter buffer before stopping
                        for buffered in _jitter_buf:
                            await asyncio.to_thread(stream.write, buffered)
                        _jitter_buf.clear()
                        
                        # Wait 300ms to allow OS audio buffer to play out and room echo to decay
                        # before re-enabling the microphone (prevents Jarvis hearing itself and cutting off)
                        await asyncio.sleep(0.3)
                        
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)
                _jitter_buf.append(chunk)

                # Once we have enough chunks buffered, drain them to the output stream
                if len(_jitter_buf) >= _JITTER_TARGET:
                    for buffered in _jitter_buf:
                        await asyncio.to_thread(stream.write, buffered)
                    _jitter_buf.clear()
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        reconnect_delay   = 1.0
        consecutive_fails = 0

        while True:
            try:
                print("[JARVIS] 🔌 Conectando...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=5)  # buffer moderado — evita drops durante ráfagas de mic
                    self._turn_done_event = asyncio.Event()
                    self._reconnect_event = asyncio.Event()

                    print("[JARVIS] ✅ Conectado.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS en línea.")
                    reconnect_delay   = 1.0   # reset backoff on successful connection
                    consecutive_fails = 0
                    self._api_1011_tool = None   # clear 1011 tool tracker

                    # Clear recent-turns buffer so conversational context is fresh
                    try:
                        clear_recent_turns()
                    except Exception:
                        pass

                    # ── First-connect extras ──────────────────────────────────
                    if self._first_connect:
                        self._first_connect = False
                        # Start Vision Guardian if enabled
                        try:
                            _start_vision_guardian(
                                inject_fn=self._inject_text,
                                speaking_fn=lambda: self._is_speaking,
                            )
                        except Exception as _vge:
                            print(f"[JARVIS] VisionGuardian init error: {_vge}")
                            
                        # Start Notification Watcher
                        try:
                            from core.notification_watcher import NotificationWatcher
                            def _on_notif(app_name, title, body):
                                self._inject_text(f"[SISTEMA] Acaba de llegar una notificación de {app_name}. Título: {title}. Ofrécele leérsela.")
                                # Update hologram via thread-safe signal
                                try:
                                    html_content = f"<div style='padding: 20px; font-family: Outfit, sans-serif;'><h2 style='color: #f59e0b; margin-top:0;'><i class='fas fa-bell'></i> {app_name}</h2><h3 style='color: white; margin-bottom: 5px;'>{title}</h3><p style='color: rgba(255,255,255,0.8); font-size: 16px; margin-top:0;'>{body}</p></div>"
                                    self.ui._win._holo_sig.emit("", html_content)
                                except Exception:
                                    pass

                            self._notif_watcher = NotificationWatcher(_on_notif)
                            tg.create_task(self._notif_watcher.start())
                        except Exception as ne:
                            print(f"[JARVIS] NotifWatcher error: {ne}")
                        # Auto morning brief (6am–12pm, once per day)
                        _hour = __import__("datetime").datetime.now().hour
                        if 6 <= _hour < 12 and not already_briefed_today():
                            async def _auto_brief():
                                await asyncio.sleep(1)  # let session settle
                                await self.session.send_client_content(
                                    turns={"parts": [{"text": "[AUTO] Dame el informe matutino del día."}]},
                                    turn_complete=True
                                )
                            tg.create_task(_auto_brief())

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watch_reconnect())

            except Exception as e:
                exceptions = e.exceptions if isinstance(e, ExceptionGroup) else [e]

                is_handshake_timeout = False
                is_config_reconnect  = False
                for exc in exceptions:
                    msg = str(exc)
                    if "Config changed" in msg:
                        # Intentional reconnect triggered by config change — fast, no backoff
                        is_config_reconnect = True
                        consecutive_fails = 0
                    elif "timed out during opening handshake" in msg or (
                        isinstance(exc, TimeoutError) and "handshake" in msg
                    ):
                        # Timeout de WebSocket al conectar — error de red transitorio.
                        # NO incrementar consecutive_fails: sólo reintento rápido.
                        is_handshake_timeout = True
                        print(f"[JARVIS] ⏱️ Timeout al conectar — reintentando en 1s...")
                    elif "1011" in msg or "Internal error" in msg:
                        tool_hint = self._api_1011_tool or ""
                        print(f"[JARVIS] ⚡ API 1011{tool_hint and ' durante '+tool_hint} — reconectando...")
                        consecutive_fails += 1
                        if consecutive_fails >= 4:
                            self.ui.write_log(
                                "SYS: ⚠️ Error 1011 repetido. Esperando para no saturar la API...\n"
                                "SYS: Si persiste más de 2 min, reiniciá JARVIS."
                            )
                        elif tool_hint:
                            self.ui.write_log(f"SYS: Error de servidor al ejecutar '{tool_hint}'. Reconectando...")
                        else:
                            self.ui.write_log("SYS: Error de servidor 1011. Reconectando...")
                    elif "1008" in msg or "policy violation" in msg.lower() or "not found for API version" in msg:
                        # Model not available / wrong API version — log clearly, retry with same model
                        print(f"[JARVIS] ⚠️ Modelo no disponible en esta versión de API: {msg[:120]}")
                        self.ui.write_log("SYS: ⚠️ Modelo no disponible. Reintentando...")
                        consecutive_fails += 1
                    elif "1000" in msg or "going away" in msg.lower():
                        # Cierre normal de la sesión (expiró ~15 min) — silencioso
                        print(f"[JARVIS] 🔄 Sesión expirada — reconectando...")
                        consecutive_fails = 0   # reset: no es un fallo
                    else:
                        print(f"[JARVIS] ⚠️ {exc}")
                        traceback.print_exc()
                        consecutive_fails += 1

                if is_config_reconnect:
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(0.5)
                    continue

                if is_handshake_timeout:
                    # Timeout en handshake → reintento fijo de 1s, sin backoff
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(1.0)
                    continue

            self.set_speaking(False)
            self.ui.set_state("THINKING")

            # Exponential backoff con jitter para evitar thundering herd
            # Reducido el retraso de reconexión máximo a 10s (antes 90s) para volver en línea al instante
            if consecutive_fails > 1:
                max_delay = 10.0 if consecutive_fails >= 5 else 6.0
                reconnect_delay = min(reconnect_delay * 2, max_delay)
            elif consecutive_fails == 0:
                reconnect_delay = 1.0

            import random as _rnd
            jitter = _rnd.uniform(0, reconnect_delay * 0.25)
            total  = reconnect_delay + jitter
            print(f"[JARVIS] 🔄 Reconectando en {total:.1f}s...")
            await asyncio.sleep(total)

def main():
    # ── Single Instance Lock ──────────────────────────────────────────────────
    import ctypes
    _single_instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JARVIS_AI_SINGLE_INSTANCE_MUTEX")
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        print("[JARVIS] Ya hay una instancia en ejecución. Cerrando.")
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "JARVIS-AI-HUD")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"[JARVIS] Error al restaurar la ventana activa: {e}")
        sys.exit(0)

    # ── Admin validation ──────────────────────────────────────────────────────
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False
    if not is_admin:
        print("[JARVIS] ⚠️ ADVERTENCIA: No se está ejecutando con privilegios de Administrador.")
        print("[JARVIS] ⚠️ Algunas funciones de control del PC o de terminal podrían fallar.")
        print("[JARVIS] ⚠️ Se recomienda iniciar JARVIS mediante 'Iniciar JARVIS Beta.vbs'.")

    # ── License check ─────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────

    # Load timezone from config
    _load_tz()

    def _ensure_both_api_keys():
        cfg = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        gemini = cfg.get("gemini_api_key", "").strip()
        openrouter = cfg.get("openrouter_api_key", "").strip()
        ai_provider = cfg.get("ai_provider", "gemini").strip()
        
        # If Ollama is the active provider, or if we have at least one cloud key set, we are safe to start
        if ai_provider == "ollama" or gemini or openrouter:
            return
            
        from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
        from PyQt6.QtCore import Qt
        
        # We need an app instance before dialogs
        app = QApplication.instance() or QApplication(sys.argv)
        
        dialog = QDialog()
        dialog.setWindowTitle("Configuración Inicial de JARVIS")
        dialog.resize(450, 250)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(dialog)
        
        lbl_info = QLabel("¡Bienvenido a JARVIS!\n\nPor favor, ingresa tus API keys o selecciona Ollama en la configuración.\nEstas se guardarán localmente y de forma segura.")
        lbl_info.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_info)
        
        lbl_gemini = QLabel("Gemini API Key:")
        layout.addWidget(lbl_gemini)
        inp_gemini = QLineEdit()
        inp_gemini.setText(gemini)
        inp_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(inp_gemini)
        
        lbl_openrouter = QLabel("OpenRouter API Key (Opcional):")
        layout.addWidget(lbl_openrouter)
        inp_openrouter = QLineEdit()
        inp_openrouter.setText(openrouter)
        inp_openrouter.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(inp_openrouter)
        
        btn_save = QPushButton("Guardar y Continuar")
        btn_save.setStyleSheet("background-color: #0078D7; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
        layout.addWidget(btn_save)
        
        def on_save():
            g = inp_gemini.text().strip()
            o = inp_openrouter.text().strip()
            if not g and not o:
                QMessageBox.warning(dialog, "Error", "Debe proporcionar al menos una API Key de Gemini.")
                return
            cfg["gemini_api_key"] = g
            cfg["openrouter_api_key"] = o
            API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            API_CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
            dialog.accept()
            
        btn_save.clicked.connect(on_save)
        
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            sys.exit(0)

    _ensure_both_api_keys()

    # Smart User Name Verification for First-Time Setup
    def _ensure_user_name():
        cfg = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        user_name = cfg.get("user_name", "").strip()
        if user_name:
            return
            
        from PyQt6.QtWidgets import QApplication, QInputDialog
        # We need app instance before dialogs
        app = QApplication.instance() or QApplication(sys.argv)
        
        name, ok = QInputDialog.getText(
            None, 
            "Configuración Inicial - JARVIS", 
            "¿Cómo desea que lo llame, señor?", 
            text="Señor"
        )
        if ok and name.strip():
            cfg["user_name"] = name.strip()
        else:
            cfg["user_name"] = "Señor"
            
        API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        API_CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

    _ensure_user_name()
    
    # Iniciar bot de Telegram en segundo plano
    try:
        from core.telegram_bot import start_telegram_listener
        start_telegram_listener()
    except Exception as e:
        print(f"[Telegram] Error al intentar arrancar el listener: {e}")

    ui = JarvisUI("face.png")

    # --- UI COSMETICS PATCH ---
    try:
        if hasattr(ui, "_win"):
            # Aumentar transparencia (Glassmorphism)
            ui._win.setWindowOpacity(0.85)
            # Reemplazar textos "Beta" y "Gratuito"
            from PyQt6.QtWidgets import QLabel
            for label in ui._win.findChildren(QLabel):
                text_lower = label.text().lower()
                if "beta" in text_lower or "gratuita" in text_lower or "gratuito" in text_lower or "premium" in text_lower:
                    try:
                        # Ocultar el contenedor completo del banner (incluye el botón PRO)
                        label.parentWidget().hide()
                    except:
                        label.hide()

            # 2. Add keyboard shortcut & Global Hotkey (INS / Insert key) to wake up JARVIS
            from PyQt6.QtGui import QKeySequence, QShortcut
            from PyQt6.QtCore import Qt, QTimer

            def on_shortcut_triggered():
                # Wake up / unmute JARVIS
                if hasattr(ui, "_win"):
                    # Si está muteado, desmutearlo para que escuche
                    if getattr(ui, "muted", False):
                        if hasattr(ui._win, "_toggle_mute"):
                            ui._win._toggle_mute()
                            ui.write_log("SYS: 🎤 Micrófono ACTIVADO vía atajo INS.")
                    else:
                        # Si ya está activo, mostrar/restaurar la ventana principal y enfocarla
                        if hasattr(ui._win, "showNormal"):
                            ui._win.showNormal()
                            ui._win.activateWindow()
                            ui.write_log("SYS: 🔔 JARVIS en foco vía atajo INS.")
                        
                        # Cambiar estado visual a escuchando
                        try:
                            ui.set_state("LISTENING")
                        except:
                            pass

            # A. PyQt Window Shortcut (for local window events)
            local_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Insert), ui._win)
            local_shortcut.activated.connect(on_shortcut_triggered)

            # B. Win32 Native Global Hotkey Hook (for background capture)
            def setup_global_hotkey():
                import threading
                import ctypes
                import ctypes.wintypes

                def hotkey_thread():
                    user32 = ctypes.windll.user32
                    # MOD_NOREPEAT = 0x4000
                    # VK_INSERT = 0x2D
                    try:
                        if not user32.RegisterHotKey(None, 99, 0x0000, 0x2D):
                            print("[HOTKEY] Error registering global Insert hotkey.")
                            return
                    except Exception as e:
                        print(f"[HOTKEY] Exception registering global hotkey: {e}")
                        return

                    try:
                        msg = ctypes.wintypes.MSG()
                        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                            if msg.message == 0x0312: # WM_HOTKEY
                                if msg.wParam == 99:
                                    # Thread-safely trigger UI callback inside PyQt event loop
                                    QTimer.singleShot(0, on_shortcut_triggered)
                            user32.TranslateMessage(ctypes.byref(msg))
                            user32.DispatchMessageW(ctypes.byref(msg))
                    finally:
                        user32.UnregisterHotKey(None, 99)

                threading.Thread(target=hotkey_thread, daemon=True).start()

            setup_global_hotkey()
            print("[PATCH] Avengers: Age of Ultron golden aesthetics & Insert global hotkey loaded successfully!")

    except Exception as e:
        print(f"[PATCH] Cosmetics & Shortcut patch failed: {e}")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Apagando...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

    # Terminación forzada a nivel de sistema operativo para liberar handles de cámara,
    # micrófono, sockets y el mutex de instancia única al instante sin esperas ni deadlocks
    import os
    os._exit(0)

if __name__ == "__main__":
    main()