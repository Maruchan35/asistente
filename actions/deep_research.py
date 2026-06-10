# -*- coding: utf-8 -*-
"""
deep_research.py — Generador de investigaciones LARGAS por secciones.

Problema que resuelve: openrouter_agent y deepseek_agent tienen max_tokens=1500
y system prompt "muy concisa", por lo que cualquier petición de "20 páginas"
termina dando 5000 caracteres. Esta herramienta:

  1. Genera un OUTLINE con N secciones según target_pages
  2. Para cada sección, hace una llamada DEDICADA al LLM con max_tokens alto
  3. Concatena todo en markdown estructurado
  4. Llama a document_creator para producir el .docx con portada/TOC/refs
  5. Todo corre en background (task_queue) → no bloquea conversación
  6. Reporta progreso vía task.update_progress

Uso desde Gemini:
    deep_research({
        "topic": "Impacto de la IA en el sector económico",
        "target_pages": 20,
        "norm": "apa7",
        "title": "Investigacion_IA_Economia",
        "cover": "{...}"
    })
    → "Investigación iniciada (tarea abc12345). Le aviso cuando esté lista."

Cuando termina, task_queue.notify_callback inyecta:
    "(Tarea completada: Investigación...)" y JARVIS avisa al usuario.
"""
from __future__ import annotations
import json
import re
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_API  = _BASE / "config" / "api_keys.json"

# Promedios: 1 página de Word con interlineado 1.15 ≈ 400-500 palabras
# Una sección típica: ~800-1500 palabras
_WORDS_PER_PAGE     = 400
_WORDS_PER_SECTION  = 1100
_MIN_SECTIONS       = 5
_MAX_SECTIONS       = 18

_MODELS_FALLBACK = [
    "deepseek/deepseek-chat-v3.1",
    "google/gemini-2.5-flash",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o-mini",
]


# ── Cliente LLM dedicado (max_tokens alto, sin "sé conciso") ──────────────────

def _load_cfg() -> dict:
    try:
        return json.loads(_API.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _llm_call(prompt: str, max_tokens: int = 3500, system: str | None = None,
              attempt: int = 0) -> str:
    """Llamada limpia a OpenRouter sin las restricciones del openrouter_agent."""
    cfg = _load_cfg()
    api_key = cfg.get("openrouter_api_key", "").strip()

    # Fallback a DeepSeek directo si no hay OpenRouter
    if not api_key:
        return _deepseek_direct_call(prompt, max_tokens, system)

    model = cfg.get("openrouter_model", _MODELS_FALLBACK[attempt % len(_MODELS_FALLBACK)])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer":  "https://github.com/jarvis-beta",
        "X-Title":       "JARVIS Deep Research",
        "Content-Type":  "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model":       model,
        "max_tokens":  max_tokens,
        "temperature": 0.5,
        "messages":    messages,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        # Si es rate limit o modelo caído, probar otro
        if attempt < len(_MODELS_FALLBACK) - 1 and e.code in (429, 500, 502, 503):
            time.sleep(1.5)
            return _llm_call(prompt, max_tokens, system, attempt + 1)
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {body[:200]}")
    except Exception as e:
        if attempt < len(_MODELS_FALLBACK) - 1:
            time.sleep(1.5)
            return _llm_call(prompt, max_tokens, system, attempt + 1)
        raise


def _deepseek_direct_call(prompt: str, max_tokens: int = 3500,
                          system: str | None = None) -> str:
    """Fallback directo a DeepSeek si no hay OpenRouter configurado."""
    cfg = _load_cfg()
    api_key = cfg.get("deepseek_api_key", "").strip()
    if not api_key:
        raise RuntimeError("No hay API key de OpenRouter ni DeepSeek configurada.")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model":       "deepseek-chat",
        "max_tokens":  max_tokens,
        "temperature": 0.5,
        "messages":    messages,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


# ── Generador de outline ─────────────────────────────────────────────────────

def _generate_outline(topic: str, target_pages: int,
                      style_hint: str = "académico") -> list[tuple[str, str]]:
    """
    Genera lista [(título, descripción), ...] de secciones del documento.
    El número de secciones es proporcional a target_pages.
    """
    n_sections = max(_MIN_SECTIONS,
                     min(_MAX_SECTIONS,
                         target_pages * _WORDS_PER_PAGE // _WORDS_PER_SECTION))

    system = (
        "Eres un investigador académico experto. Generas estructuras de "
        "documentos largos en formato exacto. NO añadas comentarios fuera del formato pedido."
    )
    user = (
        f"Necesito un esquema detallado para una investigación de {target_pages} "
        f"páginas sobre: \"{topic}\".\n\n"
        f"Estilo: {style_hint}.\n"
        f"Devuelve EXACTAMENTE {n_sections} secciones principales en este formato:\n\n"
        f"1. TÍTULO_SECCIÓN_1 || descripción de qué cubre (1 oración)\n"
        f"2. TÍTULO_SECCIÓN_2 || descripción\n"
        f"...\n\n"
        "REGLAS:\n"
        "- NO incluyas 'Portada' ni 'Referencias' como secciones — esas las añado yo aparte.\n"
        "- La primera sección debe ser una Introducción.\n"
        "- La última debe ser una Conclusión.\n"
        "- Las secciones intermedias deben cubrir aspectos distintos del tema sin solapamiento.\n"
        f"- Devuelve EXACTAMENTE {n_sections} líneas, ni más ni menos.\n"
        "- NO uses comillas en los títulos.\n"
    )
    raw = _llm_call(user, max_tokens=1200, system=system)

    # Parsear
    sections = []
    for line in raw.split("\n"):
        line = line.strip()
        m = re.match(r"^\d+\.\s*(.+?)\s*\|\|\s*(.+)$", line)
        if m:
            title = m.group(1).strip().strip('"').strip("*")
            desc  = m.group(2).strip().strip('"')
            sections.append((title, desc))

    # Fallback: si el parser no encontró formato || intentar parsear sin descripción
    if len(sections) < _MIN_SECTIONS:
        for line in raw.split("\n"):
            line = line.strip()
            m = re.match(r"^\d+\.\s*(.+)$", line)
            if m:
                title = m.group(1).strip().strip('"').strip("*")
                # Remover ||descripción si existe pegada
                if "||" in title:
                    title, desc = [x.strip() for x in title.split("||", 1)]
                else:
                    desc = ""
                if title and (title, desc) not in sections:
                    sections.append((title, desc))

    return sections[:n_sections] if sections else [
        ("Introducción", "Presentación del tema"),
        ("Antecedentes", "Contexto histórico"),
        ("Desarrollo", "Análisis profundo"),
        ("Aplicaciones", "Casos prácticos"),
        ("Conclusiones", "Síntesis y reflexiones"),
    ]


# ── Generador de contenido por sección ────────────────────────────────────────

def _generate_section(topic: str, section_title: str, section_desc: str,
                      all_titles: list[str], style_hint: str,
                      words_target: int = _WORDS_PER_SECTION) -> str:
    """Genera contenido extenso de UNA sección. Devuelve markdown."""
    system = (
        "Eres un investigador académico que escribe en español. "
        "Produces texto profundo, riguroso, con ejemplos concretos, datos "
        "verificables y argumentación bien estructurada. "
        "Usas formato markdown: subtítulos con ##, listas con -, énfasis con **. "
        "NUNCA escribes que el tema es 'amplio' o 'complejo' para rellenar; "
        "siempre aportas información sustantiva."
    )

    others = [t for t in all_titles if t != section_title]
    others_str = " · ".join(others[:8])

    user = (
        f"Investigación general: \"{topic}\"\n"
        f"Estilo del documento: {style_hint}\n\n"
        f"Escribe ÚNICAMENTE la sección: **{section_title}**\n"
    )
    if section_desc:
        user += f"Esta sección debe cubrir: {section_desc}\n"

    user += (
        f"\nObjetivo: ~{words_target} palabras de contenido sustantivo "
        f"({words_target//200}-{words_target//150} párrafos).\n\n"
        "FORMATO DE SALIDA OBLIGATORIO:\n"
        f"## {section_title}\n"
        "(contenido aquí, organizado en párrafos y subtítulos ### cuando corresponda)\n\n"
        "REGLAS ESTRICTAS:\n"
        "- NO repitas el título principal de la investigación.\n"
        "- NO escribas introducción genérica del tema completo; ya hay sección de introducción aparte.\n"
        f"- NO solapes con estas otras secciones: {others_str}\n"
        "- Incluye al menos 1 lista (con -) y 1 subtítulo ### si la longitud lo permite.\n"
        "- Datos, ejemplos, casos reales — NO generalidades vacías.\n"
        "- NO escribas conclusiones generales (eso va en la última sección).\n"
        "- NO incluyas referencias bibliográficas en línea (van al final del documento).\n"
        "- Devuelve SOLO el markdown de esta sección, sin preámbulos."
    )

    content = _llm_call(user, max_tokens=3500, system=system)

    # Limpiar: asegurar que empiece con ## section_title
    content = content.strip()
    if not content.startswith("#"):
        content = f"## {section_title}\n\n{content}"
    return content


# ── Generador de referencias plausibles ───────────────────────────────────────

def _generate_references(topic: str, n: int = 8) -> str:
    """Genera referencias bibliográficas plausibles (NO inventa nada que no exista)."""
    system = (
        "Eres bibliotecario académico. Generas referencias en formato APA 7 "
        "de fuentes REALES y RECONOCIDAS sobre el tema dado. "
        "Usa autores conocidos, editoriales reales, revistas con factor de impacto. "
        "Si dudas de una referencia exacta, prefiere obras canónicas del campo."
    )
    user = (
        f"Tema: {topic}\n\n"
        f"Genera {n} referencias en formato APA 7 sobre este tema. "
        "Devuelve UNA referencia por línea, sin numerar, sin comentarios.\n\n"
        "Formato:\n"
        "Apellido, N. (AÑO). *Título del libro o artículo*. Editorial o Revista, vol(núm), pp-pp."
    )
    try:
        return _llm_call(user, max_tokens=1000, system=system).strip()
    except Exception:
        return ""


# ── Ensamblador principal ─────────────────────────────────────────────────────

def _do_research(topic: str, target_pages: int, norm: str,
                 title: str, save_path: str, cover: str | dict,
                 style_hint: str = "académico profesional",
                 task=None) -> str:
    """Pipeline completo con STREAMING — escribe el .docx incrementalmente
    sección por sección sobre el MISMO archivo (sin crear duplicados).

    `task` es objeto Task de task_queue para reportar progreso.
    """
    def _progress(text: str):
        if task is not None:
            try:
                task.progress = text
            except Exception:
                pass
        print(f"[DeepResearch] {text}")

    t0 = time.time()

    # ── Normalizar norma — default professional (con portada bonita) ──────────
    effective_norm = (norm or "professional").lower()
    if effective_norm not in ("professional", "academic", "apa", "apa7", "chicago", "mla", "report"):
        effective_norm = "professional"

    # ── Convertir cover a dict y GARANTIZAR portada ───────────────────────────
    if isinstance(cover, str):
        try:
            cover_dict = json.loads(cover) if cover.strip().startswith("{") else {}
        except Exception:
            cover_dict = {}
    else:
        cover_dict = cover or {}
    if not isinstance(cover_dict, dict):
        cover_dict = {}
    # Generar portada por defecto SIEMPRE para que el doc no salga "feo"
    if not cover_dict.get("title"):
        cover_dict["title"] = topic[:80]
    if not cover_dict.get("subtitle"):
        cover_dict["subtitle"] = "Investigación generada por JARVIS"
    if not cover_dict.get("authors"):
        try:
            from pathlib import Path as _P
            cfg_path = _P(__file__).resolve().parent.parent / "config" / "api_keys.json"
            user_name = json.loads(cfg_path.read_text(encoding="utf-8")).get("user_name", "Usuario")
        except Exception:
            user_name = "Usuario"
        cover_dict["authors"] = user_name
    if not cover_dict.get("date"):
        from datetime import datetime as _dt
        cover_dict["date"] = _dt.now().strftime("%B %Y")

    # ── Outline ──────────────────────────────────────────────────────────────
    _progress("Generando esquema...")
    sections = _generate_outline(topic, target_pages, style_hint)
    n = len(sections)
    all_titles = [t for t, _ in sections]
    words_per_section = max(700, target_pages * _WORDS_PER_PAGE // n)

    # ── Calcular path FIJO del archivo (sin timestamp) para sobrescribir ──────
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(" ", "_")[:50] or "Investigacion"
    save_dir = _resolve_save_dir_local(save_path or "desktop")
    fixed_path = save_dir / f"{safe_title}.docx"

    from actions.document_creator import document_creator

    def _emit(content_md: str) -> None:
        """Emite el .docx al MISMO archivo (sobrescribiendo)."""
        try:
            document_creator({
                "action":    "word",
                "norm":      effective_norm,
                "title":     title,
                "save_path": str(save_dir),
                "toc":       True,
                "cover":     json.dumps(cover_dict, ensure_ascii=False),
                "header":    cover_dict.get("title", title)[:70],
                "content":   content_md,
                "overwrite_existing": str(fixed_path),
            })
        except Exception as e:
            print(f"[DeepResearch] Aviso al emitir: {e}")

    # ── PRIMERA EMISIÓN: portada + TOC + outline placeholder ──────────────────
    _progress(f"Esquema con {n} secciones. Creando documento inicial...")
    initial_parts = ["[TOC]\n"]
    for sec_title, _ in sections:
        initial_parts.append(f"## {sec_title}\n\n*(Generando contenido...)*\n")
    _emit("\n\n".join(initial_parts))
    _progress(f"Documento esqueleto creado en {fixed_path.name}. Escribiendo secciones...")

    # ── STREAMING: generar cada sección sobrescribiendo el mismo archivo ──────
    section_contents: list[str] = []
    for i, (sec_title, sec_desc) in enumerate(sections, 1):
        if task and task.cancel_flag.is_set():
            return "Investigación cancelada por el usuario."
        _progress(f"Sección {i}/{n}: {sec_title[:40]}")
        try:
            content = _generate_section(
                topic, sec_title, sec_desc, all_titles,
                style_hint, words_target=words_per_section,
            )
            section_contents.append(content)
        except Exception as e:
            section_contents.append(
                f"## {sec_title}\n\n*(Error generando esta sección: {e})*\n"
            )

        # Re-emitir el documento con el progreso actual
        partial_parts = ["[TOC]\n"]
        partial_parts.extend(section_contents)
        for j in range(i, n):
            rest_title = sections[j][0]
            partial_parts.append(
                f"## {rest_title}\n\n*(Generando — sección {j+1}/{n}...)*\n"
            )
        _emit("\n\n".join(partial_parts))

    # ── ABSTRACT + REFERENCIAS ────────────────────────────────────────────────
    _progress("Generando referencias...")
    refs = _generate_references(topic, n=max(6, target_pages // 3))

    _progress("Generando resumen / abstract...")
    try:
        abstract = _llm_call(
            f"Escribe un abstract de 150 palabras para una investigación titulada "
            f"\"{topic}\", que cubre las siguientes secciones: {', '.join(all_titles)}. "
            "Devuelve solo el texto del abstract, sin encabezado.",
            max_tokens=400,
            system="Eres un investigador. Escribe abstracts académicos en español, en un solo párrafo.",
        ).strip()
    except Exception:
        abstract = ""

    # ── EMISIÓN FINAL completa ────────────────────────────────────────────────
    _progress("Ensamblando documento final...")
    parts: list[str] = []
    if abstract:
        parts.append(f"[ABSTRACT]\n{abstract}\n[/ABSTRACT]\n")
    parts.append("[TOC]\n")
    parts.extend(section_contents)
    if refs:
        parts.append("\n[REFERENCES]\n" + refs + "\n[/REFERENCES]\n")

    full_content = "\n\n".join(parts)
    word_count = len(full_content.split())
    _progress(f"Documento final ({word_count} palabras). Guardando...")
    _emit(full_content)

    dur = int(time.time() - t0)
    _progress(f"Listo en {dur}s")
    return (
        f"Investigación '{title}' completada en {dur}s — "
        f"{n} secciones, {word_count} palabras. "
        f"Archivo único: '{fixed_path.name}' en '{fixed_path.parent}'."
    )


def _resolve_save_dir_local(save_path: str) -> Path:
    """Resolver carpeta destino — reutiliza la lógica del document_creator."""
    try:
        from actions.document_creator import _resolve_save_dir
        return _resolve_save_dir(save_path)
    except Exception:
        import os
        return Path(os.path.expanduser("~")) / "Desktop"


# ── Entrypoint público ────────────────────────────────────────────────────────

def deep_research(parameters: dict, player=None) -> str:
    """
    Genera una investigación larga por secciones. Por defecto corre en background.

    Parámetros:
      topic          (str)   tema central — OBLIGATORIO
      target_pages   (int)   número de páginas objetivo, default 15
      norm           (str)   "apa7" | "professional" | "academic", default "professional"
      title          (str)   título del archivo (sin extensión)
      save_path      (str)   carpeta destino, default "desktop"
      cover          (str|dict)  metadatos de portada (JSON o dict)
      style_hint     (str)   "académico" | "ensayo" | "técnico" | "divulgativo"
      background     (bool)  True (default) → devuelve task_id; False → bloquea hasta terminar
    """
    topic = (parameters.get("topic") or parameters.get("query")
             or parameters.get("subject") or "").strip()
    if not topic:
        return "Error: parámetro 'topic' obligatorio."

    target_pages = int(parameters.get("target_pages", 15))
    target_pages = max(3, min(60, target_pages))

    norm       = parameters.get("norm", "professional").lower()
    title      = parameters.get("title", topic[:50].replace(" ", "_"))
    save_path  = parameters.get("save_path", "desktop")
    cover      = parameters.get("cover", {})
    style_hint = parameters.get("style_hint", "académico profesional")
    background = parameters.get("background", True)
    if isinstance(background, str):
        background = background.lower() in ("true", "1", "yes", "sí", "si")

    if background:
        try:
            from core.task_queue import submit
            from functools import partial
            # Usar partial para evitar colisión entre el `title` de la TAREA
            # (1er arg de submit) y el `title` del DOCUMENTO (kwarg de _do_research).
            bound = partial(
                _do_research,
                topic=topic, target_pages=target_pages, norm=norm,
                title=title, save_path=save_path, cover=cover,
                style_hint=style_hint,
            )
            tid = submit(
                f"Investigación: {topic[:40]}",
                target=bound,
            )
            return (
                f"Investigación iniciada en segundo plano (tarea {tid}). "
                f"Estimado: {target_pages//3}-{target_pages//2} minutos para "
                f"~{target_pages} páginas. Le aviso al terminar, señor."
            )
        except ImportError:
            background = False   # fallback síncrono

    # Síncrono (bloquea hasta terminar — puede tardar varios minutos)
    try:
        return _do_research(
            topic=topic, target_pages=target_pages, norm=norm,
            title=title, save_path=save_path, cover=cover,
            style_hint=style_hint, task=None,
        )
    except Exception as e:
        traceback.print_exc()
        return f"Error en investigación profunda: {e}"
