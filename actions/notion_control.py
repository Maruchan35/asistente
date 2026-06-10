"""notion_control.py — Notion API integration for JARVIS.
Read/write pages, databases, and blocks via Notion's official REST API.
Requires an Integration Token from https://www.notion.so/my-integrations."""
from __future__ import annotations
import json, re, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_BASE = "https://api.notion.com/v1"
VERSION  = "2022-06-28"

def _load_keys() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _notion_request(method: str, path: str, token: str,
                    body: dict | None = None, timeout: int = 10) -> dict | str:
    url  = f"{API_BASE}/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization":    f"Bearer {token}",
            "Notion-Version":   VERSION,
            "Content-Type":     "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_err = json.loads(e.read())
        return f"Notion error {e.code}: {body_err.get('message', e.reason)}"
    except urllib.error.URLError as e:
        return f"No se pudo conectar a Notion: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

def _text_content(block: dict) -> str:
    """Extract plain text from a Notion block."""
    btype = block.get("type", "")
    bdata = block.get(btype, {})
    rich  = bdata.get("rich_text", [])
    return "".join(r.get("plain_text", "") for r in rich)

def _page_title(page: dict) -> str:
    props = page.get("properties", {})
    for key in ("Name", "Title", "title", "Nombre"):
        if key in props:
            title_prop = props[key]
            for rt in title_prop.get("title", title_prop.get("rich_text", [])):
                return rt.get("plain_text", "")
    return page.get("id", "Sin título")[:12]

def _format_page(page: dict) -> str:
    title    = _page_title(page)
    page_id  = page.get("id", "?").replace("-", "")[:12]
    url      = page.get("url", "")
    modified = page.get("last_edited_time", "")[:10]
    return f"  [{page_id}] {title} — {modified}\n  {url}"

# ══════════════════════════════════════════════════════════════════════════════
def notion_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "search").lower().strip()

    def log(msg: str):
        if player:
            player.write_log(f"📓 Notion: {msg}")

    keys  = _load_keys()
    token = keys.get("notion_token", keys.get("notion_integration_token", "")).strip()

    if action in ("setup", "configurar"):
        return (
            "Para configurar Notion:\n"
            "1. Ir a https://www.notion.so/my-integrations\n"
            "2. Crear una nueva integración → copiar el 'Internal Integration Token'\n"
            "3. Agregar en config/api_keys.json:\n"
            "   'notion_token': 'secret_XXXXXXXXXX'\n"
            "4. En Notion, abrir cada página/base que quieras usar:\n"
            "   ··· → Connect to → [nombre de tu integración]"
        )

    if not token:
        return (
            "Notion no configurado. Usá action=setup para ver instrucciones.\n"
            "Necesitás un 'notion_token' en config/api_keys.json."
        )

    # ── SEARCH ────────────────────────────────────────────────────────────────
    if action in ("search", "buscar"):
        query = parameters.get("query", parameters.get("q", "")).strip()
        count = int(parameters.get("count", 10))
        body  = {"page_size": count}
        if query:
            body["query"] = query
        result = _notion_request("POST", "search", token, body)
        if isinstance(result, str):
            return f"Error: {result}"
        items = result.get("results", [])
        if not items:
            return f"No se encontraron páginas{' para «' + query + '»' if query else ''}."
        lines = [f"Páginas en Notion ({len(items)}):"]
        for item in items:
            lines.append(_format_page(item))
        log(f"Search '{query}': {len(items)} resultados")
        return "\n".join(lines)

    # ── READ PAGE ─────────────────────────────────────────────────────────────
    elif action in ("read", "leer", "get_page"):
        page_id = parameters.get("page_id", parameters.get("id", "")).strip()
        if not page_id:
            return "Especificá page_id con el ID de la página de Notion."
        page_id = page_id.replace("-", "")

        # Get page metadata
        page = _notion_request("GET", f"pages/{page_id}", token)
        if isinstance(page, str):
            return f"Error: {page}"
        title = _page_title(page)

        # Get page blocks (content)
        blocks = _notion_request("GET", f"blocks/{page_id}/children?page_size=50", token)
        if isinstance(blocks, str):
            return f"Error obteniendo contenido: {blocks}"

        lines = [f"Página: {title}\n"]
        for block in blocks.get("results", []):
            text = _text_content(block)
            btype = block.get("type", "")
            if text:
                if btype.startswith("heading"):
                    level = btype.replace("heading_", "")
                    prefix = "#" * int(level) if level.isdigit() else "##"
                    lines.append(f"{prefix} {text}")
                elif btype == "bulleted_list_item":
                    lines.append(f"  • {text}")
                elif btype == "numbered_list_item":
                    lines.append(f"  {text}")
                elif btype == "to_do":
                    done = block.get("to_do", {}).get("checked", False)
                    lines.append(f"  {'[x]' if done else '[ ]'} {text}")
                elif btype == "code":
                    lang = block.get("code", {}).get("language", "")
                    lines.append(f"```{lang}\n{text}\n```")
                else:
                    lines.append(text)

        log(f"Página leída: {title[:40]}")
        return "\n".join(lines)

    # ── CREATE PAGE ───────────────────────────────────────────────────────────
    elif action in ("create", "crear", "new", "nueva"):
        title   = parameters.get("title", parameters.get("name", "Nueva página")).strip()
        content = parameters.get("content", parameters.get("body", "")).strip()
        parent_id = parameters.get("parent_id", parameters.get("database_id", "")).strip()

        if not parent_id:
            return (
                "Especificá parent_id con el ID de la página padre o database donde crear.\n"
                "Usá action=search para encontrar IDs de páginas existentes."
            )

        parent_id = parent_id.replace("-", "")
        # Determine if parent is page or database
        parent_type = "page_id" if parameters.get("parent_type", "page") == "page" else "database_id"

        blocks = []
        if content:
            for para in content.split("\n"):
                para = para.strip()
                if not para:
                    continue
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": para[:2000]}}]
                    }
                })

        body = {
            "parent": {parent_type: parent_id},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": title}}]
                }
            },
        }
        if blocks:
            body["children"] = blocks[:100]

        result = _notion_request("POST", "pages", token, body)
        if isinstance(result, str):
            return f"Error creando página: {result}"

        new_id  = result.get("id", "?").replace("-", "")[:12]
        new_url = result.get("url", "")
        log(f"Página creada: {title}")
        return f"Página '{title}' creada en Notion.\n  ID: {new_id}\n  {new_url}"

    # ── APPEND TO PAGE ────────────────────────────────────────────────────────
    elif action in ("append", "agregar", "add_content"):
        page_id = parameters.get("page_id", parameters.get("id", "")).strip()
        content = parameters.get("content", parameters.get("text", "")).strip()
        if not page_id:
            return "Especificá page_id."
        if not content:
            return "Especificá content con el texto a agregar."
        page_id = page_id.replace("-", "")

        block_type = parameters.get("block_type", "paragraph").lower()
        VALID_TYPES = {"paragraph", "bulleted_list_item", "numbered_list_item",
                       "to_do", "heading_1", "heading_2", "heading_3", "quote"}
        if block_type not in VALID_TYPES:
            block_type = "paragraph"

        blocks = []
        for para in content.split("\n"):
            para = para.strip()
            if not para:
                continue
            block = {
                "object": "block",
                "type": block_type,
                block_type: {
                    "rich_text": [{"type": "text", "text": {"content": para[:2000]}}]
                }
            }
            if block_type == "to_do":
                block[block_type]["checked"] = False
            blocks.append(block)

        result = _notion_request("PATCH", f"blocks/{page_id}/children",
                                  token, {"children": blocks[:100]})
        if isinstance(result, str):
            return f"Error agregando contenido: {result}"
        log(f"Contenido agregado a {page_id[:12]}")
        return f"Contenido agregado a la página."

    # ── QUERY DATABASE ────────────────────────────────────────────────────────
    elif action in ("query", "query_database", "database"):
        db_id = parameters.get("database_id", parameters.get("id", "")).strip()
        count = int(parameters.get("count", 10))
        if not db_id:
            return "Especificá database_id con el ID de la base de datos de Notion."
        db_id = db_id.replace("-", "")

        body = {"page_size": count}
        # Optional filter
        filter_prop = parameters.get("filter_property", "")
        filter_val  = parameters.get("filter_value", "")
        if filter_prop and filter_val:
            body["filter"] = {
                "property": filter_prop,
                "rich_text": {"contains": filter_val}
            }

        result = _notion_request("POST", f"databases/{db_id}/query", token, body)
        if isinstance(result, str):
            return f"Error: {result}"
        items = result.get("results", [])
        if not items:
            return "La base de datos está vacía o no hay resultados para el filtro."
        lines = [f"Base de datos Notion ({len(items)} registros):"]
        for item in items:
            lines.append(_format_page(item))
        log(f"Database query: {len(items)} registros")
        return "\n".join(lines)

    # ── UPDATE PAGE ───────────────────────────────────────────────────────────
    elif action in ("update", "actualizar", "rename"):
        page_id  = parameters.get("page_id", parameters.get("id", "")).strip()
        new_title = parameters.get("title", parameters.get("name", "")).strip()
        archived  = parameters.get("archived", None)
        if not page_id:
            return "Especificá page_id."
        page_id = page_id.replace("-", "")

        body: dict = {}
        if new_title:
            body["properties"] = {
                "title": {"title": [{"type": "text", "text": {"content": new_title}}]}
            }
        if archived is not None:
            body["archived"] = bool(archived)
        if not body:
            return "Especificá title o archived para actualizar."

        result = _notion_request("PATCH", f"pages/{page_id}", token, body)
        if isinstance(result, str):
            return f"Error: {result}"
        log(f"Página actualizada: {page_id[:12]}")
        return f"Página actualizada."

    # ── ARCHIVE (delete) ──────────────────────────────────────────────────────
    elif action in ("archive", "delete", "archivar", "eliminar"):
        page_id = parameters.get("page_id", parameters.get("id", "")).strip()
        if not page_id:
            return "Especificá page_id."
        page_id = page_id.replace("-", "")
        result = _notion_request("PATCH", f"pages/{page_id}", token, {"archived": True})
        if isinstance(result, str):
            return f"Error: {result}"
        log(f"Página archivada: {page_id[:12]}")
        return "Página archivada en Notion."

    return (f"Acción '{action}' no reconocida. "
            "Usa: search | read | create | append | query | update | archive | setup")
