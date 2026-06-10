@echo off
title JARVIS AI
cd /d "%~dp0"

echo.
echo [JARVIS] Iniciando...
echo.

:: ── Buscar Python del venv ────────────────────────────────────────────────────
set PYTHON=
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    echo [OK] Entorno virtual encontrado.
) else (
    echo [!!] No hay entorno virtual. Creando...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual. Instala Python 3.12.
        pause
        exit /b 1
    )
    set PYTHON=.venv\Scripts\python.exe
    echo [OK] Entorno virtual creado.
)

:: ── Instalar dependencias faltantes ──────────────────────────────────────────
echo [..] Verificando dependencias...

"%PYTHON%" -c "import google.genai" >nul 2>&1
if errorlevel 1 (
    echo [!!] Instalando google-genai...
    "%PYTHON%" -m pip install google-genai --quiet
)

"%PYTHON%" -c "import pyautogui" >nul 2>&1
if errorlevel 1 (
    echo [!!] Instalando pyautogui...
    "%PYTHON%" -m pip install pyautogui --quiet
)

"%PYTHON%" -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo [!!] Instalando PyQt6...
    "%PYTHON%" -m pip install pyqt6 pyqt6-webengine --quiet
)

"%PYTHON%" -c "import sounddevice" >nul 2>&1
if errorlevel 1 (
    echo [!!] Instalando sounddevice...
    "%PYTHON%" -m pip install sounddevice --quiet
)

"%PYTHON%" -c "import numpy" >nul 2>&1
if errorlevel 1 (
    echo [!!] Instalando numpy...
    "%PYTHON%" -m pip install numpy --quiet
)

echo [OK] Dependencias listas.
echo.

:: ── Verificar api_keys.json ───────────────────────────────────────────────────
if not exist "config\api_keys.json" (
    if exist "config\api_keys.example.json" (
        copy "config\api_keys.example.json" "config\api_keys.json" >nul
        echo [OK] Plantilla de config copiada.
    )
)

:: ── Lanzar JARVIS ─────────────────────────────────────────────────────────────
echo [>>] Lanzando JARVIS...
echo.
"%PYTHON%" main.py

:: ── Si llega aqui, JARVIS cerro o crasheo ────────────────────────────────────
echo.
echo [JARVIS] Se cerro. Si hay error, leelo arriba.
echo.
pause
