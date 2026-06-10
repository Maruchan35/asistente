# -*- coding: utf-8 -*-
"""
knowledge_base.py — Base de conocimiento personal persistente de JARVIS.
Guarda notas, ideas, snippets, referencias y hechos en un archivo JSON local.
"""
import json
import time
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
KB_FILE  = BASE_DIR / "memory" / "knowledge_base.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load() -> list:
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not KB_FILE.exists():
        KB_FILE.write_text("[]", encoding="utf-8")
        return []
    try:
        data = json.loads(KB_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save(data: list):
    try:
        from core.safe_json import safe_write
        safe_write(KB_FILE, data)
    except ImportError:
        KB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _short_id(entry: dict) -> str:
    return str(entry.get("id", ""))[:8]

# ── Función principal ─────────────────────────────────────────────────────────

def knowledge_base(parameters: dict, player=None) -> str:
    """
    Base de conocimiento personal. Acciones:
    add/save/store | search/find | list | get/read/view | update | delete | stats | export
    """
    raw_action = parameters.get("action", "list").strip().lower()

    # Normalizar aliases
    _ALIASES = {
        "save": "add", "store": "add",
        "find": "search",
        "read": "get", "view": "get",
        "remove": "delete",
    }
    action = _ALIASES.get(raw_action, raw_action)

    title    = parameters.get("title", "").strip()
    content  = parameters.get("content", "").strip()
    kb_type  = parameters.get("type", "note").strip().lower()
    tags_raw = parameters.get("tags", "").strip()
    query    = parameters.get("query", "").strip()
    entry_id = parameters.get("entry_id", "").strip()
    path_out = parameters.get("path", "").strip()

    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

    try:
        data = _load()

        # ── ADD ───────────────────────────────────────────────────────────
        if action == "add":
            if not title and not content:
                return "Error: Necesito al menos un título o contenido para guardar."
            entry = {
                "id":        str(int(time.time() * 1000)),
                "title":     title or content[:50],
                "content":   content,
                "type":      kb_type,
                "tags":      tags,
                "created":   time.strftime("%Y-%m-%d %H:%M"),
                "updated":   time.strftime("%Y-%m-%d %H:%M"),
            }
            data.append(entry)
            _save(data)
            if player:
                try: player.write_log(f"📚 KB guardado: {entry['title']}")
                except Exception: pass
            return f"Guardado en la base de conocimiento: '{entry['title']}' (ID: {_short_id(entry)})."

        # ── LIST ──────────────────────────────────────────────────────────
        elif action == "list":
            if not data:
                return "La base de conocimiento está vacía. Podés guardar notas, ideas, snippets, etc."
            lines = [f"📚 Base de conocimiento — {len(data)} entradas:"]
            for e in data[-20:]:   # últimas 20
                tag_str = f" [{', '.join(e.get('tags', []))}]" if e.get('tags') else ""
                lines.append(f"  [{_short_id(e)}] {e.get('type','note').upper()} — {e.get('title','Sin título')}{tag_str} ({e.get('created','')})")
            return "\n".join(lines)

        # ── SEARCH ────────────────────────────────────────────────────────
        elif action == "search":
            if not query:
                return "Error: Necesito un término de búsqueda (parámetro 'query')."
            q = query.lower()
            results = [
                e for e in data
                if q in e.get("title","").lower()
                or q in e.get("content","").lower()
                or any(q in t.lower() for t in e.get("tags",[]))
                or q in e.get("type","").lower()
            ]
            if not results:
                return f"No encontré nada en la base de conocimiento para '{query}'."
            lines = [f"🔍 {len(results)} resultado(s) para '{query}':"]
            for e in results[:10]:
                preview = e.get("content","")[:80].replace("\n"," ")
                lines.append(f"  [{_short_id(e)}] {e.get('title','')} — {preview}...")
            return "\n".join(lines)

        # ── GET ───────────────────────────────────────────────────────────
        elif action == "get":
            if not entry_id:
                return "Error: Necesito 'entry_id' para ver una entrada."
            match = next((e for e in data if e.get("id","").startswith(entry_id)), None)
            if not match:
                return f"No encontré una entrada con ID '{entry_id}'."
            tags_str = ", ".join(match.get("tags",[])) or "sin tags"
            return (
                f"📄 [{_short_id(match)}] {match.get('title')}\n"
                f"Tipo: {match.get('type')} | Tags: {tags_str}\n"
                f"Creado: {match.get('created')} | Actualizado: {match.get('updated')}\n\n"
                f"{match.get('content','')}"
            )

        # ── UPDATE ────────────────────────────────────────────────────────
        elif action == "update":
            if not entry_id:
                return "Error: Necesito 'entry_id' para actualizar."
            match = next((e for e in data if e.get("id","").startswith(entry_id)), None)
            if not match:
                return f"No encontré entrada con ID '{entry_id}'."
            if title:   match["title"]   = title
            if content: match["content"] = content
            if tags:    match["tags"]    = tags
            if kb_type: match["type"]    = kb_type
            match["updated"] = time.strftime("%Y-%m-%d %H:%M")
            _save(data)
            return f"Entrada '{match['title']}' actualizada correctamente."

        # ── DELETE ────────────────────────────────────────────────────────
        elif action == "delete":
            if not entry_id:
                return "Error: Necesito 'entry_id' para eliminar."
            before = len(data)
            data = [e for e in data if not e.get("id","").startswith(entry_id)]
            if len(data) == before:
                return f"No encontré entrada con ID '{entry_id}'."
            _save(data)
            return f"Entrada '{entry_id}' eliminada de la base de conocimiento."

        # ── STATS ─────────────────────────────────────────────────────────
        elif action == "stats":
            if not data:
                return "La base de conocimiento está vacía."
            from collections import Counter
            types  = Counter(e.get("type","note") for e in data)
            all_tags = [t for e in data for t in e.get("tags",[])]
            top_tags = Counter(all_tags).most_common(5)
            lines = [
                f"📊 Estadísticas de la base de conocimiento:",
                f"  Total de entradas: {len(data)}",
                f"  Por tipo: {dict(types)}",
                f"  Tags más usados: {', '.join(f'{t}({n})' for t,n in top_tags) or 'ninguno'}",
            ]
            return "\n".join(lines)

        # ── EXPORT ────────────────────────────────────────────────────────
        elif action == "export":
            import os
            dest = path_out or str(Path(os.path.expanduser("~")) / "Desktop" / "knowledge_base_export.json")
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return f"Base de conocimiento exportada a '{dest}' ({len(data)} entradas)."

        else:
            return f"Acción '{action}' no reconocida. Usa: add | list | search | get | update | delete | stats | export"

    except Exception as e:
        traceback.print_exc()
        return f"Error en knowledge_base: {str(e)}"
