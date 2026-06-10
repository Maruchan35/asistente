"""
core/usage_dashboard.py — Dashboard de uso de JARVIS.

Lee los logs JSONL de `logs/` y produce un resumen accionable:
  • Top 10 herramientas más usadas
  • Errores más frecuentes (agrupados por tipo)
  • Latencia promedio por herramienta (P50, P95)
  • Estado de cuotas
  • Memoria persistente (turnos, hechos)

Dos modos:
  • Texto plano (devolver a JARVIS para que lo lea en voz)
  • HTML (mostrar en hologram_view en el UI)
"""
from __future__ import annotations
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_LOGS = _BASE / "logs"


def _load_jsonl(path: Path) -> list[dict]:
    entries = []
    if not path.exists():
        return entries
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return entries


def collect_stats() -> dict:
    """Recolecta todas las estadísticas y devuelve dict."""
    tools     = _load_jsonl(_LOGS / "tools.jsonl")
    errors    = _load_jsonl(_LOGS / "errors.jsonl")
    sessions  = _load_jsonl(_LOGS / "sessions.jsonl")
    quotas    = _load_jsonl(_LOGS / "quota.jsonl")

    # ── Top herramientas ─────────────────────────────────────────────────────
    tool_counter: Counter[str] = Counter()
    tool_durations: defaultdict[str, list[int]] = defaultdict(list)
    for e in tools:
        if e.get("result") == "[started]":  # skip los "started"
            continue
        tname = e.get("tool")
        if not tname:
            continue
        tool_counter[tname] += 1
        dur = e.get("dur_ms")
        if isinstance(dur, (int, float)):
            tool_durations[tname].append(int(dur))

    # ── Errores ──────────────────────────────────────────────────────────────
    err_counter: Counter[str] = Counter()
    for e in errors:
        et = e.get("exc_type", "Unknown")
        em = (e.get("exc_msg") or "")[:60]
        key = f"{et}: {em}" if em else et
        err_counter[key] += 1

    # ── Sesiones ─────────────────────────────────────────────────────────────
    sess_events: Counter[str] = Counter()
    for e in sessions:
        sess_events[e.get("event", "unknown")] += 1

    # ── Memoria ──────────────────────────────────────────────────────────────
    try:
        from memory.memory_engine import get_stats as memstats
        mem = memstats()
    except Exception:
        mem = {}

    # ── Quota ────────────────────────────────────────────────────────────────
    try:
        from core.quota_manager import get_status as qstatus
        quota_state = qstatus()
    except Exception:
        quota_state = {}

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "top_tools": tool_counter.most_common(10),
        "tool_latency_p50": {
            t: int(statistics.median(d)) for t, d in tool_durations.items()
        },
        "tool_latency_p95": {
            t: int(sorted(d)[int(len(d)*0.95)]) if len(d) >= 5 else None
            for t, d in tool_durations.items()
        },
        "top_errors":  err_counter.most_common(8),
        "sessions":    dict(sess_events),
        "memory":      mem,
        "quota_state": quota_state,
        "totals": {
            "tool_calls":     sum(tool_counter.values()),
            "errors":         sum(err_counter.values()),
            "unique_tools":   len(tool_counter),
        },
    }


def format_text(stats: dict | None = None) -> str:
    """Resumen en texto plano."""
    stats = stats or collect_stats()
    lines = []
    lines.append(f"=== JARVIS Dashboard ({stats['generated_at']}) ===\n")

    t = stats["totals"]
    lines.append(f"Total: {t['tool_calls']} llamadas, "
                 f"{t['unique_tools']} herramientas distintas, "
                 f"{t['errors']} errores\n")

    lines.append("TOP HERRAMIENTAS:")
    for tool, n in stats["top_tools"]:
        p50 = stats["tool_latency_p50"].get(tool, 0)
        lines.append(f"  {n:>4}× {tool:<25} (p50={p50}ms)")

    if stats["top_errors"]:
        lines.append("\nERRORES FRECUENTES:")
        for err, n in stats["top_errors"]:
            lines.append(f"  {n:>4}× {err}")

    if stats["memory"]:
        m = stats["memory"]
        lines.append(f"\nMEMORIA: {m.get('long_term_entries',0)} hechos · "
                     f"{m.get('total_turns_logged',0)} turnos · "
                     f"{m.get('session_days',0)} días")

    if stats["quota_state"]:
        lines.append("\nPROVEEDORES:")
        for p, s in stats["quota_state"].items():
            st = s.get("status", "?")
            lines.append(f"  {p}: {st}")

    return "\n".join(lines)


def format_html(stats: dict | None = None) -> str:
    """Vista HTML (para hologram_view)."""
    stats = stats or collect_stats()
    from core.hologram_helpers import _CSS_BASE, _GOLD, _GOLD_DIM, _TEXT, _TEXT_DIM

    top_tools_rows = "".join(
        f"<tr><td>{tool}</td><td style='text-align:right'>{n}</td>"
        f"<td style='text-align:right;color:{_TEXT_DIM}'>"
        f"{stats['tool_latency_p50'].get(tool,0)}ms</td></tr>"
        for tool, n in stats["top_tools"]
    )

    err_rows = "".join(
        f"<tr><td>{n}</td><td>{e[:80]}</td></tr>"
        for e, n in stats["top_errors"]
    )

    m = stats.get("memory", {})
    t = stats["totals"]

    html = f"""{_CSS_BASE}
<div class="card">
  <div class="title">◈ JARVIS Dashboard</div>
  <div style="margin:8px 0">
    <span class="stat"><span class="stat-big">{t['tool_calls']}</span><span class="stat-label">llamadas</span></span>
    <span class="stat"><span class="stat-big">{t['unique_tools']}</span><span class="stat-label">herramientas</span></span>
    <span class="stat"><span class="stat-big" style="color:{'#e07070' if t['errors']>0 else _GOLD}">{t['errors']}</span><span class="stat-label">errores</span></span>
    <span class="stat"><span class="stat-big">{m.get('long_term_entries',0)}</span><span class="stat-label">hechos</span></span>
  </div>
</div>

<div class="card">
  <div class="title">Top Herramientas</div>
  <table>
    <thead><tr><th>Herramienta</th><th style="text-align:right">Uso</th><th style="text-align:right">P50</th></tr></thead>
    <tbody>{top_tools_rows or '<tr><td colspan="3">Sin datos aún</td></tr>'}</tbody>
  </table>
</div>
"""
    if err_rows:
        html += f"""
<div class="card">
  <div class="title">Errores frecuentes</div>
  <table>
    <thead><tr><th style="width:40px">#</th><th>Error</th></tr></thead>
    <tbody>{err_rows}</tbody>
  </table>
</div>"""

    return html


def usage_dashboard(parameters: dict, player=None) -> str:
    """Entry point para Gemini. action: 'text' (default) | 'html'."""
    action = (parameters.get("action") or "text").lower()
    stats = collect_stats()
    if action == "html":
        return format_html(stats)
    return format_text(stats)
