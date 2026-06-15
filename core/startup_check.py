"""
core/startup_check.py — Validación de integridad al arrancar JARVIS.

Corre verificaciones RÁPIDAS (AST, sin red, < 1s) que atrapan bugs estructurales
ANTES de que el usuario los descubra usándolos. Habría detectado al instante:
  • el bug de la visión (lectores leían claves cifradas sin descifrar)
  • una tool declarada sin dispatcher (Gemini la llamaría y fallaría)

Si algo está roto, avisa en consola con detalle. NO bloquea el arranque
(JARVIS sigue funcionando), pero el usuario sabe que hay un problema latente.
"""
from __future__ import annotations
import ast
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_ENCRYPTED_KEYS = (
    "gemini_api_key", "openrouter_api_key", "deepseek_api_key",
    "groq_api_key", "telegram_bot_token",
)
_EXEMPT_READERS = {"core/secure_config.py", "install.py"}


def _check_tool_consistency() -> list[str]:
    """Cada tool declarada debe tener dispatcher o fallback dinámico válido."""
    problems = []
    try:
        main_src = (_BASE / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(main_src)

        # Nombres declarados (en tool_registry o main)
        declared = set()
        for src_file in ("core/tool_registry.py", "main.py"):
            p = _BASE / src_file
            if not p.exists():
                continue
            t = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(t):
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "TOOL_DECLARATIONS":
                            if isinstance(node.value, ast.List):
                                for elt in node.value.elts:
                                    if isinstance(elt, ast.Dict):
                                        for k, v in zip(elt.keys, elt.values):
                                            if (isinstance(k, ast.Constant) and k.value == "name"
                                                    and isinstance(v, ast.Constant)):
                                                declared.add(v.value)

        # Nombres con dispatcher (name == "X")
        dispatched = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "name":
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        dispatched.add(comp.value)

        for name in declared - dispatched:
            # ¿tiene módulo actions/<name>.py con función <name>?
            mod = _BASE / "actions" / f"{name}.py"
            ok = False
            if mod.exists():
                try:
                    mt = ast.parse(mod.read_text(encoding="utf-8", errors="ignore"))
                    ok = any(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name
                             for x in mt.body)
                except Exception:
                    pass
            if not ok:
                problems.append(f"tool '{name}' declarada sin dispatcher ni actions/{name}.py")
    except Exception as e:
        problems.append(f"no se pudo validar consistencia de tools: {e}")
    return problems


def _check_key_readers() -> list[str]:
    """Ningún módulo debe leer api_keys.json y usar claves cifrables sin secure_config."""
    problems = []
    try:
        for py in _BASE.rglob("*.py"):
            rel = str(py.relative_to(_BASE)).replace("\\", "/")
            if (rel in _EXEMPT_READERS or rel.startswith(".venv")
                    or "__pycache__" in rel or rel.startswith("backups/")
                    or rel.startswith("tests/")):
                continue
            try:
                src = py.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if ("api_keys.json" in src and any(k in src for k in _ENCRYPTED_KEYS)
                    and "secure_config" not in src and "read_config" not in src):
                problems.append(f"{rel} lee claves sin secure_config (recibiría 'enc::')")
    except Exception as e:
        problems.append(f"no se pudo validar lectores de claves: {e}")
    return problems


def run_startup_check(verbose: bool = True) -> dict:
    """Ejecuta todas las validaciones. Devuelve {ok, problems}."""
    problems = []
    problems += _check_tool_consistency()
    problems += _check_key_readers()

    ok = len(problems) == 0
    if verbose:
        if ok:
            print("[STARTUP-CHECK] OK — integridad de tools y config verificada.")
        else:
            print(f"[STARTUP-CHECK] !! {len(problems)} problema(s) de integridad detectados:")
            for p in problems:
                print(f"[STARTUP-CHECK]    - {p}")
    return {"ok": ok, "problems": problems}
