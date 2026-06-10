"""codebase.py — Real code analysis: file tree, metrics, complexity, search, stats.
Works on any project directory. Python files get AST analysis; all files get metrics."""
from __future__ import annotations
import ast, json, os, re, subprocess
from pathlib import Path
from collections import defaultdict

BASE_DIR  = Path(__file__).resolve().parent.parent
CONF_FILE = BASE_DIR / "config" / "codebase_config.json"

# ── Config ────────────────────────────────────────────────────────────────────
def _load_conf() -> dict:
    try:
        return json.loads(CONF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_conf(cfg: dict):
    CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONF_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def _resolve_dir(parameters: dict) -> str:
    d = (parameters.get("path") or parameters.get("directory") or "").strip()
    if d and os.path.isdir(d):
        return d
    cfg = _load_conf()
    default = cfg.get("default_path", "").strip()
    if default and os.path.isdir(default):
        return default
    return str(BASE_DIR)  # fallback to JARVIS root

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "env", ".env", "dist", "build", ".pytest_cache", ".mypy_cache"}
CODE_EXTS  = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs", ".cpp",
              ".c", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala"}
TEXT_EXTS  = CODE_EXTS | {".html", ".css", ".json", ".yaml", ".yml",
                            ".md", ".txt", ".xml", ".sh", ".bat", ".ps1"}

# ── File walker ───────────────────────────────────────────────────────────────
def _walk_files(root: str, max_depth: int = 8) -> list[Path]:
    files = []
    root_p = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root_p)
        depth = len(rel.parts)
        if depth > max_depth:
            dirnames.clear()
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            files.append(Path(dirpath) / f)
    return files

# ── Python AST analysis ───────────────────────────────────────────────────────
def _analyze_python(content: str) -> dict:
    """Parse Python file, return classes/functions/imports counts + complexity."""
    result = {"classes": [], "functions": [], "imports": [], "lines": 0,
              "complexity": 0, "errors": []}
    try:
        tree = ast.parse(content)
        result["lines"] = content.count("\n") + 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result["functions"].append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name)
                else:
                    result["imports"].append(f"from {node.module}")
            # Simple cyclomatic complexity: count branches
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                   ast.With, ast.Assert, ast.comprehension)):
                result["complexity"] += 1
        result["complexity"] = max(1, result["complexity"])
    except SyntaxError as e:
        result["errors"].append(f"SyntaxError: {e}")
    except Exception as e:
        result["errors"].append(str(e))
    return result

def _ai(prompt: str) -> str:
    try:
        from actions.openrouter_agent import openrouter_agent
        return openrouter_agent(prompt)
    except Exception as e:
        return f"[AI no disponible: {e}]"

# ══════════════════════════════════════════════════════════════════════════════
def codebase(parameters: dict, player=None) -> str:
    action  = parameters.get("action", "overview").lower().strip()
    root    = _resolve_dir(parameters)
    query   = parameters.get("query", parameters.get("search", "")).strip()
    file_p  = parameters.get("file", "").strip()
    ext_f   = parameters.get("extension", "").lower().strip().lstrip(".")

    def log(msg: str):
        if player:
            player.write_log(f"🔍 codebase: {msg}")

    # ── SET PATH ─────────────────────────────────────────────────────────────
    if action in ("set_path", "set", "configurar"):
        path = (parameters.get("path") or "").strip()
        if not path or not os.path.isdir(path):
            return f"La ruta '{path}' no existe."
        cfg = _load_conf()
        cfg["default_path"] = path
        _save_conf(cfg)
        return f"Ruta del proyecto configurada: {path}"

    # ── OVERVIEW / STRUCTURE ──────────────────────────────────────────────────
    if action in ("overview", "structure", "tree", "resumen"):
        files = _walk_files(root, max_depth=4)
        by_ext: dict[str, int] = defaultdict(int)
        total_lines = 0
        total_files = len(files)

        for f in files:
            by_ext[f.suffix.lower()] += 1
            if f.suffix.lower() in TEXT_EXTS:
                try:
                    total_lines += f.read_text(
                        encoding="utf-8", errors="replace").count("\n")
                except Exception:
                    pass

        top_exts = sorted(by_ext.items(), key=lambda x: x[1], reverse=True)[:8]
        ext_str  = "  ".join(f"{e or 'sin ext'}:{n}" for e, n in top_exts)

        # Quick tree (first 2 levels)
        root_p   = Path(root)
        tree_lines = [f"📁 {root_p.name}/"]
        for item in sorted(root_p.iterdir()):
            if item.name in SKIP_DIRS or item.name.startswith("."):
                continue
            if item.is_dir():
                n_files = sum(1 for _ in item.rglob("*") if _.is_file())
                tree_lines.append(f"  📂 {item.name}/  ({n_files} archivos)")
            else:
                tree_lines.append(f"  📄 {item.name}")
            if len(tree_lines) > 25:
                tree_lines.append("  ...")
                break

        log(f"Overview de {total_files} archivos en {root}")
        return (f"Proyecto: {root_p.name}\n"
                f"Archivos: {total_files} | Líneas: {total_lines:,}\n"
                f"Tipos: {ext_str}\n\n"
                + "\n".join(tree_lines))

    # ── STATS ────────────────────────────────────────────────────────────────
    elif action in ("stats", "metrics", "métricas"):
        files = _walk_files(root)
        py_files = [f for f in files if f.suffix == ".py"]

        total_lines = 0; total_classes = 0; total_funcs = 0
        total_complexity = 0; py_errors = []

        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                info = _analyze_python(content)
                total_lines     += info["lines"]
                total_classes   += len(info["classes"])
                total_funcs     += len(info["functions"])
                total_complexity+= info["complexity"]
                if info["errors"]:
                    py_errors.append(f"{f.name}: {info['errors'][0]}")
            except Exception as e:
                py_errors.append(f"{f.name}: {e}")

        n = len(py_files)
        avg_complexity = total_complexity / n if n else 0
        log(f"Stats: {n} archivos Python analizados")
        result = (f"Estadísticas de {Path(root).name}:\n"
                  f"  Archivos Python: {n}\n"
                  f"  Líneas totales: {total_lines:,}\n"
                  f"  Clases: {total_classes}\n"
                  f"  Funciones: {total_funcs}\n"
                  f"  Complejidad promedio: {avg_complexity:.1f}")
        if py_errors:
            result += f"\n\n⚠ Archivos con errores de sintaxis ({len(py_errors)}):\n"
            result += "\n".join(f"  • {e}" for e in py_errors[:5])
        return result

    # ── SEARCH ───────────────────────────────────────────────────────────────
    elif action in ("search", "buscar", "grep", "find"):
        if not query:
            return "Especificá query para buscar en el código."
        matches = []
        pattern = re.compile(query, re.IGNORECASE)
        files = _walk_files(root)
        if ext_f:
            files = [f for f in files if f.suffix.lstrip(".") == ext_f]
        for f in files:
            if f.suffix.lower() not in TEXT_EXTS:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                for i, line in enumerate(lines, 1):
                    if pattern.search(line):
                        rel = str(f.relative_to(root))
                        matches.append(f"  {rel}:{i}  {line.strip()[:80]}")
                        if len(matches) >= 30:
                            break
            except Exception:
                continue
            if len(matches) >= 30:
                matches.append(f"  ... (primeros 30 resultados)")
                break
        log(f"Search '{query}': {len(matches)} matches")
        if not matches:
            return f"No se encontró '{query}' en el código."
        return f"Resultados para '{query}':\n" + "\n".join(matches)

    # ── ANALYZE FILE ─────────────────────────────────────────────────────────
    elif action in ("analyze_file", "analizar_archivo", "file"):
        if not file_p:
            return "Especificá file con la ruta del archivo a analizar."
        full = Path(root) / file_p if not os.path.isabs(file_p) else Path(file_p)
        if not full.exists():
            return f"Archivo '{file_p}' no encontrado."
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error leyendo '{file_p}': {e}"

        if full.suffix == ".py":
            info = _analyze_python(content)
            summary = (f"Archivo: {full.name}\n"
                       f"Líneas: {info['lines']}\n"
                       f"Clases: {', '.join(info['classes'][:10]) or 'ninguna'}\n"
                       f"Funciones: {', '.join(info['functions'][:10]) or 'ninguna'}\n"
                       f"Complejidad: {info['complexity']}")
            if info["errors"]:
                summary += f"\n⚠ {info['errors'][0]}"
        else:
            lines = content.count("\n") + 1
            summary = f"Archivo: {full.name} | {lines} líneas | {len(content):,} chars"

        # AI review
        prompt = (f"Revisá el siguiente código de {full.name} y dá un análisis breve: "
                  f"¿qué hace?, ¿tiene bugs obvios?, ¿qué mejorarías?\n\n"
                  f"{content[:6000]}")
        ai_review = _ai(prompt)
        log(f"Analizado: {full.name}")
        return f"{summary}\n\n{ai_review}"

    # ── FIND TODOS ────────────────────────────────────────────────────────────
    elif action in ("todos", "find_todos", "pendientes"):
        pattern = re.compile(r"#\s*(TODO|FIXME|HACK|NOQA|NOTE|BUG):?\s*(.+)", re.IGNORECASE)
        results = []
        for f in _walk_files(root):
            if f.suffix.lower() not in TEXT_EXTS:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                for i, line in enumerate(lines, 1):
                    m = pattern.search(line)
                    if m:
                        rel = str(f.relative_to(root))
                        results.append(f"  [{m.group(1)}] {rel}:{i} — {m.group(2).strip()[:60]}")
            except Exception:
                continue
        log(f"TODOs encontrados: {len(results)}")
        if not results:
            return "No se encontraron TODOs/FIXMEs en el código. ¡Todo limpio!"
        return f"TODOs y pendientes ({len(results)}):\n" + "\n".join(results[:40])

    # ── FIND STUBS ────────────────────────────────────────────────────────────
    elif action in ("stubs", "find_stubs", "incompletos"):
        stub_patterns = [
            re.compile(r"^\s*return\s+['\"].+['\"]$"),  # single-line return string
            re.compile(r"^\s*pass\s*$"),
            re.compile(r"^\s*\.\.\.\s*$"),
            re.compile(r"raise\s+NotImplementedError"),
        ]
        results = []
        for f in _walk_files(root):
            if f.suffix != ".py":
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                line_count = len(lines)
                if line_count <= 3:
                    # Tiny file — almost certainly a stub
                    rel = str(f.relative_to(root))
                    results.append(f"  ⚠ STUB  {rel} ({line_count} líneas)")
                    continue
                for i, line in enumerate(lines, 1):
                    for p in stub_patterns:
                        if p.search(line):
                            rel = str(f.relative_to(root))
                            results.append(f"  ⚠ {rel}:{i}")
                            break
            except Exception:
                continue
        log(f"Stubs detectados: {len(results)}")
        if not results:
            return "No se detectaron stubs obvios. ¡Todo implementado!"
        return f"Posibles stubs/incompletos ({len(results)}):\n" + "\n".join(results[:30])

    # ── DEPENDENCIES ─────────────────────────────────────────────────────────
    elif action in ("dependencies", "deps", "dependencias"):
        imports_found: set[str] = set()
        for f in _walk_files(root):
            if f.suffix != ".py":
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("import "):
                        imports_found.add(line.split()[1].split(".")[0])
                    elif line.startswith("from "):
                        parts = line.split()
                        if len(parts) >= 2:
                            imports_found.add(parts[1].split(".")[0])
            except Exception:
                continue
        STDLIB = {"os","sys","re","json","time","datetime","pathlib","subprocess",
                  "threading","collections","itertools","functools","io","math",
                  "random","string","struct","uuid","copy","abc","enum","typing",
                  "dataclasses","contextlib","asyncio","logging","warnings","traceback",
                  "inspect","ast","dis","importlib","pkgutil","site","zipfile","tarfile",
                  "shutil","tempfile","glob","fnmatch","hashlib","base64","urllib",
                  "http","email","smtplib","socket","ssl","queue","weakref","gc"}
        third_party = sorted(imports_found - STDLIB)
        log(f"Dependencias: {len(third_party)} externas detectadas")
        return (f"Dependencias de terceros detectadas ({len(third_party)}):\n"
                + "  " + ", ".join(third_party[:50]))

    # ── AI REVIEW ────────────────────────────────────────────────────────────
    elif action in ("review", "revisar", "ai_review"):
        if file_p:
            full = Path(root) / file_p if not os.path.isabs(file_p) else Path(file_p)
            if not full.exists():
                return f"Archivo '{file_p}' no encontrado."
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return f"Error: {e}"
            prompt = (f"Hacé una revisión de código detallada de '{full.name}'. "
                      "Identificá bugs, code smells, mejoras de performance y seguridad:\n\n"
                      f"{content[:8000]}")
        else:
            # Summarize the whole project
            files = _walk_files(root)
            py_files = [f for f in files if f.suffix == ".py"][:10]
            snippets = []
            for f in py_files:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")[:500]
                    rel = str(f.relative_to(root))
                    snippets.append(f"[{rel}]\n{content}")
                except Exception:
                    pass
            prompt = (f"Hacé una revisión arquitectónica del proyecto '{Path(root).name}'. "
                      f"Analizá estos archivos principales:\n\n{'---'.join(snippets)}\n\n"
                      "Identificá problemas de diseño, acoplamiento, code smells generales.")
        log(f"AI review iniciado")
        return _ai(prompt)

    return (f"Acción '{action}' no reconocida. "
            "Usa: overview | stats | search | analyze_file | todos | stubs | dependencies | review | set_path")
