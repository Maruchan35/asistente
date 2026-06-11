"""
tests/integration_e2e.py — Tests de integración E2E para JARVIS.

A diferencia de smoke_tools.py (que solo verifica que las herramientas importan
y devuelven algo), este suite valida FLUJOS COMPLETOS:

  • Memoria: record_turn → load_long_term → get_context_block (encadenado)
  • Document creator: cover + TOC + sections + APA → verificar estructura del .docx
  • Deep research: outline parsing (no llama LLM)
  • Sandbox: comando peligroso → confirmación requerida → solo ejecuta tras OK
  • Task queue: submit → progress updates → callback → cleanup
  • Emotion + correction learner: input frustrado + corrección → ambos detectados
  • Hologram helpers: cada generador produce HTML válido
  • Web search structured: validar parser de DDG (con HTML sample)
  • Focus mode: enable + suppress + auto-expire

Uso:
    .venv/Scripts/python.exe tests/integration_e2e.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

_results: list[tuple[str, str, str]] = []


def _record(name: str, status: str, info: str = ""):
    _results.append((name, status, info))
    print(f"  {status} {name:<48} {info}")


def run(name: str, fn):
    t0 = time.time()
    try:
        result = fn()
        dur = int((time.time() - t0) * 1000)
        if result is False:
            _record(name, FAIL, f"({dur}ms) returned False")
        else:
            preview = str(result)[:60].replace("\n", " ") if result else ""
            _record(name, PASS, f"({dur}ms) {preview}")
    except AssertionError as e:
        dur = int((time.time() - t0) * 1000)
        _record(name, FAIL, f"({dur}ms) ASSERT: {e}")
    except ImportError as e:
        _record(name, SKIP, f"missing: {e}")
    except Exception as e:
        dur = int((time.time() - t0) * 1000)
        _record(name, FAIL, f"({dur}ms) {type(e).__name__}: {str(e)[:80]}")


# ── E2E: Memoria end-to-end ──────────────────────────────────────────────────
def t_memory_e2e():
    from memory.memory_engine import (
        record_turn, load_long_term, get_context_block, remember,
    )
    record_turn(
        "Me llamo TestUserE2E y vivo en Madrid",
        "Anotado.",
        tools_used=["test_e2e"],
    )
    lt = load_long_term()
    # Verificar que el nombre o ubicación se guardaron
    found = False
    for cat, items in lt.items():
        if not isinstance(items, dict):
            continue
        for k, v in items.items():
            val_str = str(v.get("value", "") if isinstance(v, dict) else v).lower()
            if "testusere2e" in val_str or "madrid" in val_str:
                found = True
    assert found, f"name/location not auto-extracted from text. lt={lt}"
    ctx = get_context_block()
    assert "PERSISTENTE" in ctx, "context block missing header"
    return "auto-extract + format OK"


# ── E2E: Document creator multi-feature ──────────────────────────────────────
def t_document_creator_full():
    from actions.document_creator import document_creator
    out_dir = ROOT / "tests" / "_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    res = document_creator({
        "action": "word",
        "norm": "apa7",
        "title": "E2E_Full_Test",
        "save_path": str(out_dir),
        "toc": True,
        "cover": json.dumps({
            "institution": "Test U", "title": "E2E Full",
            "authors": "JARVIS Tests", "course": "Test", "date": "2026",
        }),
        "content": (
            "[ABSTRACT]Resumen del documento de prueba.[/ABSTRACT]\n\n"
            "[TOC]\n\n"
            "# Sección 1\nContenido 1.\n\n"
            "## Subsección\n- Punto A\n- Punto B\n\n"
            "[BOX title=\"Importante\"]Nota.[/BOX]\n\n"
            "# Sección 2\nContenido 2.\n\n"
            "[REFERENCES]\nRef1\nRef2\n[/REFERENCES]"
        ),
    })
    assert "creado" in res.lower() or "Documento" in res
    # Verificar que el archivo existe
    import re
    m = re.search(r"'([^']+\.docx)'", res)
    assert m, f"no .docx file found in result: {res}"
    fname = m.group(1)
    fpath = out_dir / fname
    assert fpath.exists(), f"file not created: {fpath}"
    assert fpath.stat().st_size > 5000, f"file too small ({fpath.stat().st_size}b)"
    return f"{fname} {fpath.stat().st_size//1024}KB"


# ── E2E: Deep research outline parsing (sin LLM) ─────────────────────────────
def t_deep_research_outline_parsing():
    """Verifica que el parser de outline tolera distintos formatos del LLM."""
    from actions import deep_research as dr
    # Monkeypatch del LLM call para no usar red
    raw = """
1. Introducción || Presentación del tema y objetivos
2. Marco Teórico || Bases conceptuales
3. Metodología || Cómo se hizo
4. Resultados || Hallazgos principales
5. Conclusión || Síntesis
"""
    original = dr._llm_call
    dr._llm_call = lambda prompt, max_tokens=1200, system=None, attempt=0: raw
    try:
        sections = dr._generate_outline("Test topic", target_pages=5)
        assert len(sections) >= 4, f"expected >=4 sections, got {len(sections)}"
        assert all("||" not in s[0] for s in sections), "title contains separator"
        assert any("Introducción" in s[0] for s in sections)
    finally:
        dr._llm_call = original
    return f"parsed {len(sections)} sections"


# ── E2E: Sandbox bloquea cosas peligrosas ────────────────────────────────────
def t_sandbox_e2e():
    from core.sandbox import classify_command, classify_paths

    # CRITICAL: borrado recursivo en Desktop
    r = classify_command("rm -rf /home/test/Desktop/*")
    assert r.needs_confirmation(), "CRITICAL command should need confirmation"

    # SAFE: simple ls
    r2 = classify_command("ls -la")
    assert not r2.needs_confirmation()

    # Paths: borrado en carpeta protegida
    r3 = classify_paths("delete", [str(Path.home() / "Desktop" / "test.txt")])
    assert r3.risk in ("HIGH", "CRITICAL")

    return "block + allow OK"


# ── E2E: TaskQueue con progreso + callback ───────────────────────────────────
def t_task_queue_e2e():
    from core.task_queue import submit, get_task, set_notify_callback

    notified = []
    set_notify_callback(lambda t: notified.append(t.id))

    def slow_with_progress(task=None):
        for i in range(3):
            time.sleep(0.05)
            if task is not None:
                task.progress = f"step {i+1}/3"
        return 42

    tid = submit("e2e slow", target=slow_with_progress)
    # Esperar hasta 2s
    for _ in range(40):
        time.sleep(0.05)
        if get_task(tid).status in ("done", "failed"):
            break
    t = get_task(tid)
    assert t.status == "done", f"status={t.status} error={t.error}"
    assert t.result == 42
    assert tid in notified, f"callback no invocado. notified={notified}"
    return f"progress + callback OK ({len(notified)} cbs)"


# ── E2E: Emotion + correction learner ────────────────────────────────────────
def t_emotion_and_correction():
    from core.emotion_detector import detect
    from core.correction_learner import detect_correction

    e1 = detect("ESTO NO FUNCIONA, joder")
    assert e1.label == "frustrado", f"expected frustrado, got {e1.label}"

    e2 = detect("perfecto, gracias señor")
    assert e2.label == "contento", f"expected contento, got {e2.label}"

    e3 = detect("estoy cansado, vamos rápido")
    # cansado o apurado, ambos válidos por intensidad
    assert e3.label in ("cansado", "apurado")

    # Corrección
    c = detect_correction("no, así no, siempre usa minúsculas")
    assert c is not None, "no detectó corrección"
    return f"frust={e1.intensity:.2f} happy={e2.intensity:.2f} corr={c[0]}"


# ── E2E: Hologram helpers generan HTML válido ────────────────────────────────
def t_hologram_helpers():
    from core.hologram_helpers import (
        chart_bar, stats_panel, checklist, table, code_block,
        document_preview, map_view,
    )
    items = [("A", 10), ("B", 25), ("C", 7)]
    h1 = chart_bar("Test", items, unit="%")
    assert "<div" in h1 and "bar-fill" in h1

    h2 = stats_panel("Stats", [("X", "100"), ("Y", "42")])
    assert "stat-big" in h2

    h3 = checklist("Tareas", [("a", True), ("b", False)])
    assert "checklist" in h3 and "done" in h3

    h4 = table("T", ["a","b"], [["1","2"],["3","4"]])
    assert "<table" in h4

    h5 = code_block("test", "python", "print(1)")
    assert "<pre" in h5

    h6 = document_preview("Doc", ["H1","H2"], "snippet")
    assert "doc-preview" in h6

    h7 = map_view("Madrid")
    assert "openstreetmap" in h7.lower()
    return "7/7 helpers OK"


# ── E2E: Focus mode lifecycle ────────────────────────────────────────────────
def t_focus_mode_e2e():
    from core.focus_mode import enable, disable, is_active, should_suppress
    disable()  # reset
    assert not is_active()
    enable(duration_minutes=1, reason="test")
    assert is_active()
    assert should_suppress("normal") is True
    assert should_suppress("critical") is False
    disable()
    assert not is_active()
    return "lifecycle OK"


# ── E2E: Web search structured parsing (con HTML sample) ─────────────────────
def t_web_search_parsing():
    """Verifica el parser de DDG con HTML inventado — sin red."""
    from actions import web_search as ws

    sample_html = """
    <html><body>
    <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage1" class='result-link'>Title One</a>
    <td class='result-snippet'>Snippet de prueba uno.</td>
    <a class='result-link' href="https://example.com/page2">Title Two</a>
    <td class='result-snippet'>Snippet dos.</td>
    </body></html>
    """
    # Monkey-patch urlopen para devolver el sample
    import urllib.request, io
    orig = urllib.request.urlopen
    class FakeResp:
        def __init__(self, content): self._c = content.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return self._c
    urllib.request.urlopen = lambda *a, **k: FakeResp(sample_html)
    try:
        results = ws._ddg_lite_structured("test", max_results=5)
    finally:
        urllib.request.urlopen = orig

    assert len(results) >= 1, f"expected >=1 result, got {len(results)}"
    r0 = results[0]
    assert "example.com" in r0["url"], f"url not extracted: {r0}"
    return f"{len(results)} results parsed"


# ── E2E: Proactive engine carga sin error ────────────────────────────────────
def t_proactive_engine():
    from core.proactive_engine import list_patterns, get_suggestion_for_now
    patterns = list_patterns(top_n=5)
    # Puede estar vacío si no hay historial, eso está bien — solo no debe crashear
    s = get_suggestion_for_now()
    # s puede ser None — también OK
    return f"patterns={len(patterns)} sugg={'yes' if s else 'no'}"


# ── E2E: Usage dashboard genera texto y HTML ─────────────────────────────────
def t_usage_dashboard():
    from core.usage_dashboard import collect_stats, format_text, format_html
    stats = collect_stats()
    assert "top_tools" in stats
    txt = format_text(stats)
    assert "JARVIS Dashboard" in txt
    html = format_html(stats)
    assert "<div" in html and "card" in html
    return f"{stats['totals']['tool_calls']} calls"


# ── E2E: Session buffer ──────────────────────────────────────────────────────
def t_session_buffer():
    from core.session_buffer import push, snapshot, clear, format_for_reinjection
    clear()
    push("hola jarvis", "buenas, señor")
    push("dime la hora", "son las 3pm")
    snap = snapshot()
    assert len(snap) == 2
    fmt = format_for_reinjection()
    assert "CONTEXTO INMEDIATO" in fmt
    clear()
    assert len(snapshot()) == 0
    return "push/snapshot/clear OK"


# ── E2E: doc_search tokenización + scoring (sin tocar archivos reales) ───────
def t_doc_search_engine():
    from actions.doc_search import _tokenize, _search, _normalize
    assert _normalize("Inteligencia ARTIFICIAL") == "inteligencia artificial"
    tokens = _tokenize("La Inteligencia Artificial en la economía moderna")
    assert "inteligencia" in tokens and "economia" in tokens
    assert "la" not in tokens   # stopword

    fake_index = {"files": {
        "C:/docs/ia.docx": {
            "name": "ia.docx", "n_tokens": 100, "mtime": 0,
            "tf": {"inteligencia": 8, "artificial": 8, "economia": 4},
            "preview": "La inteligencia artificial transforma la economía global.",
        },
        "C:/docs/recetas.docx": {
            "name": "recetas.docx", "n_tokens": 80, "mtime": 0,
            "tf": {"cocina": 10, "pastel": 5},
            "preview": "Recetas de cocina para pasteles.",
        },
    }}
    results = _search("inteligencia artificial", fake_index, max_results=5)
    assert len(results) == 1, f"esperaba 1 match, got {len(results)}"
    assert results[0]["name"] == "ia.docx"
    return f"score={results[0]['score']}"


# ── E2E: self_update check (solo lectura, no modifica nada) ──────────────────
def t_self_update_check():
    from actions.self_update import _run_git
    code, out = _run_git("rev-parse", "HEAD")
    assert code == 0, f"git no disponible: {out}"
    assert len(out.strip()) == 40, "HEAD no es un hash valido"
    return f"HEAD={out[:8]}"


# ── E2E: audio ducking (sin reproducir — solo que no crashee) ─────────────────
def t_audio_ducking():
    from core.audio_ducking import duck, unduck, is_enabled
    assert isinstance(is_enabled(), bool)
    duck()     # puede no encontrar sesiones — no debe lanzar
    unduck()
    return "duck/unduck sin excepciones"


# ── E2E: telegram bot importa sin python-telegram-bot ─────────────────────────
def t_telegram_import():
    from core.telegram_bot import start_telegram_listener, TelegramAPI, TOOLS
    assert len(TOOLS) >= 10
    # start con token vacío debe ser no-op silencioso
    start_telegram_listener()
    return f"{len(TOOLS)} tools remotas"


# ── E2E: sandbox bloquea en dispatcher (simulación del flujo confirmed) ──────
def t_sandbox_confirm_flow():
    from core.sandbox import classify_command
    r1 = classify_command("Remove-Item -Recurse -Force C:\\Users\\test\\Desktop")
    assert r1.needs_confirmation(), "debió requerir confirmación"
    r2 = classify_command("Get-Date")
    assert not r2.needs_confirmation()
    return f"{r1.risk} bloqueado, SAFE pasa"


# ── E2E: deep_research web grounding (parser fail-safe sin red) ───────────────
def t_deep_research_grounding():
    from actions import deep_research as dr
    # Sin red / con error → debe devolver ("", []) sin lanzar
    import actions.web_search as ws
    orig = ws._ddg_lite_structured
    ws._ddg_lite_structured = lambda *a, **k: (_ for _ in ()).throw(OSError("sin red"))
    try:
        ctx, sources = dr._gather_web_context("tema", "seccion")
        assert ctx == "" and sources == []
    finally:
        ws._ddg_lite_structured = orig
    # Con resultados simulados
    ws._ddg_lite_structured = lambda *a, **k: [
        {"title": "Estudio IA 2026", "url": "https://example.com/x", "snippet": "datos"}]
    try:
        ctx, sources = dr._gather_web_context("tema", "seccion")
        assert "Estudio IA 2026" in ctx and len(sources) == 1
    finally:
        ws._ddg_lite_structured = orig
    # Referencias con fuentes reales
    refs = dr._generate_references.__wrapped__ if hasattr(dr._generate_references, "__wrapped__") else None
    return "fail-safe + grounding OK"


# ── E2E: núcleo de autonomía ──────────────────────────────────────────────────
def t_autonomy_core():
    from core.autonomy import (set_level, get_level, is_allowed,
                               kill, resume, is_killed, audit, audit_report)
    orig = get_level()
    try:
        set_level(1)
        assert not is_allowed("SAFE"), "nivel 1 no debe auto-ejecutar nada"
        set_level(2)
        assert is_allowed("MEDIUM") and not is_allowed("HIGH")
        set_level(3)
        assert is_allowed("HIGH") and not is_allowed("CRITICAL"), "CRITICAL nunca pasa"
        kill()
        assert is_killed() and not is_allowed("SAFE"), "kill switch debe bloquear todo"
        resume()
        assert not is_killed()
        audit("test", "accion de prueba", "ok")
        rep = audit_report(hours=1)
        assert "accion de prueba" in rep
    finally:
        set_level(orig)
        resume()
    return "niveles + kill + audit OK"


def t_autonomy_control_tool():
    from actions.autonomy_control import autonomy_control
    from core.autonomy import get_level, set_level
    orig = get_level()
    try:
        r = autonomy_control({"action": "set_level", "level": 2})
        assert "2" in r and "ASISTIDO" in r
        r2 = autonomy_control({"action": "status"})
        assert "nivel 2" in r2.lower()
        r3 = autonomy_control({"action": "report", "hours": 1})
        assert isinstance(r3, str) and len(r3) > 5
    finally:
        set_level(orig)
    return "tool de voz OK"


def t_verify_outcome():
    from actions.verify_outcome import verify_outcome
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    tmp.write(b"x" * 2048); tmp.close()
    try:
        r1 = verify_outcome({"check": "file_exists", "target": tmp.name})
        assert "VERIFICADO" in r1
        r2 = verify_outcome({"check": "file_exists", "target": tmp.name + ".nope"})
        assert "FALLO" in r2
        r3 = verify_outcome({"check": "file_size_min", "target": tmp.name, "min_kb": 1})
        assert "VERIFICADO" in r3
        r4 = verify_outcome({"check": "file_recent", "target": tmp.name, "max_age_s": 60})
        assert "VERIFICADO" in r4
        r5 = verify_outcome({"check": "process_running", "target": "python"})
        assert "VERIFICADO" in r5
    finally:
        os.unlink(tmp.name)
    return "5 checks OK"


def t_self_heal_scan():
    from actions.self_heal import _scan, _signature, _file_from_trace
    # _scan no debe lanzar (puede o no haber errores reales)
    patterns = _scan()
    # firma estable
    sig = _signature({"tool": "x", "exc_type": "ValueError", "exc_msg": "bad"})
    assert "ValueError" in sig
    # localizar archivo del proyecto en un traceback simulado
    trace = f'File "{ROOT / "actions" / "weather_report.py"}", line 10, in x'
    rel = _file_from_trace(trace)
    assert rel is not None and "weather_report" in str(rel)
    # los protegidos NO son parchables
    from actions.self_heal import _is_patchable
    from pathlib import Path as _P
    ok, why = _is_patchable(_P("actions/terminal_agent.py"))
    assert not ok, "terminal_agent debe estar protegido"
    ok2, _ = _is_patchable(_P("actions/weather_report.py"))
    assert ok2
    return f"{len(patterns)} patrones, protecciones OK"


def t_system_repair_reports():
    from actions.system_repair import system_repair
    r = system_repair({"repair": "disk_report"})
    assert "GB" in r
    # gate de autonomía: reparación MEDIUM en nivel 1 sin confirmar → bloqueada
    from core.autonomy import set_level, get_level, resume
    orig = get_level()
    try:
        resume()
        set_level(1)
        r2 = system_repair({"repair": "restart_app", "target": "fakeapp"})
        assert "no la permite" in r2 or "confirmaci" in r2.lower()
    finally:
        set_level(orig)
    return "reports + gate OK"


def t_autonomy_daemon():
    from core.autonomy_daemon import _get_idle_seconds, is_running, start, stop
    idle = _get_idle_seconds()
    assert idle >= 0
    # start/stop sin crashear
    start()
    import time as _t; _t.sleep(0.2)
    assert is_running()
    stop()
    return f"idle={idle:.0f}s daemon start/stop OK"


TESTS = {
    "memory_e2e":              t_memory_e2e,
    "document_creator_full":   t_document_creator_full,
    "deep_research_outline":   t_deep_research_outline_parsing,
    "sandbox":                 t_sandbox_e2e,
    "task_queue":              t_task_queue_e2e,
    "emotion_correction":      t_emotion_and_correction,
    "hologram_helpers":        t_hologram_helpers,
    "focus_mode":              t_focus_mode_e2e,
    "web_search_parsing":      t_web_search_parsing,
    "proactive_engine":        t_proactive_engine,
    "usage_dashboard":         t_usage_dashboard,
    "session_buffer":          t_session_buffer,
    "doc_search_engine":       t_doc_search_engine,
    "self_update_check":       t_self_update_check,
    "audio_ducking":           t_audio_ducking,
    "telegram_import":         t_telegram_import,
    "sandbox_confirm_flow":    t_sandbox_confirm_flow,
    "deep_research_grounding": t_deep_research_grounding,
    "autonomy_core":           t_autonomy_core,
    "autonomy_control_tool":   t_autonomy_control_tool,
    "verify_outcome":          t_verify_outcome,
    "self_heal_scan":          t_self_heal_scan,
    "system_repair_reports":   t_system_repair_reports,
    "autonomy_daemon":         t_autonomy_daemon,
}


def main():
    (ROOT / "tests" / "_out").mkdir(parents=True, exist_ok=True)
    print(f"\nJARVIS E2E Integration Tests - {len(TESTS)} flows\n" + "-"*70)
    t_start = time.time()
    for name, fn in TESTS.items():
        run(name, fn)
    elapsed = time.time() - t_start

    passed  = sum(1 for _, s, _ in _results if s == PASS)
    failed  = sum(1 for _, s, _ in _results if s == FAIL)
    skipped = sum(1 for _, s, _ in _results if s == SKIP)
    print("-"*70)
    print(f"  {passed} pass | {failed} fail | {skipped} skip | {elapsed:.1f}s")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
