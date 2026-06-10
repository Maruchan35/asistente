@echo off
title JARVIS - Reinstalacion Limpia v4
cd /d "%~dp0"

echo.
echo [JARVIS] Reinstalacion completa desde GitHub...
echo.

:: ── Verificar git ──────────────────────────────────────────────────────────────
where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git no esta instalado.
    echo         Descargalo de: https://git-scm.com/download/win
    pause
    exit /b 1
)

:: ── Verificar Python ───────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Instala Python 3.12 desde python.org y marca "Add to PATH".
    pause
    exit /b 1
)

:: ── 1. Backup de config personal y memoria ────────────────────────────────────
echo [1/5] Guardando configuracion personal y memoria...
set BACKUP=%USERPROFILE%\Documents\_jarvis_backup_temp
if exist "%BACKUP%" rmdir /s /q "%BACKUP%"
mkdir "%BACKUP%"
mkdir "%BACKUP%\config"
mkdir "%BACKUP%\memory"

:: Config personal (NO se sube al repo — debe preservarse)
if exist "config\api_keys.json"               copy "config\api_keys.json"               "%BACKUP%\config\" >nul
if exist "config\google_credentials.json"     copy "config\google_credentials.json"     "%BACKUP%\config\" >nul
if exist "config\google_token_gmail.json"     copy "config\google_token_gmail.json"     "%BACKUP%\config\" >nul
if exist "config\google_token_calendar.json"  copy "config\google_token_calendar.json"  "%BACKUP%\config\" >nul
if exist "config\macros.json"                 copy "config\macros.json"                 "%BACKUP%\config\" >nul
if exist "config\rules.json"                  copy "config\rules.json"                  "%BACKUP%\config\" >nul
if exist "config\accessibility_config.json"   copy "config\accessibility_config.json"   "%BACKUP%\config\" >nul
if exist "config\whatsapp_contacts.json"      copy "config\whatsapp_contacts.json"      "%BACKUP%\config\" >nul
if exist "config\whatsapp_coords.json"        copy "config\whatsapp_coords.json"        "%BACKUP%\config\" >nul
if exist "config\user_profile.json"           copy "config\user_profile.json"           "%BACKUP%\config\" >nul

:: Memoria persistente del usuario (datos privados)
if exist "memory\long_term.json"              copy "memory\long_term.json"              "%BACKUP%\memory\" >nul
if exist "memory\recent_turns.json"           copy "memory\recent_turns.json"           "%BACKUP%\memory\" >nul
if exist "memory\knowledge_base.json"         copy "memory\knowledge_base.json"         "%BACKUP%\memory\" >nul
if exist "memory\sessions"                    xcopy "memory\sessions" "%BACKUP%\memory\sessions\" /E /I /Q >nul

echo [OK] Backup guardado en: %BACKUP%
echo.

:: ── 2. Clonar repo nuevo ───────────────────────────────────────────────────────
echo [2/5] Descargando JARVIS nuevo desde GitHub...
set NEWDIR=%USERPROFILE%\Documents\_jarvis_repo_nuevo
if exist "%NEWDIR%" rmdir /s /q "%NEWDIR%"

git clone https://github.com/Maruchan35/asistente "%NEWDIR%"
if errorlevel 1 (
    echo [ERROR] No se pudo clonar. Verifica tu internet.
    rmdir /s /q "%BACKUP%" >nul 2>&1
    pause
    exit /b 1
)
echo [OK] Repositorio descargado.
echo.

:: ── 3. Aplicar archivos base del repo nuevo (preservando config y memoria) ────
echo [3/5] Aplicando archivos del repo nuevo...
robocopy "%NEWDIR%" "%~dp0" /E /XD ".venv" "config" "memory" ".git" "logs" "backups" /XF "*.log" /NJH /NJS /NFL /NDL >nul
echo [OK] Codigo actualizado.
echo.

:: ── 4. Restaurar SOLO config y memoria personal ───────────────────────────────
echo [4/5] Restaurando configuracion y memoria personal...

:: Config del usuario (api_keys, tokens, etc)
if exist "%BACKUP%\config\api_keys.json"              copy "%BACKUP%\config\api_keys.json"              "%~dp0config\" >nul
if exist "%BACKUP%\config\google_credentials.json"    copy "%BACKUP%\config\google_credentials.json"    "%~dp0config\" >nul
if exist "%BACKUP%\config\google_token_gmail.json"    copy "%BACKUP%\config\google_token_gmail.json"    "%~dp0config\" >nul
if exist "%BACKUP%\config\google_token_calendar.json" copy "%BACKUP%\config\google_token_calendar.json" "%~dp0config\" >nul
if exist "%BACKUP%\config\macros.json"                copy "%BACKUP%\config\macros.json"                "%~dp0config\" >nul
if exist "%BACKUP%\config\rules.json"                 copy "%BACKUP%\config\rules.json"                 "%~dp0config\" >nul
if exist "%BACKUP%\config\accessibility_config.json"  copy "%BACKUP%\config\accessibility_config.json"  "%~dp0config\" >nul
if exist "%BACKUP%\config\whatsapp_contacts.json"     copy "%BACKUP%\config\whatsapp_contacts.json"     "%~dp0config\" >nul
if exist "%BACKUP%\config\whatsapp_coords.json"       copy "%BACKUP%\config\whatsapp_coords.json"       "%~dp0config\" >nul
if exist "%BACKUP%\config\user_profile.json"          copy "%BACKUP%\config\user_profile.json"          "%~dp0config\" >nul

:: Si no hay api_keys.json (primera instalacion), copiar el template
if not exist "config\api_keys.json" (
    if exist "config\api_keys.template.json" (
        copy "config\api_keys.template.json" "config\api_keys.json" >nul
        echo [!!] Primera instalacion: configura tus API keys en config\api_keys.json
    )
)

:: Memoria persistente del usuario
if exist "%BACKUP%\memory\long_term.json"     copy "%BACKUP%\memory\long_term.json"     "%~dp0memory\" >nul
if exist "%BACKUP%\memory\recent_turns.json"  copy "%BACKUP%\memory\recent_turns.json"  "%~dp0memory\" >nul
if exist "%BACKUP%\memory\knowledge_base.json" copy "%BACKUP%\memory\knowledge_base.json" "%~dp0memory\" >nul
if exist "%BACKUP%\memory\sessions"           xcopy "%BACKUP%\memory\sessions" "%~dp0memory\sessions\" /E /I /Y /Q >nul

echo [OK] Datos personales restaurados.
echo.

:: ── 5. Crear venv limpio e instalar dependencias ──────────────────────────────
echo [5/5] Creando entorno virtual e instalando dependencias...
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
echo [..] Instalando dependencias del requirements.txt (3-8 minutos)...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!!] Algunos paquetes fallaron, intentando uno por uno...
    for /f "tokens=* delims=" %%p in (requirements.txt) do (
        echo %%p | findstr /b "#" >nul
        if errorlevel 1 (
            if not "%%p"=="" (
                echo     Instalando: %%p
                .venv\Scripts\python.exe -m pip install "%%p" --quiet 2>nul
            )
        )
    )
)

echo.
echo [OK] Dependencias instaladas.
echo.

:: ── Limpiar temporales y lanzar ───────────────────────────────────────────────
rmdir /s /q "%NEWDIR%"  >nul 2>&1
rmdir /s /q "%BACKUP%"  >nul 2>&1

echo ============================================================
echo   JARVIS v4 - Reinstalacion completada
echo
echo   Mejoras incluidas:
echo   - Memoria persistente + recovery de contexto
echo   - deep_research (investigaciones por secciones)
echo   - Pair programming + Focus mode
echo   - Proactive engine + Emotion detection
echo   - Hologramas contextuales
echo   - Dashboard de uso + Tests E2E
echo   - Activity panel + Global hotkey Ctrl+Alt+J
echo ============================================================
echo.

.venv\Scripts\python.exe main.py

echo.
echo [JARVIS] Se cerro. Si hay error, leelo arriba.
pause
