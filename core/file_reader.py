"""
core/file_reader.py — Universal file content extractor for JARVIS.
Supports: txt, csv, json, md, py, js, html, xml, pdf, docx, xlsx, images.
"""
from __future__ import annotations
import os, json

# ── Maximum characters sent to JARVIS (keeps token cost sane) ────────────────
MAX_CHARS = 12_000   # ~3 k tokens, enough for most documents

def read_file(path: str) -> tuple[str, str]:
    """
    Returns (content: str, summary_label: str).
    content      — text to inject into JARVIS
    summary_label — short description for the UI label
    """
    if not os.path.isfile(path):
        return "", f"Archivo no encontrado: {path}"

    ext  = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    size = os.path.getsize(path)

    # ── Plain text ────────────────────────────────────────────────────────────
    if ext in (".txt", ".md", ".py", ".js", ".ts", ".html", ".xml",
               ".css", ".sh", ".bat", ".ini", ".cfg", ".yaml", ".yml",
               ".log", ".sql", ".rs", ".go", ".java", ".c", ".cpp", ".h"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_CHARS)
            truncated = " [TRUNCADO]" if size > MAX_CHARS else ""
            return content, f"Texto plano{truncated}"
        except Exception as e:
            return "", f"Error leyendo texto: {e}"

    # ── JSON ──────────────────────────────────────────────────────────────────
    if ext == ".json":
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                raw = f.read(MAX_CHARS)
            # Pretty-print if small enough
            try:
                obj = json.loads(raw)
                pretty = json.dumps(obj, ensure_ascii=False, indent=2)
                return pretty[:MAX_CHARS], "JSON"
            except Exception:
                return raw, "JSON (no parseado)"
        except Exception as e:
            return "", f"Error leyendo JSON: {e}"

    # ── CSV ───────────────────────────────────────────────────────────────────
    if ext == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(path, nrows=200, encoding_errors="replace")
            content = (
                f"Filas totales: ~{len(df)}\n"
                f"Columnas: {', '.join(str(c) for c in df.columns)}\n\n"
                f"{df.to_string(max_rows=50, max_cols=20)}"
            )
            return content[:MAX_CHARS], f"CSV ({len(df)} filas)"
        except Exception as e:
            return "", f"Error leyendo CSV: {e}"

    # ── Excel ─────────────────────────────────────────────────────────────────
    if ext in (".xlsx", ".xls", ".ods"):
        try:
            import pandas as pd
            xls = pd.ExcelFile(path)
            parts = []
            for sheet in xls.sheet_names[:5]:   # cap at 5 sheets
                df = pd.read_excel(path, sheet_name=sheet, nrows=100)
                parts.append(
                    f"=== Hoja: {sheet} ===\n"
                    f"Filas: {len(df)}  Columnas: {', '.join(str(c) for c in df.columns)}\n"
                    f"{df.to_string(max_rows=30, max_cols=15)}"
                )
            content = "\n\n".join(parts)
            return content[:MAX_CHARS], f"Excel ({len(xls.sheet_names)} hojas)"
        except Exception as e:
            return "", f"Error leyendo Excel: {e}"

    # ── PDF ───────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        try:
            import pdfplumber
            pages_text = []
            with pdfplumber.open(path) as pdf:
                total = len(pdf.pages)
                for pg in pdf.pages[:30]:   # first 30 pages
                    t = pg.extract_text() or ""
                    if t.strip():
                        pages_text.append(t)
            content = "\n\n".join(pages_text)
            truncated = " [TRUNCADO a 30 págs]" if total > 30 else ""
            return content[:MAX_CHARS], f"PDF ({total} págs){truncated}"
        except Exception as e:
            return "", f"Error leyendo PDF: {e}"

    # ── Word DOCX ─────────────────────────────────────────────────────────────
    if ext in (".docx", ".doc"):
        try:
            import docx as _docx
            doc = _docx.Document(path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            content = "\n".join(paragraphs)
            return content[:MAX_CHARS], f"Word ({len(paragraphs)} párrafos)"
        except Exception as e:
            return "", f"Error leyendo Word: {e}"

    # ── Images (OCR via Gemini vision) ────────────────────────────────────────
    if ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"):
        try:
            import base64
            with open(path, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode()
            mime = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png",  ".bmp": "image/bmp",
                ".webp": "image/webp", ".gif": "image/gif",
                ".tiff": "image/tiff",
            }.get(ext, "image/jpeg")
            # Return special marker — main.py will send as image part
            return f"__IMAGE_B64__{mime}::{b64}", "Imagen"
        except Exception as e:
            return "", f"Error leyendo imagen: {e}"

    # ── Unknown ───────────────────────────────────────────────────────────────
    return "", f"Tipo de archivo '{ext}' no soportado."


def build_inject_message(filename: str, content: str, file_type: str) -> str:
    """Build the text that JARVIS receives about the dropped file."""
    if content.startswith("__IMAGE_B64__"):
        # Image: handled separately by caller
        return content

    header = (
        f"[ARCHIVO CARGADO EN DROP ZONE]\n"
        f"Nombre: {filename}\n"
        f"Tipo: {file_type}\n"
        f"─────────────────────────────\n"
    )
    return header + content
