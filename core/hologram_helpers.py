"""
core/hologram_helpers.py — Genera HTML listo para `show_hologram` según el contexto.

Cuando JARVIS produce un resultado, en lugar de solo hablarlo, en algunos casos
vale mucho más mostrarlo visualmente:
  • Datos numéricos → mini gráfico de barras o tabla
  • Ubicación → mapa estático
  • Documento creado → vista previa
  • Lista de tareas → checklist
  • Código → bloque syntax-highlighted

Estas funciones generan HTML standalone que se inyecta directo al WebView del UI.
Estilo dorado coherente con el resto del UI.
"""
from __future__ import annotations
import html as _html
import json
import re
import urllib.parse
from typing import Any


# Paleta dorada coherente con el resto del UI
_BG       = "rgba(8, 8, 12, 0.92)"
_GOLD     = "#D4AF37"
_GOLD_DIM = "#8a7220"
_TEXT     = "#F2E6BD"
_TEXT_DIM = "#7e7350"
_CSS_BASE = f"""
<style>
  body, html {{
    margin: 0; padding: 0;
    background: transparent;
    color: {_TEXT};
    font-family: 'Consolas','Courier New',monospace;
    font-size: 13px;
    overflow: hidden;
  }}
  .card {{
    background: {_BG};
    border: 1px solid {_GOLD_DIM};
    border-radius: 10px;
    padding: 16px 20px;
    margin: 8px;
    box-shadow: 0 0 30px rgba(212,175,55,0.15);
  }}
  .title {{
    color: {_GOLD};
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1px solid {_GOLD_DIM};
    padding-bottom: 4px;
  }}
  .bar-row {{ display: flex; align-items: center; margin: 4px 0; }}
  .bar-label {{ width: 120px; color: {_TEXT}; }}
  .bar-track {{ flex: 1; height: 14px; background: rgba(212,175,55,0.08); border-radius: 2px; position: relative; }}
  .bar-fill  {{ height: 100%; background: linear-gradient(90deg, {_GOLD_DIM}, {_GOLD}); border-radius: 2px; }}
  .bar-value {{ width: 60px; text-align: right; color: {_GOLD}; padding-left: 8px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; color: {_GOLD}; border-bottom: 1px solid {_GOLD_DIM}; padding: 4px 8px; }}
  td {{ padding: 4px 8px; border-bottom: 1px dotted rgba(212,175,55,0.15); }}
  ul.checklist {{ list-style: none; padding: 0; margin: 0; }}
  ul.checklist li {{ padding: 3px 0; }}
  ul.checklist li.done {{ color: {_TEXT_DIM}; text-decoration: line-through; }}
  ul.checklist li.pending::before {{ content: "◯ "; color: {_GOLD}; }}
  ul.checklist li.done::before    {{ content: "✓ "; color: {_GOLD_DIM}; }}
  .stat {{ display: inline-block; margin: 4px 12px; }}
  .stat-big {{ font-size: 22px; color: {_GOLD}; font-weight: bold; display: block; }}
  .stat-label {{ color: {_TEXT_DIM}; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }}
  code, pre {{ font-family: 'Consolas','Fira Code',monospace; }}
  pre.code {{
    background: rgba(0,0,0,0.4);
    border-left: 3px solid {_GOLD_DIM};
    padding: 8px 12px;
    margin: 8px 0;
    overflow-x: auto;
    color: {_TEXT};
  }}
  .doc-preview {{ background: #f8f6e8; color: #222; padding: 16px; min-height: 160px; }}
  .doc-preview h1 {{ color: #1f4978; margin: 0 0 8px; }}
  .doc-preview h2 {{ color: #2e74b5; margin: 6px 0 4px; font-size: 14px; }}
  .map-frame {{ width: 100%; min-height: 200px; border: none; }}
</style>
"""


def chart_bar(title: str, items: list[tuple[str, float]],
              unit: str = "", max_value: float | None = None) -> str:
    """Mini barchart: items = [(label, value), ...]"""
    if not items:
        return ""
    mv = max_value or max(v for _, v in items) or 1.0
    rows = []
    for label, val in items:
        pct = max(2, min(100, (val / mv) * 100))
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{_html.escape(str(label))}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<span class="bar-value">{val:g}{_html.escape(unit)}</span>'
            f'</div>'
        )
    body = "".join(rows)
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">{_html.escape(title)}</div>
  {body}
</div>"""


def stats_panel(title: str, stats: list[tuple[str, str]]) -> str:
    """Panel de stats grandes: stats = [(label, value), ...]"""
    parts = []
    for lbl, val in stats:
        parts.append(
            f'<div class="stat"><span class="stat-big">{_html.escape(str(val))}</span>'
            f'<span class="stat-label">{_html.escape(str(lbl))}</span></div>'
        )
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">{_html.escape(title)}</div>
  {''.join(parts)}
</div>"""


def checklist(title: str, items: list[tuple[str, bool]]) -> str:
    """Lista de checks: items = [(texto, completado_bool), ...]"""
    lis = "".join(
        f'<li class="{"done" if done else "pending"}">{_html.escape(txt)}</li>'
        for txt, done in items
    )
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">{_html.escape(title)}</div>
  <ul class="checklist">{lis}</ul>
</div>"""


def table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    """Tabla simple."""
    th = "".join(f"<th>{_html.escape(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        tds = "".join(f"<td>{_html.escape(str(c))}</td>" for c in r)
        body += f"<tr>{tds}</tr>"
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">{_html.escape(title)}</div>
  <table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>
</div>"""


def code_block(title: str, language: str, code: str) -> str:
    """Bloque de código (sin syntax highlighting real — solo monoespaciado)."""
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">{_html.escape(title)} <span style="color:{_TEXT_DIM};font-size:10px">[{_html.escape(language)}]</span></div>
  <pre class="code">{_html.escape(code)}</pre>
</div>"""


def document_preview(title: str, headings: list[str], snippet: str = "") -> str:
    """Vista previa de un documento generado (mostrar tras document_creator)."""
    h_html = "".join(f"<h2>{_html.escape(h)}</h2>" for h in headings[:8])
    snip = _html.escape(snippet[:280]) if snippet else ""
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">📄 Documento generado</div>
  <div class="doc-preview">
    <h1>{_html.escape(title)}</h1>
    {h_html}
    <p>{snip}</p>
  </div>
</div>"""


def map_view(query: str) -> str:
    """Mapa estático centrado en `query`. Usa OpenStreetMap (sin API key)."""
    safe = urllib.parse.quote_plus(query)
    # Embed OSM como iframe
    return f"""{_CSS_BASE}<div class="card">
  <div class="title">🗺️ {_html.escape(query)}</div>
  <iframe class="map-frame"
    src="https://www.openstreetmap.org/export/embed.html?bbox=-180%2C-85%2C180%2C85&amp;layer=mapnik&amp;marker={safe}"
    sandbox="allow-scripts allow-same-origin"></iframe>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
#  DETECCIÓN AUTOMÁTICA — análisis del resultado de una herramienta
# ══════════════════════════════════════════════════════════════════════════════

def auto_hologram_from_tool_result(tool_name: str, result: Any,
                                   args: dict | None = None) -> str | None:
    """
    Analiza el resultado de una herramienta y devuelve HTML de holograma
    si tiene sentido mostrarlo. None si no aplica.

    Esto NO se llama automáticamente — el flujo en main.py decide cuándo
    invocarlo (típicamente tras herramientas que producen datos visualizables).
    """
    if result is None:
        return None
    result_str = str(result)

    # ── weather_report → stats panel ─────────────────────────────────────────
    if tool_name == "weather_report":
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*°", result_str)
        temp = m.group(1) + "°" if m else "—"
        humidity_m = re.search(r"humedad[:\s]+(\d+)%", result_str, re.IGNORECASE)
        wind_m     = re.search(r"viento[:\s]+([\d.]+)\s*km", result_str, re.IGNORECASE)
        stats = [("Temperatura", temp)]
        if humidity_m: stats.append(("Humedad", humidity_m.group(1) + "%"))
        if wind_m:     stats.append(("Viento", wind_m.group(1) + " km/h"))
        if len(stats) >= 2:
            return stats_panel("Estado del clima", stats)

    # ── google_maps / location → map view ────────────────────────────────────
    if tool_name == "google_maps":
        q = (args or {}).get("query") or (args or {}).get("destination") or ""
        if q:
            return map_view(q)

    # ── system_diagnostics / task_status → tabla simple ──────────────────────
    if tool_name in ("system_diagnostics", "task_status"):
        lines = [l for l in result_str.split("\n") if l.strip()]
        if len(lines) >= 2:
            rows = []
            for l in lines:
                if ":" in l:
                    k, v = l.split(":", 1)
                    rows.append([k.strip().rstrip("·"), v.strip()])
            if rows:
                return table("Estado del sistema", ["Métrica", "Valor"], rows)

    # ── document_creator → preview ───────────────────────────────────────────
    if tool_name == "document_creator":
        m = re.search(r"'([^']+\.docx)'", result_str)
        if m:
            fname = m.group(1)
            args = args or {}
            content = (args.get("content") or "")
            # Extraer headings (## o # del markdown)
            headings = re.findall(r"^#{1,3}\s+(.+)$", content, re.MULTILINE)
            snippet = re.sub(r"^[#\[].*$", "", content, flags=re.MULTILINE).strip()[:280]
            title = args.get("title") or fname.rsplit("_", 2)[0].replace("_", " ")
            return document_preview(title, headings[:8], snippet)

    # ── deep_research progreso → mostrar plan en activity panel ──────────────
    if tool_name == "deep_research":
        return None  # esto ya se ve en el activity_panel

    # ── web_search con citas → tabla de fuentes ──────────────────────────────
    if tool_name == "web_search":
        # Heurística: detectar URLs en el resultado
        urls = re.findall(r"https?://[^\s)\]]+", result_str)
        if len(urls) >= 2:
            rows = [[i+1, u[:60] + ("..." if len(u) > 60 else "")] for i, u in enumerate(urls[:6])]
            return table("Fuentes consultadas", ["#", "URL"], rows)

    return None
