# -*- coding: utf-8 -*-
"""
tests/test_tool_consistency.py — Verifica que TOOL_DECLARATIONS y el
dispatcher de _execute_tool estén sincronizados.

Detecta la clase de bug más repetida del proyecto:
  • Tool declarada sin rama en el dispatcher → Gemini la llama y revienta
  • Rama en el dispatcher sin declaración → código muerto que nadie puede invocar

Funciona por análisis AST de main.py (y core/tool_registry.py si existe) —
NO importa main.py (importarlo arranca Qt).

Uso:
    .venv/Scripts/python.exe tests/test_tool_consistency.py
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Tools manejadas fuera del dispatcher estándar o intencionalmente especiales
ALLOWED_DECLARED_ONLY: set[str] = set()      # declaradas sin elif (no debería haber)
ALLOWED_DISPATCHED_ONLY: set[str] = {
    "screen_process",        # alias histórico de screen_vision en el dispatcher
}


def _find_tool_declarations(tree: ast.Module) -> set[str]:
    """Nombres en TOOL_DECLARATIONS = [ {"name": "..."} , ... ]"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "TOOL_DECLARATIONS":
                if isinstance(node.value, ast.List):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Dict):
                            for k, v in zip(elt.keys, elt.values):
                                if (isinstance(k, ast.Constant) and k.value == "name"
                                        and isinstance(v, ast.Constant)):
                                    names.add(v.value)
    return names


def _find_dispatched_names(tree: ast.Module) -> set[str]:
    """Nombres comparados contra `name` dentro de _execute_tool:
    `if name == "X"`, `elif name == "X"`, `name == "X" or name == "Y"`."""
    names: set[str] = set()

    func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_execute_tool":
            func = node
            break
    if func is None:
        return names

    for node in ast.walk(func):
        if isinstance(node, ast.Compare):
            # name == "X"   /   "X" == name
            left = node.left
            comparators = node.comparators
            is_name_left = isinstance(left, ast.Name) and left.id == "name"
            for comp in comparators:
                if is_name_left and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    names.add(comp.value)
                elif (isinstance(comp, ast.Name) and comp.id == "name"
                      and isinstance(left, ast.Constant) and isinstance(left.value, str)):
                    names.add(left.value)
    return names


def main() -> int:
    main_py = ROOT / "main.py"
    tree_main = ast.parse(main_py.read_text(encoding="utf-8"))

    declared = _find_tool_declarations(tree_main)

    # Si las declaraciones viven en core/tool_registry.py, leer de ahí también
    registry = ROOT / "core" / "tool_registry.py"
    if registry.exists():
        tree_reg = ast.parse(registry.read_text(encoding="utf-8"))
        declared |= _find_tool_declarations(tree_reg)

    dispatched = _find_dispatched_names(tree_main)

    if not declared:
        print("[FAIL] No se encontró TOOL_DECLARATIONS (ni en main.py ni en core/tool_registry.py)")
        return 1
    if not dispatched:
        print("[FAIL] No se encontró el dispatcher _execute_tool en main.py")
        return 1

    missing_dispatch = declared - dispatched - ALLOWED_DECLARED_ONLY
    missing_decl     = dispatched - declared - ALLOWED_DISPATCHED_ONLY

    ok = True
    dynamic_ok: list[str] = []

    # Las tools declaradas sin elif explícito pueden funcionar vía el fallback
    # dinámico del dispatcher: importlib.import_module(f"actions.{name}") +
    # getattr(module, name). Verificar que ESE camino existe de verdad.
    truly_broken: list[str] = []
    for n in sorted(missing_dispatch):
        mod_path = ROOT / "actions" / f"{n}.py"
        if mod_path.exists():
            try:
                mod_tree = ast.parse(mod_path.read_text(encoding="utf-8", errors="ignore"))
                has_func = any(
                    isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == n
                    for x in mod_tree.body
                )
                if has_func:
                    dynamic_ok.append(n)
                    continue
            except Exception:
                pass
        truly_broken.append(n)

    if truly_broken:
        ok = False
        print(f"[FAIL] {len(truly_broken)} tool(s) declaradas SIN dispatcher NI fallback dinámico válido")
        print("       (Gemini puede llamarlas y fallarán):")
        for n in truly_broken:
            print(f"         - {n}  (falta actions/{n}.py con función {n}())")
    if missing_decl:
        ok = False
        print(f"[FAIL] {len(missing_decl)} rama(s) del dispatcher SIN declaración")
        print("       (código muerto — Gemini nunca las invocará):")
        for n in sorted(missing_decl):
            print(f"         - {n}")

    if ok:
        print(f"[PASS] {len(declared)} tools declaradas, {len(dispatched)} con elif, "
              f"{len(dynamic_ok)} vía fallback dinámico verificado — todo consistente")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
