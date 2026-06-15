"""
web_search.py — Búsqueda web real usando DuckDuckGo (sin API key necesaria).
Estrategia:
  1. DuckDuckGo Instant Answers API → respuestas directas y abstractos
  2. DuckDuckGo Lite HTML → resultados de búsqueda reales (scraping ligero)
  3. Fallback → abrir el navegador con la búsqueda
"""
import json
import re
import webbrowser
import urllib.request
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _ddg_instant(query: str) -> str:
    """DuckDuckGo Instant Answers API — respuestas factuales directas."""
    url = (
        "https://api.duckduckgo.com/?q="
        + urllib.parse.quote(query)
        + "&format=json&no_html=1&skip_disambig=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JARVIS/2.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    parts = []

    # Respuesta directa (matemáticas, conversiones, etc.)
    if data.get("Answer"):
        parts.append(f"Respuesta directa: {data['Answer']}")

    # Resumen de Wikipedia / fuente authoritative
    if data.get("Abstract"):
        source = data.get("AbstractSource", "")
        url_src = data.get("AbstractURL", "")
        parts.append(
            f"{data['Abstract']}"
            + (f"\n(Fuente: {source} — {url_src})" if source else "")
        )

    # Temas relacionados
    if not parts and data.get("RelatedTopics"):
        topics = []
        for t in data["RelatedTopics"][:5]:
            if isinstance(t, dict) and t.get("Text"):
                topics.append(t["Text"])
            elif isinstance(t, dict) and t.get("Topics"):
                for sub in t["Topics"][:2]:
                    if isinstance(sub, dict) and sub.get("Text"):
                        topics.append(sub["Text"])
        if topics:
            parts.append("Resultados relacionados:\n" + "\n".join(f"• {t}" for t in topics[:5]))

    return "\n\n".join(parts) if parts else ""


def _ddg_lite_structured(query: str, max_results: int = 5) -> list[dict]:
    """
    Raspa DuckDuckGo Lite y devuelve [{title, url, snippet}] estructurado.
    No requiere API key ni JavaScript.
    """
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    # Match conjunto: capturar URL real + título en un solo regex
    # DDG Lite envuelve cada resultado así:
    #   <a rel="nofollow" href="//duckduckgo.com/l/?uddg=URL_ENCODED" class='result-link'>Title</a>
    # O bien con href directo:
    #   <a class='result-link' href="https://...">Title</a>
    pattern = re.compile(
        r"<a[^>]+(?:href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"]|"
        r"class=['\"]result-link['\"][^>]*href=['\"]([^'\"]+)['\"])[^>]*>([^<]+)</a>",
        re.IGNORECASE,
    )
    snippet_pattern = re.compile(r"class=['\"]result-snippet['\"]>(.*?)</td>", re.S)

    def strip_tags(s):
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"&amp;", "&", s)
        s = re.sub(r"&quot;", '"', s)
        s = re.sub(r"&#x27;", "'", s)
        s = re.sub(r"&lt;", "<", s)
        s = re.sub(r"&gt;", ">", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    def resolve_url(raw_url: str) -> str:
        """Si DDG envolvió la URL en su redirector, extraer la URL real."""
        if not raw_url:
            return ""
        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url
        if "duckduckgo.com/l/" in raw_url:
            m = re.search(r"uddg=([^&]+)", raw_url)
            if m:
                try:
                    return urllib.parse.unquote(m.group(1))
                except Exception:
                    return raw_url
        return raw_url

    matches    = pattern.findall(html)
    snippets   = [strip_tags(s) for s in snippet_pattern.findall(html)]

    results = []
    for i, m in enumerate(matches[:max_results]):
        href = m[0] or m[1]
        title = strip_tags(m[2])
        if not title:
            continue
        snippet = snippets[i] if i < len(snippets) else ""
        results.append({
            "title":   title,
            "url":     resolve_url(href),
            "snippet": snippet,
        })
    return results


def _ddg_lite(query: str, max_results: int = 5) -> str:
    """Versión texto plana — para retro-compatibilidad y voz."""
    results = _ddg_lite_structured(query, max_results)
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   🔗 {r['url']}")
    return "\n".join(lines)


def web_search(parameters: dict, player=None) -> str:
    """
    Búsqueda web real con DuckDuckGo.
    Devuelve resultados concretos que JARVIS puede leer en voz alta.
    """
    query   = parameters.get("query", "").strip()
    mode    = parameters.get("mode", "search").lower()   # search | compare | news
    open_browser = parameters.get("open_browser", False)
    with_citations = parameters.get("with_citations", False)
    max_results = int(parameters.get("max_results", 5))

    if not query:
        return "Error: Falta el parámetro 'query'."

    if player:
        try: player.write_log(f"🔍 Buscando: '{query}'...")
        except Exception: pass

    # ── Modo comparación ──────────────────────────────────────────────────────
    if mode == "compare":
        items  = parameters.get("items", [])
        aspect = parameters.get("aspect", "")
        if items:
            query = f"comparar {' vs '.join(items)}" + (f" {aspect}" if aspect else "")

    results_text = ""

    # ── Intento 1: Instant Answers (factual / rápido) ────────────────────────
    try:
        results_text = _ddg_instant(query)
    except Exception as e:
        if player:
            try: player.write_log(f"⚠️ DDG Instant falló: {e} — intentando Lite...")
            except Exception: pass

    # ── Intento 2: Lite scraping con citas estructuradas ─────────────────────
    if not results_text or with_citations:
        try:
            structured = _ddg_lite_structured(query, max_results=max_results)
            if with_citations and structured:
                # Devolver formato con URLs claramente identificables
                lines = [f"Resultados con fuentes para '{query}':\n"]
                for i, r in enumerate(structured, 1):
                    lines.append(f"[{i}] {r['title']}")
                    if r.get("snippet"):
                        lines.append(f"    {r['snippet']}")
                    if r.get("url"):
                        lines.append(f"    Fuente: {r['url']}")
                    lines.append("")
                results_text = "\n".join(lines)
            elif not results_text:
                results_text = _ddg_lite(query, max_results=max_results)
        except Exception as e:
            if player:
                try: player.write_log(f"⚠️ DDG Lite falló: {e} — abriendo navegador...")
                except Exception: pass

    # ── Fallback: abrir navegador ────────────────────────────────────────────
    if not results_text:
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
        return f"No pude obtener resultados automáticamente. Abrí Google para: '{query}'."

    if open_browser:
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))

    final = f"Resultados de búsqueda para '{query}':\n\n{results_text}"
    if player:
        try: player.write_log(f"✅ Búsqueda completada ({len(results_text)} chars)")
        except Exception: pass
    return final
