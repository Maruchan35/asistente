# -*- coding: utf-8 -*-
"""
skill_factory.py — JARVIS se extiende a sí mismo: crea herramientas nuevas por voz.

Flujo completo con red de seguridad:
  design  → el LLM diseña actions/<skill>.py (función + entry point estándar)
            y la declaración de tool para el registry
  install → 1. backup de tool_registry.py
            2. escribe actions/<skill>.py (sintaxis validada con ast)
            3. inserta la declaración en core/tool_registry.py
            4. corre tests/test_tool_consistency.py + smoke
            5. tests verdes → conservar; rojos → ROLLBACK total
  list    → habilidades creadas por la fábrica

LÍMITES DUROS:
  • Solo escribe en actions/ (nunca core, main, intocables)
  • Nombre validado: [a-z_][a-z0-9_]{2,30}, no colisiona con tool existente
  • Requiere nivel autonomía 3 o confirmación explícita para INSTALAR
  • Sandbox: el código generado se escanea por patrones peligrosos antes de escribir
"""
from __future__ import annotations
import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_BASE     = Path(__file__).resolve().parent.parent
_ACTIONS  = _BASE / "actions"
_REGISTRY = _BASE / "core" / "tool_registry.py"
_BACKUPS  = _BASE / "backups"
_MANIFEST = _BASE / "config" / "factory_skills.json"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,30}$")

# Patrones peligrosos que NO se permiten en código autogenerado
_FORBIDDEN_CODE = [
    r"\bos\.remove\b", r"\bshutil\.rmtree\b", r"\bos\.unlink\b",
    r"\bsubprocess\.(?:run|Popen|call)\b.*(?:rm |del |format|rmdir)",
    r"\bRemove-Item\b", r"\bformat\b.*[a-zA-Z]:",
    r"__import__\(.*terminal_agent", r"\bself_edit\b",
    r"\beval\(", r"\bexec\(", r"open\([^)]*['\"][wa]",  # escritura de archivos arbitraria
]


def _llm(prompt: str, system: str, max_tokens: int = 3500) -> str:
    from actions.deep_research import _llm_call
    return _llm_call(prompt, max_tokens=max_tokens, system=system)


def _existing_tool_names() -> set[str]:
    try:
        from core.tool_registry import TOOL_DECLARATIONS
        return {d.get("name", "") for d in TOOL_DECLARATIONS}
    except Exception:
        return set()


def _load_manifest() -> list[dict]:
    try:
        return json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_manifest(items: list[dict]) -> None:
    try:
        from core.safe_json import safe_write
        safe_write(_MANIFEST, items)
    except Exception:
        _MANIFEST.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _design(description: str, suggested_name: str = "") -> dict:
    """Pedir al LLM el código + declaración. Devuelve dict validado."""
    existing = ", ".join(sorted(_existing_tool_names()))
    system = (
        "Eres un ingeniero que crea herramientas para el asistente JARVIS. "
        "Devuelves SOLO un JSON válido sin markdown con esta forma exacta:\n"
        '{"name": "snake_case_unico", '
        '"code": "CONTENIDO COMPLETO de actions/<name>.py", '
        '"declaration": {DECLARACION de tool con name/description/parameters}, '
        '"summary": "que hace en 1 frase"}\n\n'
        "REGLAS del code:\n"
        "- Define exactamente UNA función `def <name>(parameters: dict, player=None) -> str`\n"
        "- Devuelve SIEMPRE un string con el resultado para el usuario\n"
        "- Usa solo librerías estándar de Python o las ya instaladas (requests, "
        "pyautogui, psutil, pyperclip, urllib). NO instales nada.\n"
        "- NO borres archivos, NO uses eval/exec, NO toques terminal_agent ni self_edit\n"
        "- Maneja errores con try/except y devuelve el error como string\n"
        "- Comentarios en español, código limpio\n\n"
        "REGLAS de declaration: formato Gemini con type OBJECT, properties con type "
        "STRING/INTEGER/BOOLEAN, y description clara de cuándo usar la tool."
    )
    user = (
        f"Crea una herramienta nueva para JARVIS que: {description}\n"
        + (f"Nombre sugerido: {suggested_name}\n" if suggested_name else "")
        + f"\nNombres de tools YA existentes (NO uses estos): {existing}\n\n"
        "Devuelve el JSON."
    )
    raw = _llm(user, system).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except Exception:
        return {"ok": False, "reason": "El LLM no devolvió JSON parseable."}

    name = (data.get("name") or "").strip()
    code = data.get("code") or ""
    decl = data.get("declaration") or {}

    # Validaciones
    if not _NAME_RE.match(name):
        return {"ok": False, "reason": f"Nombre inválido '{name}' (usa snake_case, 3-30 chars)."}
    if name in _existing_tool_names():
        return {"ok": False, "reason": f"Ya existe una tool llamada '{name}'."}
    if (_ACTIONS / f"{name}.py").exists():
        return {"ok": False, "reason": f"Ya existe el archivo actions/{name}.py."}
    if not code.strip() or f"def {name}" not in code:
        return {"ok": False, "reason": f"El código no define la función {name}()."}
    # Sintaxis
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"ok": False, "reason": f"El código tiene error de sintaxis: {e}"}
    # Patrones peligrosos
    for pat in _FORBIDDEN_CODE:
        if re.search(pat, code, re.IGNORECASE):
            return {"ok": False, "reason": f"El código generado contiene un patrón no permitido ({pat})."}
    # Declaración mínima
    if decl.get("name") != name or "description" not in decl:
        decl = {"name": name, "description": data.get("summary", description),
                "parameters": decl.get("parameters", {"type": "OBJECT", "properties": {}})}

    return {"ok": True, "name": name, "code": code, "declaration": decl,
            "summary": data.get("summary", "")}


def _insert_declaration(decl: dict) -> None:
    """Insertar la declaración antes del ] final del registry."""
    src = _REGISTRY.read_text(encoding="utf-8")
    decl_str = "    " + json.dumps(decl, ensure_ascii=False, indent=4).replace("\n", "\n    ")
    idx = src.rstrip().rfind("]")
    new_src = src[:idx] + decl_str + ",\n" + src[idx:]
    ast.parse(new_src)   # validar antes de escribir
    _REGISTRY.write_text(new_src, encoding="utf-8")


def _run_tests() -> tuple[bool, str]:
    venv_py = _BASE / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    out_all = ""
    for test in ("test_tool_consistency.py", "smoke_tools.py"):
        try:
            p = subprocess.run([py, str(_BASE / "tests" / test)],
                               capture_output=True, text=True, timeout=180, cwd=str(_BASE),
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out_all += f"[{test}] {(p.stdout or '')[-150:]}\n"
            if p.returncode != 0:
                return False, out_all
        except Exception as e:
            return False, f"{test}: {e}"
    return True, out_all


def _install(design: dict) -> str:
    from core.autonomy import audit
    name = design["name"]
    skill_path = _ACTIONS / f"{name}.py"

    # Backup del registry
    _BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reg_backup = _BACKUPS / f"tool_registry.{stamp}.bak"
    shutil.copy2(_REGISTRY, reg_backup)
    reg_original = _REGISTRY.read_text(encoding="utf-8")

    # Escribir skill + declaración
    header = f'# -*- coding: utf-8 -*-\n# Skill autogenerada por JARVIS Skill Factory el {stamp}\n'
    skill_path.write_text(header + design["code"], encoding="utf-8")
    try:
        _insert_declaration(design["declaration"])
    except Exception as e:
        skill_path.unlink(missing_ok=True)
        _REGISTRY.write_text(reg_original, encoding="utf-8")
        return f"No se pudo insertar la declaración: {e}. Nada cambió."

    # Tests
    ok, out = _run_tests()
    if ok:
        manifest = _load_manifest()
        manifest.append({"name": name, "summary": design.get("summary", ""),
                         "created": stamp})
        _save_manifest(manifest)
        audit("skill_factory", f"Nueva skill creada: {name}",
              f"tests verdes — {design.get('summary','')}")
        return (f"HABILIDAD CREADA: '{name}' — {design.get('summary','')}. "
                f"Tests: PASS. Reinicie JARVIS (diga 'reiníciate') para activarla.")
    # Rollback
    skill_path.unlink(missing_ok=True)
    _REGISTRY.write_text(reg_original, encoding="utf-8")
    audit("skill_factory", f"Skill '{name}' REVERTIDA — tests fallaron", out[:150])
    return (f"Creé '{name}' pero los tests fallaron — hice ROLLBACK, nada cambió. "
            f"Detalle: {out[:200]}")


# Estado temporal del último diseño (para confirmar antes de instalar)
_pending: dict = {}


def skill_factory(parameters: dict, player=None) -> str:
    from core.autonomy import get_level, is_killed

    action = (parameters.get("action") or "design").lower()

    if action == "list":
        manifest = _load_manifest()
        if not manifest:
            return "Aún no he creado ninguna habilidad propia."
        return "Habilidades que he creado:\n" + "\n".join(
            f"  • {m['name']}: {m.get('summary','')}" for m in manifest)

    if action == "design":
        desc = (parameters.get("description") or "").strip()
        if not desc:
            return "¿Qué habilidad necesitas que cree? Descríbeme qué debe hacer."
        if player:
            try: player.write_log(f"🛠️ Diseñando habilidad: {desc[:50]}")
            except Exception: pass
        design = _design(desc, parameters.get("name", ""))
        if not design.get("ok"):
            return f"No pude diseñar la habilidad: {design.get('reason')}"
        _pending.clear()
        _pending.update(design)
        return (f"Diseñé la habilidad '{design['name']}': {design['summary']}. "
                "¿La instalo y pruebo? (instalaré con backup + tests + rollback automático). "
                "Di 'sí, instálala' para proceder.")

    if action == "install":
        if is_killed():
            return "Sistema de autonomía detenido — no se instalan habilidades."
        confirmed = parameters.get("confirmed", False)
        if isinstance(confirmed, str):
            confirmed = confirmed.lower() in ("true", "1", "yes", "sí", "si")
        if not confirmed and get_level() < 3:
            return ("Instalar una habilidad nueva requiere nivel de autonomía 3 o tu "
                    "confirmación. Di 'sí, instálala'.")
        # Si viene descripción directa, diseñar primero
        if not _pending and parameters.get("description"):
            d = _design(parameters["description"], parameters.get("name", ""))
            if not d.get("ok"):
                return f"No pude diseñar: {d.get('reason')}"
            _pending.update(d)
        if not _pending:
            return "No hay ninguna habilidad diseñada pendiente. Primero descríbeme qué necesitas."
        result = _install(_pending)
        _pending.clear()
        return result

    return f"Acción '{action}' no reconocida. Usa: design | install | list."
