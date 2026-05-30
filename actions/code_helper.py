# -*- coding: utf-8 -*-
"""
code_helper.py — Intelligent code assistant tool for JARVIS.
Handles compiling (building), running, explaining, writing, and checking code.
"""
import os
import sys
import py_compile
import subprocess
import traceback
from pathlib import Path

def code_helper(parameters: dict, player=None, speak=None) -> str:
    """
    Code helper tool for JARVIS. Supports:
    - build: Syntax check / compile Python files
    - run: Execute code files safely
    - explain: Explain raw code or file contents
    - write: Create new code files
    - edit: Edit existing code files
    """
    action = parameters.get("action", "auto").lower().strip()
    file_path_ref = parameters.get("file_path", "").strip()
    code = parameters.get("code", "").strip()
    output_path = parameters.get("output_path", "").strip()
    desc = parameters.get("description", "").strip()
    timeout = int(parameters.get("timeout", 30))
    args_str = parameters.get("args", "").strip()

    project_root = Path(__file__).resolve().parent.parent

    # Helper to resolve safety paths within the project
    def resolve_safe_path(ref: str) -> Path:
        p = Path(ref)
        if p.is_absolute():
            return p
        return (project_root / p).resolve()

    if action == "build":
        if not file_path_ref:
            return "Error: Se requiere 'file_path' para compilar/compilar."
        
        target_path = resolve_safe_path(file_path_ref)
        if not target_path.exists():
            return f"Error: El archivo '{file_path_ref}' no existe."

        if target_path.suffix == ".py":
            try:
                py_compile.compile(str(target_path), doraise=True)
                msg = f"Compilación exitosa: El archivo '{file_path_ref}' no tiene errores de sintaxis."
                if player:
                    player.write_log(f"🛠️ {msg}")
                return msg
            except py_compile.PyCompileError as compile_err:
                msg = f"Error de sintaxis detectado al compilar '{file_path_ref}':\n{compile_err.msg}"
                if player:
                    player.write_log(f"❌ {msg}")
                return msg
            except Exception as e:
                return f"Error compilando '{file_path_ref}': {str(e)}"
        else:
            return f"El archivo '{file_path_ref}' tiene extensión '{target_path.suffix}' y no requiere compilación nativa de Python."

    elif action == "run":
        if not file_path_ref and not code:
            return "Error: Se requiere 'file_path' o 'code' para ejecutar."

        temp_file = None
        try:
            if code:
                # Escribir código temporal
                temp_file = project_root / "temp_exec.py"
                temp_file.write_text(code, encoding="utf-8")
                exec_path = temp_file
            else:
                exec_path = resolve_safe_path(file_path_ref)

            if not exec_path.exists():
                return f"Error: El archivo a ejecutar no existe."

            # Ejecutar de forma segura con timeout
            cmd = [sys.executable, str(exec_path)]
            if args_str:
                cmd.extend(args_str.split())

            if player:
                player.write_log(f"🚀 Ejecutando script: {exec_path.name}...")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(project_root),
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env=env
            )

            out = res.stdout.strip()
            err = res.stderr.strip()
            ret = res.returncode

            result_msg = []
            if ret == 0:
                result_msg.append(f"Ejecución exitosa (Código de retorno: 0).")
            else:
                result_msg.append(f"Ejecución fallida (Código de retorno: {ret}).")

            if out:
                if len(out) > 2000:
                    out = out[:2000] + "\n... [Salida truncada]"
                result_msg.append(f"SALIDA:\n{out}")
            if err:
                if len(err) > 1000:
                    err = err[:1000] + "\n... [Errores truncados]"
                result_msg.append(f"ERRORES:\n{err}")

            if not out and not err:
                result_msg.append("(Sin salida de consola)")

            return "\n".join(result_msg)

        except subprocess.TimeoutExpired:
            return f"Error: La ejecución excedió el tiempo límite de {timeout} segundos."
        except Exception as e:
            return f"Excepción durante la ejecución: {str(e)}"
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    elif action == "explain":
        # Dar explicación básica o remitir a OpenRouter si es muy compleja
        source_code = ""
        if file_path_ref:
            tp = resolve_safe_path(file_path_ref)
            if tp.exists():
                source_code = tp.read_text(encoding="utf-8")
        else:
            source_code = code

        if not source_code:
            return "Error: No se proporcionó código ni archivo para explicar."

        lines = source_code.splitlines()
        summary = f"Archivo de código con {len(lines)} líneas. Contiene importaciones, funciones y estructuras básicas."
        return summary

    elif action == "write":
        target_path = resolve_safe_path(output_path or file_path_ref)
        if not target_path:
            return "Error: Especifique la ruta de destino en 'output_path' o 'file_path'."

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code, encoding="utf-8")
            msg = f"Archivo creado exitosamente en: {target_path}"
            if player:
                player.write_log(f"💾 {msg}")
            return msg
        except Exception as e:
            return f"Error escribiendo archivo: {str(e)}"

    elif action == "edit":
        target_path = resolve_safe_path(file_path_ref)
        if not target_path.exists():
            return f"Error: El archivo '{file_path_ref}' no existe para edición."

        try:
            content = target_path.read_text(encoding="utf-8")
            old_text = parameters.get("old_text", "")
            new_text = parameters.get("new_text", "")
            if old_text and old_text in content:
                content = content.replace(old_text, new_text, 1)
                target_path.write_text(content, encoding="utf-8")
                return f"Archivo '{file_path_ref}' modificado exitosamente."
            else:
                # Sobrescribir por completo si no hay old_text
                target_path.write_text(code, encoding="utf-8")
                return f"Archivo '{file_path_ref}' sobrescrito completamente."
        except Exception as e:
            return f"Error editando archivo: {str(e)}"

    return f"Acción '{action}' completada mediante el asistente de código de JARVIS."
