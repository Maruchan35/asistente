# -*- coding: utf-8 -*-
"""
core/tool_registry.py — Declaraciones de herramientas para Gemini Live.

Extraido de main.py para mantener el archivo principal manejable.
Cada entrada describe una funcion que Gemini puede invocar; el dispatcher
vive en main.py (_execute_tool) con fallback dinamico a actions/<name>.py.

REGLA: al agregar una tool aqui, ejecuta tests/test_tool_consistency.py
para verificar que el dispatcher la cubre.
"""

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
        "name": "screen_reader",
        "description": (
            "Lector de pantalla de accesibilidad: captura una región o la pantalla completa, "
            "y puede narrar el contenido, extraer texto (OCR), localizar elementos de UI "
            "o describir el layout. Usar cuando el usuario pida 'léeme la pantalla', "
            "'extrae el texto de esta ventana', 'qué botones hay'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "narrate | extract_text | locate | describe_layout"
                },
                "query": {
                    "type": "STRING",
                    "description": "Para locate: qué elemento buscar"
                }
            }
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
        "description": (
            "Clima actual y pronostico de una ciudad: temperatura, humedad, viento, lluvia. "
            "Usar cuando pregunten por clima, temperatura, si llovera, o que ropa llevar."
        ),
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
            "Para enviar un documento usar action='send_document' con file_path=ruta del archivo. "
            "LEER CHATS: action='read' SIN receiver lista que chats tienen mensajes sin leer; "
            "action='read' CON receiver ENTRA a ese chat y devuelve la transcripcion REAL de los "
            "ultimos mensajes (no respondas a un mensaje sin leerlo primero asi)."
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
        "description": (
            "Crea recordatorios y alarmas con fecha/hora exacta usando el Task Scheduler de Windows. "
            "Usar para: 'recuerdame X a las Y', 'ponme una alarma', 'avisame en 20 minutos'. "
            "NO usar para tareas recurrentes (eso es scheduler)."
        ),
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
        "description": (
            "Escribe, edita, explica, ejecuta o construye archivos de codigo en el PC del usuario. "
            "Usar para: 'crea un script de Python que X', 'corrige este archivo', 'ejecuta mi script'. "
            "Para razonamiento de codigo complejo SIN tocar archivos, usar deepseek_agent."
        ),
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
        "description": (
            "Busca vuelos reales en Google Flights entre dos ciudades en una fecha y devuelve "
            "las mejores opciones con precio y horario. Usar cuando pidan vuelos, boletos de avion "
            "o precios para viajar."
        ),
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
        "name": "self_update",
        "description": (
            "Actualiza JARVIS desde GitHub. action='check' para ver si hay versión nueva, "
            "action='update' para aplicar la actualización (git pull + dependencias), "
            "action='restart' para reiniciar JARVIS y aplicar cambios. "
            "Usar cuando el usuario diga 'actualízate', '¿hay actualizaciones?', "
            "'ponte al día', 'reinicia jarvis'. "
            "FLUJO: check primero → confirmar con el usuario → update → ofrecer restart."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'check' | 'update' | 'restart'",
                    "enum": ["check", "update", "restart"]
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "doc_search",
        "description": (
            "Busca DENTRO del contenido de los documentos del usuario (Word, PDF, TXT, "
            "PowerPoint) en Desktop, Documents y Downloads. "
            "Usar cuando el usuario pregunte sobre el CONTENIDO de sus archivos: "
            "'¿qué decía mi documento de X?', 'busca en mis apuntes Y', "
            "'¿en qué archivo hablo de Z?', '¿qué documentos tengo sobre W?'. "
            "NO usar para buscar archivos POR NOMBRE (eso es file_controller) "
            "ni para buscar en internet (eso es web_search). "
            "action='search' busca; action='reindex' reconstruye el índice (lento, "
            "solo si el usuario dice que faltan documentos recientes)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Qué buscar dentro de los documentos"
                },
                "action": {
                    "type": "STRING",
                    "description": "'search' (default) | 'reindex' | 'stats'",
                    "enum": ["search", "reindex", "stats"]
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Máximo de documentos a devolver (default 5)"
                }
            }
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
            "Reports or CANCELS background tasks JARVIS is running. "
            "Call with action='summary' when the user asks '¿en qué vas?', '¿cómo va la tarea?'. "
            "Call with action='cancel' when the user says 'cancela la investigación', "
            "'detén la tarea', 'para eso', 'ya no lo quiero'. "
            "Returns a human-readable summary."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'list' = ver tareas, 'summary' = resumen breve, 'cancel' = cancelar tarea en curso",
                    "enum": ["list", "summary", "cancel"]
                },
                "title": {
                    "type": "STRING",
                    "description": "Para cancel: parte del título de la tarea a cancelar. Si se omite, cancela la más reciente en curso."
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
                "goal":        {"type": "STRING",  "description": "Texto del objetivo (al crear)"},
                "title":       {"type": "STRING",  "description": "Título del objetivo"},
                "description": {"type": "STRING",  "description": "Descripción detallada"},
                "deadline":    {"type": "STRING",  "description": "Fecha límite ISO (YYYY-MM-DD)"},
                "recurrence":  {"type": "STRING",  "description": "'daily' o 'weekly' para recordatorio proactivo. Usar cuando el usuario diga 'cada día', 'todos los días', 'cada semana'."},
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
                },
                "confirmed": {
                    "type": "BOOLEAN",
                    "description": (
                        "SOLO pasar true cuando el usuario YA confirmó verbalmente un comando "
                        "que el sandbox bloqueó por riesgo HIGH/CRITICAL. Nunca pasar true "
                        "en la primera llamada."
                    )
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
    {
        "name": "autonomy_control",
        "description": (
            "Controla el nivel de autonomia de JARVIS y su registro de actividad. "
            "action='set_level' con level 1 (manual: pregunta todo), 2 (asistido: ejecuta "
            "lo seguro solo) o 3 (autonomo: ejecuta todo salvo lo critico). "
            "action='kill' cuando el usuario diga 'detente', 'para todo', 'modo manual ya'. "
            "action='resume' para reanudar. action='report' cuando pregunte "
            "'que hiciste mientras no estaba' o 'que has hecho solo'. action='status' para consultar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["set_level", "status", "kill", "resume", "report"],
                           "description": "set_level | status | kill | resume | report"},
                "level": {"type": "INTEGER", "description": "Para set_level: 1, 2 o 3"},
                "hours": {"type": "INTEGER", "description": "Para report: ventana en horas (default 24)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "verify_outcome",
        "description": (
            "Verifica que una accion realmente ocurrio ANTES de reportar exito al usuario. "
            "Usar despues de crear archivos, abrir apps o completar tareas importantes. "
            "Si la verificacion FALLA, reintenta la accion por un camino alternativo "
            "(maximo 2 reintentos) antes de reportar el fallo. "
            "checks: file_exists, file_recent (max_age_s), file_size_min (min_kb), "
            "process_running, window_open, url_reachable, screen_contains."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "check": {"type": "STRING",
                          "enum": ["file_exists", "file_recent", "file_size_min",
                                   "process_running", "window_open", "url_reachable", "screen_contains"],
                          "description": "Tipo de verificacion"},
                "target": {"type": "STRING", "description": "Ruta, nombre de proceso/ventana, URL o texto a verificar"},
                "max_age_s": {"type": "INTEGER", "description": "Para file_recent: antiguedad maxima en segundos"},
                "min_kb": {"type": "INTEGER", "description": "Para file_size_min: tamano minimo en KB"}
            },
            "required": ["check", "target"]
        }
    },
    {
        "name": "self_heal",
        "description": (
            "Sistema de auto-reparacion de JARVIS. action='scan' lista fallas repetidas "
            "de las ultimas 24h. action='diagnose' analiza una falla con IA y propone parche. "
            "action='fix' aplica el parche CON backup + tests + rollback automatico si fallan. "
            "Usar cuando el usuario diga 'reparate', 'arregla tus errores', 'que fallas tienes', "
            "o cuando una herramienta falle repetidamente en la conversacion. "
            "FLUJO: scan -> diagnose -> confirmar con el usuario -> fix con confirmed=true."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["scan", "diagnose", "fix"],
                           "description": "scan | diagnose | fix"},
                "pattern_index": {"type": "INTEGER", "description": "Numero de falla del scan (1 = mas frecuente)"},
                "confirmed": {"type": "BOOLEAN", "description": "true solo si el usuario confirmo aplicar el fix"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_repair",
        "description": (
            "Playbook de reparaciones del sistema operativo. Usar cuando algo del PC falle: "
            "internet caido -> network_report y luego wifi_reconnect o flush_dns; "
            "app congelada (Spotify, Chrome...) -> restart_app con target; "
            "sin sonido -> restart_audio; disco lleno -> disk_report. "
            "Los reports (disk_report, network_report) son seguros y puedes ejecutarlos "
            "libremente para diagnosticar. Las reparaciones respetan el nivel de autonomia: "
            "si devuelve que requiere confirmacion, pregunta al usuario y re-llama con confirmed=true."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "repair": {"type": "STRING",
                           "enum": ["wifi_reconnect", "restart_app", "flush_dns",
                                    "restart_audio", "disk_report", "network_report"],
                           "description": "Reparacion a ejecutar"},
                "target": {"type": "STRING", "description": "Para restart_app: nombre de la app (ej: spotify)"},
                "confirmed": {"type": "BOOLEAN", "description": "true si el usuario ya confirmo una reparacion riesgosa"}
            },
            "required": ["repair"]
        }
    },
    {
        "name": "whatsapp_watch",
        "description": (
            "Vigila WhatsApp para DETECTAR MENSAJES ENTRANTES automaticamente — el usuario "
            "ya no tiene que avisar que llego un mensaje. "
            "action='start' mode='notify' → avisa al usuario cuando llegue algo. "
            "action='start' mode='converse' contact='Nombre' → MODO CONVERSACION CONTINUA: "
            "JARVIS detecta cada mensaje nuevo, lo lee (whatsapp action=read) y responde solo "
            "(whatsapp action=send), manteniendo la conversacion sin intervencion del usuario. "
            "Usar cuando digan: 'sigue la conversacion con X', 'avisame si me escriben', "
            "'responde por mi a X', 'vigila mi whatsapp', 'contesta mis mensajes'. "
            "action='stop' para detener; action='status' para consultar. "
            "REQUIERE que WhatsApp Web o Desktop este abierto en una ventana."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["start", "stop", "status"],
                           "description": "start | stop | status"},
                "contact": {"type": "STRING",
                            "description": "Contacto objetivo para modo converse (vacio = cualquiera)"},
                "mode": {"type": "STRING", "enum": ["notify", "converse"],
                         "description": "notify = solo avisar al usuario | converse = leer y responder solo"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "skill_factory",
        "description": (
            "Crea HERRAMIENTAS NUEVAS para JARVIS por voz — JARVIS se extiende a si mismo. "
            "action='design' description='lo que debe hacer' → disena la habilidad y la muestra. "
            "action='install' → la instala con backup + tests + rollback automatico (requiere "
            "confirmacion del usuario o nivel autonomia 3). action='list' → habilidades creadas. "
            "Usar cuando el usuario diga: 'necesito que puedas X', 'create una herramienta para Y', "
            "'aprende a hacer Z', 'agregate la capacidad de'. Tras instalar, ofrece reiniciar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["design", "install", "list"]},
                "description": {"type": "STRING", "description": "Que debe hacer la herramienta nueva"},
                "name": {"type": "STRING", "description": "Nombre sugerido (snake_case, opcional)"},
                "confirmed": {"type": "BOOLEAN", "description": "true si el usuario confirmo instalar"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "wa_memory",
        "description": (
            "Consulta el historial de conversaciones de WhatsApp que JARVIS mantuvo "
            "(leidas y respondidas autonomamente). Usar cuando pregunten 'que le dijiste a X', "
            "'resume mi conversacion con Y', 'que hablaste con Z'. "
            "action='get' chat='nombre' o action='list' para ver todos los contactos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["get", "list"]},
                "chat": {"type": "STRING", "description": "Nombre del contacto"},
                "limit": {"type": "INTEGER", "description": "Cuantos mensajes (default 20)"}
            }
        }
    },
    {
        "name": "screen_awareness",
        "description": (
            "Modo atento: JARVIS observa tu pantalla periodicamente y te ofrece ayuda si "
            "detecta errores (stacktraces, dialogos de error). Usa OCR local (no gasta cuota). "
            "Usar cuando digan 'modo atento', 'vigila mi pantalla', 'avisame si ves un error'. "
            "action='start' | 'stop' | 'status'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["start", "stop", "status"]},
                "interval_s": {"type": "INTEGER", "description": "Cada cuantos segundos (default 45)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "secure_config_tool",
        "description": (
            "Gestiona el cifrado de las API keys. action='status' muestra cuantas estan "
            "cifradas. action='encrypt' cifra las que esten en texto plano. "
            "Usar cuando pregunten por la seguridad de las claves o pidan cifrarlas."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["status", "encrypt"]}
            },
            "required": ["action"]
        }
    },
    {
        "name": "offline_status",
        "description": (
            "Consulta el estado de conectividad y capacidades offline de JARVIS "
            "(internet, Ollama local). Usar cuando pregunten 'hay internet', "
            "'estas en linea', 'funcionas sin internet'."
        ),
        "parameters": {"type": "OBJECT", "properties": {}}
    },
]
