# JARVIS AI — Asistente virtual holográfico para Windows

Un asistente de voz inspirado en el JARVIS de Iron Man, construido sobre Gemini Live API con integración profunda con Windows, automatización cognitiva, generación de documentos profesionales, visión de pantalla, y una interfaz PyQt6 estilo holograma dorado.

## ✨ Características principales

### 🎤 Voz e interacción
- **Gemini Live** real-time voice con VAD nativa y transcripción bidireccional
- **Wake word personalizable** (offline con Vosk) — di "JARVIS" o tu propia palabra
- **Hotkey global `Ctrl+Alt+J`** para activar sin esperar wake word
- **Detección emocional**: adapta el tono según si estás frustrado, cansado, contento, apurado

### 🧠 Memoria persistente real
- Long-term: hechos auto-extraídos de la conversación (nombre, ciudad, preferencias)
- Session journal por día (JSONL)
- **Recovery de contexto** al reconectar Gemini (mantiene los últimos 6 turnos en RAM)
- **Aprendizaje de correcciones**: "no, así no" → se guarda como regla permanente

### 📄 Generación de documentos
- **`document_creator`** — Word profesional con portada azul, TOC funcional, callouts, tablas, encabezados, normas APA/Professional/Academic
- **`deep_research`** — investigaciones de hasta 60 páginas generadas POR SECCIONES (cada una con su propia llamada al LLM, sin límite de 1500 tokens), con streaming al .docx en vivo

### 🛠️ Herramientas (más de 60)
- Control del sistema (volumen, brillo, wifi, apagar)
- Apps (Spotify, Netflix, YouTube, Steam)
- Comunicaciones (WhatsApp, Gmail, Telegram, Discord)
- Archivos (crear, mover, analizar, organizar)
- Visión de pantalla con LLM multimodal
- Búsqueda web con **citas verificables** (URLs reales)
- Calendario, recordatorios, scheduler
- Terminal (PowerShell/CMD) con sandbox de seguridad

### 🎯 Modos especiales
- **Pair programming** — JARVIS observa tu IDE y reporta bugs en el activity panel sin interrumpir
- **Focus mode** — silencia notificaciones y proactividad por X minutos
- **Proactividad** — detecta patrones (lunes 9am → calendario) y sugiere acciones
- **Dashboard de uso** — top herramientas, latencias, errores, memoria, quota

### 🎨 UI
- Holograma dorado dinámico (Glassmorphism, QWebEngineView)
- **Activity panel** flotante con herramienta actual + tareas en curso + plan multi-paso
- **Hologramas contextuales**: gráficos, tablas, mapas, vista previa de documentos generados

### 🔒 Seguridad
- Sandbox de comandos clasificados SAFE/MEDIUM/HIGH/CRITICAL
- Archivos intocables (`terminal_agent`, `self_edit`)
- Confirmación obligatoria para operaciones destructivas
- Quota manager con fallback automático: Gemini → DeepSeek → OpenRouter → Ollama

### 📊 Observabilidad
- Logs JSONL estructurados por categoría: `system / tool / audio / error / quota / session`
- Rotación automática a 5MB
- Smoke tests (16) + E2E tests (12) — `python tests/smoke_tools.py`

## 🛠️ Stack técnico

- **Python 3.12**
- **PyQt6** + WebEngine para la UI holográfica
- **Google Gemini Live API** (voz)
- **OpenRouter / DeepSeek / Ollama** (texto)
- **python-docx** para Word
- **sounddevice + vosk** para audio
- **keyboard** para hotkey global

## 🚀 Instalación rápida (5 minutos)

### Requisitos previos

1. **Python 3.12** — <https://www.python.org/downloads/> · ⚠️ Marca "Add Python to PATH" al instalar
2. **Git** — <https://git-scm.com/download/win>
3. **API key de Gemini (gratis)** — <https://aistudio.google.com/app/apikey>
   - Inicia sesión con tu cuenta de Google
   - Haz clic en **"Create API key"**
   - Copia la clave (empieza con `AQ.Ab8...` o similar) — la vas a necesitar en el paso 4

### Pasos

```cmd
1) Clonar el repo
   git clone https://github.com/Maruchan35/asistente.git
   cd asistente

2) Doble click en  Instalar_JARVIS.bat
   (te pide permisos de admin; instala ~3 GB de dependencias en 5-10 min)

3) El instalador crea automáticamente  config\api_keys.json  vacío
   a partir del template api_keys.example.json

4) Abre  config\api_keys.json  con Notepad y reemplaza:

       "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE"

   por tu clave real (la que copiaste del paso 3 de requisitos):

       "gemini_api_key": "AQ.Ab8RN6IwXXXXXXXXXXXXXXX"

5) Guarda el archivo  y haz doble click en  JARVIS_Iniciar.bat
```

### ⚠️ Errores comunes

| Síntoma | Solución |
|---|---|
| "API key de Gemini no configurada" | Editaste mal `config/api_keys.json`, sigue el paso 4 |
| "Python not found" | Olvidaste marcar "Add Python to PATH" — reinstala Python |
| Pip falla con algún paquete | Corre `REINSTALAR_JARVIS.bat` — reinstala uno por uno con fallback |
| Sin sonido | Verifica el dispositivo en `config/api_keys.json` → `mic_device` y `speaker_device` |

## ✅ Qué funciona solo con la API key de Gemini

El instalador descarga automáticamente: dependencias Python, Chromium para Playwright, y modelo Vosk para wake word offline. Con **solo** la `gemini_api_key`, esto funciona **out-of-the-box**:

- 🎤 **Voz** (Gemini Live + transcripción)
- 👁️ **Visión de pantalla** (`screen_vision`)
- 📄 **Documentos Word/Excel/PDF** (`document_creator`)
- 🧠 **Memoria persistente**, correcciones, emociones
- 🌐 **Búsqueda web** (DuckDuckGo, sin API key)
- ☀️ **Clima** (Open-Meteo, sin API key)
- 🖥️ **Control de sistema** (volumen, brillo, wifi, apps)
- 📂 **Gestión de archivos** (mover, organizar, analizar)
- 🎯 **Activity panel, focus mode, pair programming, dashboard**
- ⌨️ **Hotkey global** `Ctrl+Alt+J`
- 🗣️ **Wake word** "JARVIS" (modo offline con Vosk)
- 🌐 **Navegador automatizado** (Playwright + Chromium)
- 🧪 **Tests** (`python tests/smoke_tools.py`)

## 🔧 Qué requiere configuración EXTRA (opcional)

Estas funciones son **opcionales** — JARVIS arranca sin ellas, simplemente esas herramientas devuelven un error específico si las invocas.

### 📚 `deep_research` (investigaciones largas)
Recomendado pero opcional:
- **OpenRouter** (créditos gratis al registrarse): <https://openrouter.ai/keys> → pegá la key en `openrouter_api_key`
- Fallback automático: **DeepSeek** <https://platform.deepseek.com/api_keys> → `deepseek_api_key`

### 📧 Gmail / Google Calendar / Google Drive
1. Crea proyecto en <https://console.cloud.google.com/>
2. Habilita Gmail API + Calendar API + Drive API
3. Crea credenciales OAuth 2.0 → descarga JSON
4. Guárdalo como `config/google_credentials.json`
5. Primera vez que uses la herramienta, abrirá tu navegador para autorizar

### 🎵 Spotify
1. Crea app en <https://developer.spotify.com/dashboard>
2. Redirect URI: `http://127.0.0.1:8765/callback`
3. Copia `Client ID` y `Client Secret` en `api_keys.json`:
   ```json
   "spotify_client_id": "tu_id_aqui",
   "spotify_client_secret": "tu_secret_aqui",
   "spotify_redirect_uri": "http://127.0.0.1:8765/callback"
   ```

### 💬 WhatsApp
Funciona sobre WhatsApp Web — la primera vez te pedirá calibrar coordenadas con `python scratch/calibrate_wa.py` (incluido).

### 📞 Telegram
Crea bot con [@BotFather](https://t.me/BotFather) en Telegram → copia el token a `telegram_bot_token`.

### 🏠 Smart Home (Home Assistant)
Requiere Home Assistant corriendo en tu red local. Configura `homeassistant_url` y `homeassistant_token`.

### 🎮 Steam / Epic / juegos
Funciona sin config si tienes los launchers instalados en rutas estándar.

### Opción 2 — Manual

```bash
git clone https://github.com/TU_USUARIO/JARVIS-AI.git
cd JARVIS-AI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config\api_keys.template.json config\api_keys.json
# edita config/api_keys.json con tu API key de Gemini
python main.py
```

## 🔑 API keys necesarias

| Servicio | Obligatorio | Para qué |
|---|---|---|
| **Gemini** | ✅ Sí | Voz principal (Live API) |
| OpenRouter | Recomendado | `deep_research`, `openrouter_agent` |
| DeepSeek | Opcional | Fallback de OpenRouter |
| Spotify | Opcional | Control de música |
| Telegram | Opcional | Notificaciones móviles |

Obtén tu key de Gemini en: <https://aistudio.google.com/app/apikey>

## 🎤 Comandos rápidos por voz

| Frase | Acción |
|---|---|
| "JARVIS, ¿qué ves en pantalla?" | Análisis visual |
| "Crea un Word sobre X" | `document_creator` |
| "Hazme una investigación de 20 páginas sobre X" | `deep_research` (async) |
| "¿En qué vas?" | Estado de tareas en curso |
| "Modo concentración 1 hora" | Silencia proactividad |
| "Modo programador" | Activa pair programming |
| "Dashboard" | Estadísticas de uso |
| "Busca X y cítame las fuentes" | `web_search` con URLs |
| **`Ctrl+Alt+J`** | Despertar sin wake word |

## 🧪 Tests

```bash
# Smoke tests (verifica que todo importa y arranca)
.venv\Scripts\python.exe tests\smoke_tools.py

# E2E tests (valida flujos completos)
.venv\Scripts\python.exe tests\integration_e2e.py
```

## 📂 Estructura del proyecto

```
jarvis/
├── main.py                  # Loop principal, Gemini Live, dispatcher de tools
├── ui.py                    # UI PyQt6 (holograma)
├── core/                    # Infraestructura
│   ├── activity_panel.py    # Panel flotante de actividad
│   ├── correction_learner.py # Aprende "no, así no"
│   ├── emotion_detector.py  # Detecta tono del usuario
│   ├── focus_mode.py        # Modo no molestar
│   ├── global_hotkey.py     # Ctrl+Alt+J
│   ├── hologram_helpers.py  # HTML para hologramas contextuales
│   ├── jarvis_logger.py     # Logs JSONL estructurados
│   ├── proactive_engine.py  # Sugerencias por patrones
│   ├── prompt.txt           # System prompt
│   ├── quota_manager.py     # Fallback de proveedores LLM
│   ├── sandbox.py           # Clasificación de riesgo
│   ├── session_buffer.py    # Recovery de contexto
│   ├── task_queue.py        # Cola asíncrona
│   ├── usage_dashboard.py   # Dashboard
│   └── wake_word.py         # Detección offline
├── actions/                 # +60 herramientas
│   ├── document_creator.py  # Word profesional
│   ├── deep_research.py     # Investigaciones largas
│   ├── pair_programming.py  # Modo programador
│   └── ...
├── memory/                  # Memoria persistente (gitignored)
│   └── memory_engine.py
├── config/                  # Configuración (api_keys.json gitignored)
│   └── api_keys.template.json
├── tests/                   # Smoke + E2E
└── requirements.txt
```

## 🛡️ Seguridad

- `config/api_keys.json` está en `.gitignore` — **NUNCA** lo subas a git
- `memory/long_term.json` también — contiene info personal
- Los logs JSONL están en `.gitignore` por privacidad
- `actions/terminal_agent.py` y `actions/self_edit.py` son **archivos intocables** por seguridad
- Comandos destructivos requieren confirmación explícita del usuario

## 📜 Licencia

Uso personal / educativo. Las API keys, modelos y servicios externos están sujetos a sus propios términos.

---

*JARVIS — para que la vida funcione en sintonía contigo. 🤖🎯*
