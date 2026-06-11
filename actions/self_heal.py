# -*- coding: utf-8 -*-
"""
self_heal.py — Auto-reparación de JARVIS.

Flujo seguro de 3 pasos:
  scan     → leer logs/errors.jsonl, agrupar por firma (tool+tipo de excepción),
             reportar las fallas repetidas (3+ en 24h)
  diagnose → para una firma: leer el traceback + el código fuente afectado,
             pedir diagnóstico y parche a DeepSeek-R1
  fix      → aplicar el parche CON RED DE SEGURIDAD:
               1. backup del archivo a backups/
               2. escribir el archivo parchado
               3. correr tests/smoke_tools.py
               4. tests verdes → conservar; tests rojos → ROLLBACK automático

LÍMITES DUROS (no negociables):
  • Solo puede tocar archivos dentro de actions/ y core/
  • NUNCA: actions/terminal_agent.py, actions/self_edit.py, actions/self_heal.py,
    main.py, core/sandbox.py, core/autonomy.py
  • El fix automático (sin orden directa) requiere nivel de autonomía 3
  • Toda acción queda en la auditoría
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

_BASE   = Path(__file__).resolve().parent.parent
_ERRORS = _BASE / "logs" / "errors.jsonl"
_BACKUPS = _BASE / "backups"

# Archivos que JAMÁS se auto-parchan
_FORBIDDEN = {
    "actions/terminal_agent.py", "actions/self_edit.py", "actions/self_heal.py",
    "main.py", "core/sandbox.py", "core/autonomy.py", "core/safe_json.py",
}
_ALLOWED_DIRS = ("actions", "core")

_MIN_REPEATS = 3      # fallas mínimas para considerar patrón
_WINDOW_H    = 24     # ventana de análisis


def _read_recent_errors(hours: int = _WINDOW_H) -> list[dict]:
    if not _ERRORS.exists():
        return []
    cutoff = time.time() - hours * 3600
    out = []
    with open(_ERRORS, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e.get("ts", "1970-01-01")).timestamp()
                if ts >= cutoff:
                    out.append(e)
            except Exception:
                pass
    return out


def _signature(e: dict) -> str:
    """Firma estable de un error: tool/categoría + tipo de excepción + 1a línea del msg."""
    tool = e.get("tool") or e.get("msg", "")[:40]
    return f"{tool} | {e.get('exc_type','?')} | {str(e.get('exc_msg',''))[:60]}"


def _scan() -> list[tuple[str, int, dict]]:
    """Devuelve [(firma, conteo, ejemplo_mas_reciente)] de fallas repetidas."""
    errors = _read_recent_errors()
    counter: Counter[str] = Counter()
    latest: dict[str, dict] = {}
    for e in errors:
        sig = _signature(e)
        counter[sig] += 1
        latest[sig] = e
    return [(sig, n, latest[sig]) for sig, n in counter.most_common()
            if n >= _MIN_REPEATS]


def _file_from_trace(trace: str) -> Path | None:
    """Extraer el archivo del proyecto más profundo del traceback."""
    candidates = re.findall(r'File "([^"]+\.py)", line \d+', trace or "")
    project_files = []
    for c in candidates:
        p = Path(c)
        try:
            rel = p.resolve().relative_to(_BASE.resolve())
            project_files.append(rel)
        except ValueError:
            continue
    # El último frame del proyecto es normalmente donde está el bug
    return project_files[-1] if project_files else None


def _is_patchable(rel_path: Path) -> tuple[bool, str]:
    rel_str = str(rel_path).replace("\\", "/")
    if rel_str in _FORBIDDEN:
        return False, f"{rel_str} es un archivo protegido — no se auto-parcha."
    if not rel_str.split("/")[0] in _ALLOWED_DIRS:
        return False, f"{rel_str} está fuera de actions/ y core/."
    if not (_BASE / rel_path).exists():
        return False, f"{rel_str} no existe."
    return True, ""


def _llm(prompt: str, system: str, max_tokens: int = 4000) -> str:
    from actions.deep_research import _llm_call
    return _llm_call(prompt, max_tokens=max_tokens, system=system)


def _diagnose(sig: str, example: dict) -> dict:
    """Diagnóstico + parche propuesto. Devuelve dict con file, diagnosis, patched_code."""
    trace = example.get("trace", "")
    rel = _file_from_trace(trace)
    if rel is None:
        return {"ok": False, "reason": "No se pudo localizar el archivo del error en el traceback."}
    ok, why = _is_patchable(rel)
    if not ok:
        return {"ok": False, "reason": why}

    source = (_BASE / rel).read_text(encoding="utf-8", errors="ignore")
    if len(source) > 60_000:
        return {"ok": False, "reason": f"{rel} demasiado grande para parche automático."}

    system = (
        "Eres un ingeniero de software senior reparando un bug en producción. "
        "Devuelves SOLO un JSON válido, sin markdown, con esta forma exacta:\n"
        '{"diagnosis": "explicación de 1-3 frases", '
        '"confidence": 0.0-1.0, '
        '"patched_file": "EL ARCHIVO COMPLETO corregido"}\n'
        "El patched_file debe ser el archivo ENTERO (no un diff), con el mínimo "
        "cambio necesario para arreglar el bug. Si no estás seguro de la causa, "
        "devuelve confidence < 0.5 y patched_file vacío."
    )
    prompt = (
        f"ERROR REPETIDO ({sig}):\n{example.get('exc_type')}: {example.get('exc_msg')}\n\n"
        f"TRACEBACK:\n{trace[:3000]}\n\n"
        f"ARCHIVO ({rel}):\n```python\n{source}\n```\n\n"
        "Diagnostica y devuelve el JSON con el archivo corregido."
    )
    raw = _llm(prompt, system)
    # Parsear el JSON (tolerar fences)
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except Exception:
        return {"ok": False, "reason": "El LLM no devolvió JSON parseable."}

    conf = float(data.get("confidence", 0))
    patched = data.get("patched_file", "")
    if conf < 0.6 or not patched.strip():
        return {"ok": False,
                "reason": f"Confianza insuficiente ({conf:.0%}). Diagnóstico: {data.get('diagnosis','')}"}

    # Validar que el parche al menos parsea
    import ast as _ast
    try:
        _ast.parse(patched)
    except SyntaxError as se:
        return {"ok": False, "reason": f"El parche tiene error de sintaxis: {se}"}

    return {"ok": True, "file": str(rel), "diagnosis": data.get("diagnosis", ""),
            "confidence": conf, "patched_code": patched}


def _run_smoke_tests() -> tuple[bool, str]:
    venv_py = _BASE / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    try:
        p = subprocess.run(
            [py, str(_BASE / "tests" / "smoke_tools.py")],
            capture_output=True, text=True, timeout=180, cwd=str(_BASE),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        tail = (p.stdout or "")[-300:]
        return p.returncode == 0, tail
    except Exception as e:
        return False, str(e)


def _apply_fix(diag: dict) -> str:
    """Backup → parche → tests → conservar o rollback."""
    from core.autonomy import audit
    rel = Path(diag["file"])
    full = _BASE / rel

    # 1. Backup
    _BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = _BACKUPS / f"{rel.name}.{stamp}.bak"
    shutil.copy2(full, backup)

    # 2. Parche
    original = full.read_text(encoding="utf-8", errors="ignore")
    full.write_text(diag["patched_code"], encoding="utf-8")

    # 3. Tests
    ok, test_out = _run_smoke_tests()
    if ok:
        audit("self_heal_fix", f"Parche aplicado a {rel}: {diag['diagnosis'][:120]}",
              "tests verdes — conservado", backup=str(backup))
        return (f"REPARADO: {rel} — {diag['diagnosis']} "
                f"(confianza {diag['confidence']:.0%}). Tests: PASS. "
                f"Backup en {backup.name}. Reinicie JARVIS para aplicar.")
    # 4. Rollback
    full.write_text(original, encoding="utf-8")
    audit("self_heal_fix", f"Parche a {rel} REVERTIDO — tests fallaron",
          test_out[:150], backup=str(backup))
    return (f"El parche a {rel} se aplicó pero los tests FALLARON — "
            f"hice ROLLBACK automático, nada cambió. Salida: {test_out[:200]}")


def self_heal(parameters: dict, player=None) -> str:
    """Entry point. action: scan (default) | diagnose | fix"""
    from core.autonomy import get_level, is_killed, audit

    action = (parameters.get("action") or "scan").lower()
    if is_killed():
        return "Sistema de autonomía detenido por kill switch — no se ejecutan reparaciones."

    def _log(m):
        if player:
            try: player.write_log(m)
            except Exception: pass

    patterns = _scan()

    if action == "scan":
        if not patterns:
            return "Sin fallas repetidas en las últimas 24 horas. Sistemas estables."
        lines = [f"{len(patterns)} patrón(es) de falla repetida:"]
        for i, (sig, n, _ex) in enumerate(patterns[:5], 1):
            lines.append(f"  {i}. ({n}×) {sig}")
        lines.append("Puede pedirme 'diagnostica la falla N' o 'repárala'.")
        return "\n".join(lines)

    if not patterns:
        return "No hay fallas repetidas que diagnosticar."

    idx = max(1, int(parameters.get("pattern_index", 1))) - 1
    if idx >= len(patterns):
        idx = 0
    sig, n, example = patterns[idx]

    if action == "diagnose":
        _log(f"🩺 Diagnosticando: {sig[:60]}")
        diag = _diagnose(sig, example)
        if not diag.get("ok"):
            return f"Diagnóstico de '{sig[:60]}': {diag.get('reason')}"
        return (f"DIAGNÓSTICO de '{sig[:60]}': {diag['diagnosis']} "
                f"(confianza {diag['confidence']:.0%}, archivo: {diag['file']}). "
                "¿Aplico la reparación, señor? (backup + tests + rollback automático)")

    if action == "fix":
        # Fix sin orden directa requiere nivel 3; con orden directa del usuario
        # (confirmed=true) se permite en cualquier nivel.
        confirmed = parameters.get("confirmed", False)
        if isinstance(confirmed, str):
            confirmed = confirmed.lower() in ("true", "1", "yes", "sí", "si")
        if not confirmed and get_level() < 3:
            return ("La reparación automática requiere nivel de autonomía 3 o su "
                    "confirmación explícita. Diga 'sí, repara' para proceder.")
        _log(f"🔧 Reparando: {sig[:60]}")
        diag = _diagnose(sig, example)
        if not diag.get("ok"):
            return f"No puedo reparar '{sig[:60]}': {diag.get('reason')}"
        return _apply_fix(diag)

    return f"Acción '{action}' no reconocida. Use: scan | diagnose | fix."
