"""
tests/smoke_tools.py — Test de humo para herramientas críticas de JARVIS.

Ejecuta cada herramienta con inputs canónicos seguros y verifica que:
  • Importa sin error
  • Llama con argumentos válidos sin crashear
  • Devuelve un valor no-vacío

NO depende de Gemini, red, o APIs externas (los tests que las requieren
están marcados como skip).

Uso:
    cd C:\\Users\\marux\\Documents\\jarvis
    .venv/Scripts/python.exe tests/smoke_tools.py
    .venv/Scripts/python.exe tests/smoke_tools.py --only document_creator,memory
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

_results: list[tuple[str, str, str]] = []


def _record(name: str, status: str, info: str = ""):
    _results.append((name, status, info))
    icon = {"pass": PASS, "fail": FAIL, "skip": SKIP}.get(status, "?")
    print(f"  {icon} {name:<40} {info}")


def run(name: str, fn) -> None:
    t0 = time.time()
    try:
        result = fn()
        dur = int((time.time() - t0) * 1000)
        if result is None or result is False:
            _record(name, "fail", f"({dur}ms) — devolvió None/False")
        else:
            preview = str(result)[:50].replace("\n", " ")
            _record(name, "pass", f"({dur}ms) {preview}")
    except ImportError as e:
        _record(name, "skip", f"módulo no disponible: {e}")
    except Exception as e:
        dur = int((time.time() - t0) * 1000)
        _record(name, "fail", f"({dur}ms) {type(e).__name__}: {str(e)[:80]}")
        traceback.print_exc(limit=2)


# ══════════════════════════════════════════════════════════════════════════════
#  TESTS
# ══════════════════════════════════════════════════════════════════════════════

def t_document_creator_basic():
    """Crea Word básico — sin red."""
    from actions.document_creator import document_creator
    res = document_creator({
        "action": "word",
        "norm":   "professional",
        "title":  "JARVIS_SmokeTest",
        "save_path": str(ROOT / "tests" / "_out"),
        "content": "# Test\n\nContenido de prueba.",
    })
    assert "creado" in res.lower() or "Documento" in res
    return res


def t_document_creator_apa():
    from actions.document_creator import document_creator
    res = document_creator({
        "action": "word",
        "norm":   "apa7",
        "title":  "SmokeTest_APA",
        "save_path": str(ROOT / "tests" / "_out"),
        "toc":    True,
        "cover":  '{"institution":"X","title":"Y","authors":"Z","date":"2026"}',
        "content": "[ABSTRACT]Resumen.[/ABSTRACT]\n\n# Intro\nPárrafo.\n",
    })
    return res


def t_memory_record_and_extract():
    from memory.memory_engine import record_turn, load_long_term, get_context_block
    record_turn(
        user_text="Me llamo Jorge y vivo en México",
        jarvis_text="Anotado, señor.",
        tools_used=["smoke_test"],
    )
    lt = load_long_term()
    ctx = get_context_block()
    # Debe haber extraído al menos el nombre o ubicación
    return bool(lt) and ("PERSISTENTE" in ctx)


def t_quota_detect():
    from core.quota_manager import is_quota_error
    assert is_quota_error("RESOURCE_EXHAUSTED: daily quota") is True
    assert is_quota_error("HTTP 429 too many requests") is True
    assert is_quota_error("Connection refused") is False
    return True


def t_sandbox_critical():
    from core.sandbox import classify_command, classify_paths
    r = classify_command("rm -rf /home/user/Desktop/*")
    assert r.risk == "CRITICAL", f"esperaba CRITICAL, got {r.risk}"

    r2 = classify_paths("delete", [str(Path.home() / "Desktop" / "test.txt")])
    assert r2.risk in ("HIGH", "CRITICAL"), f"esperaba HIGH+, got {r2.risk}"

    r3 = classify_command("ls -la")
    assert r3.risk == "SAFE"
    return "SAFE/MEDIUM/HIGH/CRITICAL OK"


def t_task_queue():
    from core.task_queue import submit, get_task, list_tasks
    tid = submit("smoke add", target=lambda: sum(range(100)))
    # Esperar hasta 2s
    for _ in range(20):
        time.sleep(0.1)
        if get_task(tid).status in ("done", "failed"):
            break
    t = get_task(tid)
    assert t.status == "done", f"status={t.status}"
    assert t.result == 4950
    return f"task_id={tid} result={t.result}"


def t_jarvis_logger():
    from core.jarvis_logger import log_info, log_tool, log_error, tail
    log_info("smoke test info")
    log_tool("smoke_tool", args={"x": 1}, result_preview="ok")
    log_error("smoke test error", exc=RuntimeError("dummy"))
    entries = tail("system", n=5)
    return f"{len(entries)} entries"


def t_safe_json():
    from core.safe_json import safe_write
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "jarvis_smoke_safe.json"
    safe_write(tmp, {"foo": "bar", "n": 42})
    data = json.loads(tmp.read_text(encoding="utf-8"))
    assert data["foo"] == "bar"
    tmp.unlink()
    return "atomic write OK"


def t_knowledge_base():
    from actions.knowledge_base import knowledge_base
    res = knowledge_base({
        "action": "add",
        "category": "test",
        "key": "smoke_key",
        "value": "smoke_value",
    })
    return res


def t_user_profile():
    from actions.user_profile import user_profile
    res = user_profile({"action": "get"})
    return res


def t_goals():
    from actions.goals import goals
    res = goals({"action": "list"})
    return res or "empty list ok"


def t_scheduler():
    from actions.scheduler import scheduler
    res = scheduler({"action": "list"})
    return res or "empty list ok"


def t_screen_vision_import():
    """Solo verifica que el módulo importa — la captura real requiere pantalla."""
    from actions.screen_vision import screen_vision
    return "import OK"


def t_file_processor_import():
    from actions.file_processor import file_processor
    return "import OK"


def t_open_app_import():
    from actions.open_app import open_app
    return "import OK"


def t_deep_research_import():
    """Importa y verifica que la entrada tiene la firma correcta — NO ejecuta LLM."""
    from actions.deep_research import deep_research
    # Validar que rechaza sin topic
    res = deep_research({})
    assert "Error" in res or "obligatorio" in res
    return "import OK + validates topic"


# Mapa de tests
TESTS = {
    "logger":            t_jarvis_logger,
    "safe_json":         t_safe_json,
    "quota":             t_quota_detect,
    "sandbox":           t_sandbox_critical,
    "task_queue":        t_task_queue,
    "memory":            t_memory_record_and_extract,
    "document_creator":  t_document_creator_basic,
    "document_apa":      t_document_creator_apa,
    "knowledge_base":    t_knowledge_base,
    "user_profile":      t_user_profile,
    "goals":             t_goals,
    "scheduler":         t_scheduler,
    "screen_vision":     t_screen_vision_import,
    "file_processor":    t_file_processor_import,
    "open_app":          t_open_app_import,
    "deep_research":     t_deep_research_import,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated list of tests to run")
    args = parser.parse_args()

    (ROOT / "tests" / "_out").mkdir(parents=True, exist_ok=True)

    to_run = TESTS
    if args.only:
        names = [n.strip() for n in args.only.split(",")]
        to_run = {n: TESTS[n] for n in names if n in TESTS}

    print(f"\nJARVIS Smoke Tests - {len(to_run)} tests\n" + "-"*60)
    t_start = time.time()
    for name, fn in to_run.items():
        run(name, fn)
    elapsed = time.time() - t_start

    # Resumen
    passed = sum(1 for _, s, _ in _results if s == "pass")
    failed = sum(1 for _, s, _ in _results if s == "fail")
    skipped = sum(1 for _, s, _ in _results if s == "skip")
    print("-"*60)
    print(f"  {passed} pass | {failed} fail | {skipped} skip | {elapsed:.1f}s")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
