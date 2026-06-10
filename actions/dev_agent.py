"""dev_agent.py — AI project builder.
Takes a project description, plans structure, writes files, installs deps,
runs the entry point, and auto-fixes errors — all from a single instruction."""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _ai(prompt: str, system: str = "") -> str:
    """Call openrouter_agent for AI generation."""
    try:
        from actions.openrouter_agent import openrouter_agent
        full = f"{system}\n\n{prompt}" if system else prompt
        return openrouter_agent(full)
    except Exception as e:
        return f"[AI error: {e}]"

def _run(args: list[str], cwd: str | None = None, timeout: int = 60) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()[:3000]
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

def _ps(cmd: str) -> str:
    ok, out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd])
    return out

def _open_vscode(path: str):
    code = subprocess.run(["where", "code"], capture_output=True, text=True).stdout.strip()
    if code:
        subprocess.Popen(["code", path], creationflags=subprocess.CREATE_NO_WINDOW)

# ──────────────────────────────────────────────────────────────────────────────
def dev_agent(parameters: dict, player=None, speak=None) -> str:
    description  = parameters.get("description", "").strip()
    language     = parameters.get("language", "python").lower().strip()
    project_name = parameters.get("project_name", "").strip()
    run_timeout  = int(parameters.get("timeout", 30))

    if not description:
        return "Necesito una descripción del proyecto. Ej: 'Calculadora de notas en Python con CLI'"

    def log(msg):
        if player: player.write_log(f"🔨 {msg}")

    def say(msg):
        if speak: speak(msg)

    # ── 1. Plan the project ────────────────────────────────────────────────────
    log("Planificando proyecto…")
    plan_prompt = f"""Sos un arquitecto de software senior. El usuario quiere:
"{description}"
Lenguaje: {language}

Respondé con un JSON válido con esta estructura exacta (sin markdown):
{{
  "project_name": "nombre_carpeta_sin_espacios",
  "description": "descripción breve",
  "files": [
    {{"path": "main.py", "description": "punto de entrada"}},
    {{"path": "utils.py", "description": "utilidades"}}
  ],
  "dependencies": ["requests"],
  "run_command": "python main.py",
  "entry_point": "main.py"
}}

Solo los archivos necesarios. Máximo 6 archivos. Dependencias reales."""

    plan_raw = _ai(plan_prompt)

    # Extract JSON from response
    plan = None
    try:
        json_match = re.search(r'\{[\s\S]*\}', plan_raw)
        if json_match:
            plan = json.loads(json_match.group())
    except Exception:
        pass

    if not plan:
        # Minimal fallback plan
        safe_name = re.sub(r'\W+', '_', description[:30]).strip('_').lower() or "proyecto"
        plan = {
            "project_name": safe_name,
            "description": description,
            "files": [{"path": "main.py", "description": "punto de entrada principal"}],
            "dependencies": [],
            "run_command": f"python main.py" if language == "python" else f"node main.js",
            "entry_point": "main.py" if language == "python" else "main.js",
        }

    if project_name:
        plan["project_name"] = project_name

    # ── 2. Create project directory ───────────────────────────────────────────
    projects_dir = BASE_DIR / "proyectos"
    projects_dir.mkdir(exist_ok=True)
    proj_dir = projects_dir / plan["project_name"]
    proj_dir.mkdir(parents=True, exist_ok=True)
    log(f"Directorio: {proj_dir}")

    # ── 3. Write each file ────────────────────────────────────────────────────
    written_files = []
    for file_spec in plan.get("files", []):
        file_path_rel = file_spec.get("path", "main.py")
        file_desc     = file_spec.get("description", "")
        file_full     = proj_dir / file_path_rel
        file_full.parent.mkdir(parents=True, exist_ok=True)

        log(f"Generando: {file_path_rel}…")

        # Build context from already-written files
        ctx_parts = []
        for wf in written_files[-3:]:
            ctx_parts.append(f"[Archivo ya escrito: {wf['path']}]\n{wf['content'][:500]}")
        ctx = "\n\n".join(ctx_parts)

        code_prompt = f"""Proyecto: {plan['description']}
Lenguaje: {language}

{ctx}

Escribí el contenido COMPLETO y FUNCIONAL para el archivo: {file_path_rel}
Descripción de este archivo: {file_desc}

REGLAS:
- Solo el código puro, sin explicaciones, sin bloques ```
- Comentarios claros en español
- Código funcional y completo
- Si es el entry point, incluí un if __name__ == '__main__' con ejemplo de uso
- Importaciones correctas"""

        code = _ai(code_prompt)

        # Clean up markdown fences if AI added them
        code = re.sub(r'^```\w*\s*', '', code, flags=re.MULTILINE)
        code = re.sub(r'```\s*$', '', code, flags=re.MULTILINE)

        file_full.write_text(code.strip(), encoding="utf-8")
        written_files.append({"path": file_path_rel, "content": code})
        log(f"✅ {file_path_rel}")

    # ── 4. Install dependencies ───────────────────────────────────────────────
    deps = plan.get("dependencies", [])
    if deps and language == "python":
        log(f"Instalando: {', '.join(deps)}…")
        ok, out = _run([sys.executable, "-m", "pip", "install"] + deps, timeout=120)
        if ok:
            log(f"Dependencias instaladas: {', '.join(deps)}")
        else:
            log(f"⚠ Pip error: {out[:200]}")
    elif deps and language in ("javascript", "node", "nodejs"):
        log("Instalando dependencias npm…")
        pkg_json = proj_dir / "package.json"
        if not pkg_json.exists():
            pkg_json.write_text(json.dumps({
                "name": plan["project_name"],
                "version": "1.0.0",
                "dependencies": {d: "latest" for d in deps}
            }, indent=2), encoding="utf-8")
        ok, out = _run(["npm", "install"], cwd=str(proj_dir), timeout=120)
        log(f"npm install: {'✅' if ok else '❌ ' + out[:200]}")

    # ── 5. Create README ──────────────────────────────────────────────────────
    readme_content = f"""# {plan['project_name']}

{plan.get('description', description)}

## Uso
```
{plan.get('run_command', '')}
```

## Dependencias
{', '.join(deps) if deps else 'Ninguna'}

## Archivos
{chr(10).join(f"- **{f['path']}** — {f['description']}" for f in plan.get('files', []))}

Generado por JARVIS dev_agent.
"""
    (proj_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # ── 6. Run the project ────────────────────────────────────────────────────
    entry = plan.get("entry_point", "main.py")
    entry_path = proj_dir / entry

    run_result = ""
    if entry_path.exists():
        log(f"Ejecutando {entry}…")
        if language == "python":
            ok, out = _run([sys.executable, str(entry_path)],
                           cwd=str(proj_dir), timeout=run_timeout)
        elif language in ("javascript", "node", "nodejs"):
            ok, out = _run(["node", str(entry_path)],
                           cwd=str(proj_dir), timeout=run_timeout)
        else:
            ok, out = False, f"Ejecución automática no soportada para {language}"

        if ok:
            run_result = f"\n\n✅ Salida:\n{out[:500]}" if out else "\n\n✅ Ejecutado sin errores."
            log("Proyecto ejecutado correctamente")
        else:
            # ── 7. Auto-fix errors ─────────────────────────────────────────
            log(f"Error detectado, auto-corrigiendo…")
            fix_prompt = f"""El proyecto "{plan['project_name']}" tiene este error al ejecutar:
{out[:1000]}

Archivos del proyecto:
{chr(10).join(f"[{f['path']}]:{chr(10)}{f['content'][:800]}" for f in written_files)}

Identificá el archivo con el error y devolvé el contenido corregido completo.
Formato: solo el código puro del archivo con error, sin explicaciones."""

            fixed_code = _ai(fix_prompt)
            fixed_code = re.sub(r'^```\w*\s*', '', fixed_code, flags=re.MULTILINE)
            fixed_code = re.sub(r'```\s*$', '', fixed_code, flags=re.MULTILINE)

            # Heuristic: re-write the entry point with the fix
            entry_path.write_text(fixed_code.strip(), encoding="utf-8")
            log("Correccion aplicada, re-ejecutando…")

            ok2, out2 = _run([sys.executable, str(entry_path)] if language == "python"
                              else ["node", str(entry_path)],
                              cwd=str(proj_dir), timeout=run_timeout)
            if ok2:
                run_result = f"\n\n✅ Corregido y ejecutado:\n{out2[:500]}"
                log("Auto-fix exitoso")
            else:
                run_result = f"\n\n⚠ Error persistente:\n{out2[:400]}"
                log("Auto-fix necesita revisión manual")

    # ── 8. Open in VSCode ─────────────────────────────────────────────────────
    _open_vscode(str(proj_dir))

    # ── Summary ───────────────────────────────────────────────────────────────
    files_list = "\n".join(f"  • {f['path']}" for f in written_files)
    summary = (
        f"Proyecto '{plan['project_name']}' creado en:\n{proj_dir}\n\n"
        f"Archivos:\n{files_list}\n"
        + (f"Dependencias: {', '.join(deps)}\n" if deps else "")
        + f"Ejecutar: {plan.get('run_command', '')}"
        + run_result
    )

    say(f"Proyecto {plan['project_name']} creado con {len(written_files)} archivos.")
    log("Proyecto listo")
    return summary
