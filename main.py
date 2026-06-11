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
    from actions.self_update       import self_update
except ImportError:
    self_update = None
try:
    from actions.doc_search        import doc_search
except ImportError:
    doc_search = None
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
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            _cached_api_key = json.load(f).get("gemini_api_key", "").strip()
    except FileNotFoundError:
        _cached_api_key = ""

    # Validar que no sea el placeholder del template
    _placeholders = (
        "", "YOUR_GEMINI_API_KEY_HERE", "PEGAR_AQUI_TU_API_KEY_DE_GEMINI",
        "YOUR_API_KEY_HERE", "PUT_YOUR_KEY_HERE",
    )
    if _cached_api_key in _placeholders or _cached_api_key.upper().startswith("YOUR_"):
        msg = (
            "\n" + "="*70 + "\n"
            " [ERROR] Falta tu API key de Gemini.\n"
            "="*70 + "\n\n"
            " JARVIS necesita una API key de Google Gemini para funcionar.\n\n"
            " 1. Abre:  https://aistudio.google.com/app/apikey\n"
            " 2. Haz clic en 'Create API key' (es gratis)\n"
            " 3. Copia la key (empieza con 'AQ.Ab8RN6...' o similar)\n"
            " 4. Abre con Notepad el archivo:\n"
            f"        {API_CONFIG_PATH}\n"
            " 5. Reemplaza el valor de 'gemini_api_key' por la que copiaste\n"
            " 6. Guarda el archivo y reinicia JARVIS\n\n"
            + "="*70 + "\n"
        )
        print(msg)
        # Intentar mostrar también en una ventana si Qt ya está cargado
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app is not None:
                QMessageBox.critical(None, "JARVIS — Falta API Key",
                    "Falta tu API key de Gemini.\n\n"
                    "Obténla gratis en:\nhttps://aistudio.google.com/app/apikey\n\n"
                    f"Luego edita:\n{API_CONFIG_PATH}\n"
                    "y reemplaza 'YOUR_GEMINI_API_KEY_HERE' por tu clave."
                )
        except Exception:
            pass
        raise RuntimeError("API key de Gemini no configurada (es placeholder o está vacía)")
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

# TOOL_DECLARATIONS extraido a core/tool_registry.py (ver ese archivo)
from core.tool_registry import TOOL_DECLARATIONS

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

        # Vosk se carga en BACKGROUND — tarda 1-3s y bloqueaba el arranque.
        # Solo se usa en Modo Suspensión; self.vosk_recognizer queda None
        # hasta que termine (los callbacks ya hacen getattr(..., None)).
        self.vosk_recognizer = None
        def _load_vosk_bg():
            try:
                import vosk
                if os.path.exists("config/vosk_model"):
                    model = vosk.Model("config/vosk_model")
                    self.vosk_recognizer = vosk.KaldiRecognizer(model, 16000)
                    print("[JARVIS] Modelo Vosk cargado para Modo Suspensión.")
            except Exception as e:
                print(f"[JARVIS] No se pudo cargar Vosk: {e}")
        threading.Thread(target=_load_vosk_bg, daemon=True,
                         name="VoskLoader").start()
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
                    _res_preview = str(task.result)[:250] if task.result else ""
                    self._inject_text(
                        f"(Tarea en segundo plano completada: '{task.title}'. "
                        f"Resultado real: {_res_preview} — AHORA SÍ está terminada: "
                        "avisa al usuario en una frase, mencionando el archivo si aplica.)"
                    )
                elif task.status == "failed":
                    self._inject_text(
                        f"(Tarea '{task.title}' falló: {task.error}. Reporte al usuario.)"
                    )
                elif task.status == "cancelled":
                    self._inject_text(
                        f"(Tarea '{task.title}' fue cancelada. Confirma al usuario brevemente.)"
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

        # ── Daemon de autonomía: trabaja cuando el usuario está ausente ──────
        try:
            from core.autonomy_daemon import start as _daemon_start
            def _on_idle_work_summary(summary: str):
                try:
                    self._inject_text(
                        f"(El usuario acaba de volver. Mientras no estaba hiciste: {summary}. "
                        "Ménciónaselo en UNA frase casual, sin lista.)"
                    )
                except Exception:
                    pass
            _daemon_start(on_summary=_on_idle_work_summary)
            _jlog_info("Daemon de autonomía iniciado", category="system")
        except Exception as e:
            _jlog_error("No se pudo iniciar daemon de autonomía", exc=e)

        # ── Reportar crashes del watchdog (si los hubo) ──────────────────────
        try:
            _crash_log = Path("logs/crashes.jsonl")
            if _crash_log.exists():
                import time as _t
                _lines = _crash_log.read_text(encoding="utf-8").strip().split("\n")
                if _lines and _lines[-1]:
                    _last = json.loads(_lines[-1])
                    from datetime import datetime as _dt
                    _age = _t.time() - _dt.fromisoformat(_last["ts"]).timestamp()
                    if _age < 300:   # crasheó hace < 5 min — este arranque es del watchdog
                        def _report_crash():
                            _t.sleep(10)
                            self._inject_context(
                                f"(JARVIS crasheó hace un momento (exit={_last['exit_code']}) "
                                "y el watchdog lo relanzó. Si el usuario habla, menciona "
                                "brevemente que hubo un reinicio automático.)"
                            )
                        threading.Thread(target=_report_crash, daemon=True).start()
        except Exception:
            pass

        # ── Health check al arrancar (background, no bloquea) ────────────────
        def _health_bg():
            try:
                from core.health_check import print_health_report
                report = print_health_report()
                if not report["ok"]:
                    # Avisar por voz en cuanto haya sesión
                    import time as _t
                    _t.sleep(8)   # esperar a que conecte
                    self._inject_context(
                        f"(Health check del arranque encontró problemas: {report['summary']}. "
                        "Méncionalo brevemente si el usuario pregunta por el estado del sistema.)"
                    )
            except Exception:
                pass
        threading.Thread(target=_health_bg, daemon=True, name="HealthCheck").start()

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

    def _inject_context(self, text: str):
        """Inyectar contexto SILENCIOSO (no provoca respuesta del modelo).
        Usado para hints de emoción, reglas aprendidas, estado de focus —
        el modelo lo verá en su próximo turno sin hablar ahora."""
        if self._loop and self.session:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.session.send_client_content(
                        turns={"parts": [{"text": text}]},
                        turn_complete=False
                    ),
                    self._loop
                )
            except Exception:
                pass

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
            _changed = (self._is_speaking != value)
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")
        # Audio ducking: bajar música mientras JARVIS habla, restaurar al callar.
        # En hilo aparte — el mixer de Windows (COM) puede tardar ~50ms.
        if _changed:
            try:
                from core.audio_ducking import duck, unduck, is_enabled
                if is_enabled():
                    threading.Thread(
                        target=(duck if value else unduck), daemon=True
                    ).start()
            except Exception:
                pass

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

        # Event loop al INICIO — las ramas tempranas (self_update, doc_search...)
        # lo usan antes de la asignación que vive más abajo en la función.
        loop = asyncio.get_running_loop()

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

        if name == "self_update":
            if self_update:
                self.ui.write_log("🔄 Verificando actualizaciones...")
                r = await loop.run_in_executor(
                    _TOOL_EXECUTOR, lambda: self_update(parameters=args, player=self.ui)
                )
                result = r or "Sin respuesta del actualizador."
            else:
                result = "Módulo self_update no disponible."
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "doc_search":
            if doc_search:
                self.ui.write_log("📚 Buscando en tus documentos...")
                r = await loop.run_in_executor(
                    _TOOL_EXECUTOR, lambda: doc_search(parameters=args, player=self.ui)
                )
                result = r or "Sin resultados."
            else:
                result = "Módulo doc_search no disponible."
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
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
                             + (f" — {t.progress}" if t.progress else "")
                             for t in tasks]
                    result = "Estado de tareas:\n" + "\n".join(lines)
            elif action == "cancel":
                try:
                    from core.task_queue import cancel as _task_cancel
                    target_title = (args.get("title") or "").lower().strip()
                    running = _task_list(status="running", limit=10)
                    victim = None
                    if target_title:
                        for t in running:
                            if target_title in t.title.lower():
                                victim = t; break
                    elif running:
                        victim = running[0]   # la más reciente en curso
                    if victim is None:
                        result = "No encontré ninguna tarea en curso para cancelar, señor."
                    elif _task_cancel(victim.id):
                        result = (f"Cancelando '{victim.title}'. La tarea se detendrá "
                                  "al terminar el paso actual.")
                    else:
                        result = f"No se pudo cancelar '{victim.title}' (estado: {victim.status})."
                except Exception as e:
                    result = f"Error al cancelar: {e}"
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

            elif name == "window_control":
                # No existe actions/window_control.py — es una acción de computer_control
                _wc_args = {"action": "window_control", **args}
                r = await loop.run_in_executor(_TOOL_EXECUTOR, lambda: computer_control(parameters=_wc_args, player=self.ui))
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
                    # ── SANDBOX: clasificar riesgo ANTES de ejecutar ──────────
                    _cmd = args.get("command", "")
                    _confirmed = args.get("confirmed", False)
                    if isinstance(_confirmed, str):
                        _confirmed = _confirmed.lower() in ("true", "1", "yes", "sí", "si")
                    _report = _sandbox_cmd(_cmd)
                    # Nivel de autonomía: en nivel 3, HIGH se auto-permite
                    # (CRITICAL siempre requiere confirmación, sin excepciones)
                    _auto_ok = False
                    try:
                        from core.autonomy import is_allowed as _aut_allowed, audit as _aut_audit
                        if _report is not None and _report.risk == "HIGH" and _aut_allowed("HIGH"):
                            _auto_ok = True
                            _aut_audit("terminal_auto", f"HIGH auto-aprobado (nivel 3): {_cmd[:100]}", "")
                    except Exception:
                        pass
                    if (_report is not None and _report.needs_confirmation()
                            and not _confirmed and not _auto_ok):
                        _jlog_warn(f"Sandbox bloqueó comando {_report.risk}: {_cmd[:120]}",
                                   category="tool")
                        self.ui.write_log(f"🛡️ Sandbox: comando {_report.risk} requiere confirmación")
                        result = (
                            f"COMANDO BLOQUEADO POR SEGURIDAD (riesgo {_report.risk}: {_report.reason}).\n"
                            f"Comando exacto: {_cmd}\n"
                            "INSTRUCCIÓN: Lee al usuario EXACTAMENTE qué se va a ejecutar y qué hace. "
                            "Si el usuario confirma verbalmente ('sí, confirmo', 'adelante', 'hazlo'), "
                            "vuelve a llamar terminal_agent con el MISMO comando y confirmed=true. "
                            "Si duda o se niega, NO lo ejecutes."
                        )
                    else:
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

                        # ── BARGE-IN: el usuario interrumpió a JARVIS ─────────
                        # Gemini manda interrupted=True cuando detecta voz del
                        # usuario encima de la de JARVIS. Vaciar TODO el audio
                        # encolado para que se calle al instante, no tras
                        # terminar de reproducir lo bufferizado.
                        if getattr(sc, "interrupted", False):
                            _drained = 0
                            try:
                                while not self.audio_in_queue.empty():
                                    self.audio_in_queue.get_nowait()
                                    _drained += 1
                            except Exception:
                                pass
                            self.set_speaking(False)
                            if _drained:
                                print(f"[JARVIS] ✋ Interrumpido — {_drained} chunks descartados")
                                _jlog_audio("barge_in", drained_chunks=_drained)

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
                                # Detección de correcciones del usuario — si aprende
                                # una regla, inyectarla EN VIVO como contexto silencioso
                                try:
                                    from core.correction_learner import maybe_save_correction, detect_correction
                                    def _learn_and_notify(uin=full_in, uout=full_out):
                                        if maybe_save_correction(uin, uout):
                                            found = detect_correction(uin)
                                            if found:
                                                self._inject_context(
                                                    f"(REGLA APRENDIDA del usuario, aplícala desde ahora: "
                                                    f"{found[1]})"
                                                )
                                    _th.Thread(target=_learn_and_notify, daemon=True).start()
                                except Exception:
                                    pass
                                # Detección de estado emocional — inyectar hint EN VIVO
                                # solo cuando el estado CAMBIA (no repetir cada turno)
                                try:
                                    from core.emotion_detector import update_from_user_text
                                    _estate = update_from_user_text(full_in)
                                    _prev_label = getattr(self, "_last_emotion_label", "neutral")
                                    if (_estate.label != _prev_label
                                            and _estate.label != "neutral"
                                            and _estate.intensity >= 0.4):
                                        hint = _estate.to_prompt_hint()
                                        if hint:
                                            self._inject_context(f"({hint})")
                                    self._last_emotion_label = _estate.label
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

        def _open_stream():
            s = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=PLAY_CHUNK_SIZE,
            )
            s.start()
            return s

        stream = None
        try:
            stream = _open_stream()
        except Exception as e:
            print(f"[JARVIS] ⚠️ Salida de audio no disponible al iniciar: {e}")
            _jlog_error("Audio out no abrió al iniciar", exc=e, category="audio")

        _write_fails = 0

        async def _write(data: bytes) -> None:
            """Escribir al stream con auto-recuperación.
            Un fallo del driver (PaErrorCode -9999, device removed, etc.)
            NO debe tirar la sesión completa — reabrimos el stream o, si
            es imposible, seguimos drenando la cola sin reproducir."""
            nonlocal stream, _write_fails
            if stream is None:
                try:
                    stream = await asyncio.to_thread(_open_stream)
                    print("[JARVIS] 🔊 Salida de audio recuperada")
                    _write_fails = 0
                except Exception:
                    return   # sin audio por ahora — no bloquear
            try:
                await asyncio.to_thread(stream.write, data)
                _write_fails = 0
            except Exception as we:
                _write_fails += 1
                print(f"[JARVIS] ⚠️ Audio out error ({_write_fails}): {we}")
                _jlog_error("Audio out write falló", exc=we, category="audio")
                try:
                    stream.close()
                except Exception:
                    pass
                stream = None
                if _write_fails == 5:
                    print("[JARVIS] ❌ Altavoz no disponible — continúo SIN voz "
                          "(las transcripciones siguen en pantalla; revisa el driver)")

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
                            await _write(buffered)
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
                        await _write(buffered)
                    _jitter_buf.clear()
        finally:
            self.set_speaking(False)
            if stream is not None:
                try:
                    stream.stop(); stream.close()
                except Exception:
                    pass

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