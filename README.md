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

## 🚀 Instalación

### Opción 1 — Instalación automática

1. Instala [Python 3.12](https://www.python.org/downloads/) con "Add Python to PATH"
2. Instala [Git](https://git-scm.com/download/win)
3. Clona el repo:
   ```bash
   git clone https://github.com/TU_USUARIO/JARVIS-AI.git
   cd JARVIS-AI
   ```
4. Ejecuta el instalador:
   ```cmd
   Instalar_JARVIS.bat
   ```
5. Copia el template de configuración:
   ```cmd
   copy config\api_keys.template.json config\api_keys.json
   ```
6. Edita `config/api_keys.json` y pega tus API keys (Gemini obligatorio)
7. Lanza con `JARVIS_Iniciar.bat`

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
