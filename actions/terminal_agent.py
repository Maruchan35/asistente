# -*- coding: utf-8 -*-
import subprocess
import os
import uuid
import time
from pathlib import Path

def terminal_agent(parameters: dict, player=None) -> str:
    """
    Ejecuta cualquier comando en la terminal de Windows (PowerShell o CMD).
    JARVIS puede usar esto para cualquier tarea del sistema operativo:
    instalar/desinstalar programas, consultar información, ejecutar scripts,
    manejar archivos, redes, configuraciones, etc.
    Soporta elevación UAC en tiempo real si se requieren privilegios de Administrador.
    """
    command = parameters.get("command", "")
    shell_type = parameters.get("shell", "powershell").lower()
    timeout_sec = int(parameters.get("timeout", 120))
    run_as_admin = parameters.get("admin", False)
    working_dir = parameters.get("working_directory", None)

    if not command:
        return "No se proporcionó ningún comando para ejecutar."

    # Capa de seguridad Nivel 2: Pre-filtro de comandos destructivos
    DANGEROUS_PATTERNS = [
        "rm -rf", "rm -r", "rmdir /s", "del /s", "del /f", "format ", 
        "reg delete", "erase ", "rd /s", "shutdown /s", "poweroff", 
        "reboot", "init 0", "init 6"
    ]
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return (
                "⚠️ ALERTA DE SEGURIDAD MULTINIVEL: Se ha bloqueado la ejecución automática de este comando "
                f"debido a la presencia de un patrón altamente destructivo o peligroso ('{pattern}'). "
                "Para proteger la integridad del sistema, no ejecutamos órdenes de eliminación masiva ni apagado."
            )

    # Limitar timeout a un rango razonable
    timeout_sec = max(10, min(timeout_sec, 600))

    # --- Lógica de elevación administrativa UAC ---
    try:
        import ctypes
        is_already_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_already_admin = False

    if run_as_admin and not is_already_admin:
        # Se requiere elevación de Administrador pero JARVIS no está elevado
        if player:
            player.write_log("🔑 [Permisos] Solicitando elevación de privilegios UAC de Windows...")
            
        unique_id = uuid.uuid4().hex
        temp_out = os.path.abspath(f"config/elevated_out_{unique_id}.txt")
        temp_err = os.path.abspath(f"config/elevated_err_{unique_id}.txt")
        
        # Comando powershell envuelto que redirige la salida estándar y de error a archivos de texto
        wrapped_command = f"& {{ {command} }} > '{temp_out}' 2> '{temp_err}'"
        
        # Comando para iniciar powershell como administrador
        cmd_args = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command {wrapped_command}'"
        ]
        
        try:
            subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Esperar a que el proceso elevado inicie, corra y genere/llene el archivo de salida
            start_wait = time.time()
            while time.time() - start_wait < 7.0:
                if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                    break
                time.sleep(0.25)
                
            # Pequeña pausa para asegurar liberación de bloqueos de archivo
            time.sleep(0.15)
            
            output = ""
            error = ""
            if os.path.exists(temp_out):
                try:
                    output = Path(temp_out).read_text(encoding="utf-8", errors="replace").strip()
                    os.remove(temp_out)
                except Exception:
                    pass
            if os.path.exists(temp_err):
                try:
                    error = Path(temp_err).read_text(encoding="utf-8", errors="replace").strip()
                    os.remove(temp_err)
                except Exception:
                    pass
            
            if output or error:
                combined = ""
                if error:
                    combined += f"STDERR:\n{error}\n"
                if output:
                    combined += f"STDOUT:\n{output}"
                return f"Comando ejecutado exitosamente con elevación de Administrador (UAC):\n{combined}"
            else:
                return (
                    "El comando elevado ha sido enviado al sistema operativo. "
                    "Por favor, confirma la ventana flotante de control de cuentas (UAC) de Windows "
                    "que aparece en tu barra de tareas para permitir la ejecución."
                )
                
        except Exception as e:
            return f"Excepción ejecutando comando con elevación UAC: {str(e)}"

    # --- Ejecución estándar (ya es Admin, o no se pidió ser Admin) ---
    try:
        if shell_type == "cmd":
            cmd_args = ["cmd", "/c", command]
        else:
            # PowerShell por defecto — UTF-8 forzado para salida limpia
            cmd_args = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command",
                f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"
            ]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=working_dir,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            if output:
                # Salida hasta 3000 chars para que JARVIS tenga contexto suficiente
                if len(output) > 3000:
                    output = output[:3000] + "\n...[Salida truncada]"
                return f"Comando ejecutado exitosamente:\n{output}"
            else:
                return "Comando ejecutado exitosamente (sin salida)."
        else:
            # Incluir tanto stdout como stderr para diagnóstico
            combined = ""
            if error:
                combined += f"STDERR:\n{error}\n"
            if output:
                combined += f"STDOUT:\n{output}"
            if not combined:
                combined = "(sin salida de error)"
            return f"El comando finalizó con código {result.returncode}:\n{combined}"

    except subprocess.TimeoutExpired:
        return f"Error: El comando excedió el timeout de {timeout_sec} segundos y fue terminado."
    except FileNotFoundError:
        return f"Error: No se encontró el ejecutable para shell '{shell_type}'."
    except Exception as e:
        return f"Excepción ejecutando terminal: {str(e)}"
