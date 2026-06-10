"""file_processor.py — Full-featured file processing engine.
Reads files, performs local operations (resize, OCR, CSV stats, archive) and
delegates AI tasks (summarize, explain, translate, review) to openrouter_agent."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Helpers ───────────────────────────────────────────────────────────────────
def _ps(cmd: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return f"ERROR: {e}"

def _run(args: list[str], timeout: int = 60, cwd: str | None = None) -> tuple[bool, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           cwd=cwd, creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)

def _ai(prompt: str) -> str:
    try:
        from actions.openrouter_agent import openrouter_agent
        return openrouter_agent(prompt)
    except Exception as e:
        return f"[AI no disponible: {e}]"

def _load_keys() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return {}

def _current_file(player) -> str | None:
    """Return path of the currently loaded file in the UI drop zone."""
    if player and hasattr(player, "current_file_path"):
        return player.current_file_path or None
    return None

def _save_result(content: str, src_path: str, suffix: str) -> str:
    p = Path(src_path)
    out = p.parent / f"{p.stem}_{suffix}.txt"
    out.write_text(content, encoding="utf-8")
    return str(out)

# ── File-type detection ───────────────────────────────────────────────────────
TEXT_EXTS  = {".txt",".md",".py",".js",".ts",".html",".css",".xml",
               ".sh",".bat",".ps1",".json",".yaml",".yml",".ini",".log",".sql",".java",".cs",".cpp",".c",".go",".rs"}
IMAGE_EXTS = {".jpg",".jpeg",".png",".gif",".bmp",".webp",".tiff",".tif"}
PDF_EXT    = {".pdf"}
DOCX_EXT   = {".docx",".doc"}
XLSX_EXT   = {".xlsx",".xls",".ods",".csv"}
AUDIO_EXT  = {".mp3",".wav",".ogg",".flac",".m4a",".aac",".wma"}
VIDEO_EXT  = {".mp4",".avi",".mkv",".mov",".wmv",".flv",".webm"}
ARCHIVE_EXT= {".zip",".rar",".7z",".tar",".gz",".bz2"}
PPT_EXT    = {".pptx",".ppt"}

def _detect_type(ext: str) -> str:
    ext = ext.lower()
    if ext in TEXT_EXTS:    return "text"
    if ext in IMAGE_EXTS:   return "image"
    if ext in PDF_EXT:      return "pdf"
    if ext in DOCX_EXT:     return "docx"
    if ext in XLSX_EXT:     return "spreadsheet"
    if ext in AUDIO_EXT:    return "audio"
    if ext in VIDEO_EXT:    return "video"
    if ext in ARCHIVE_EXT:  return "archive"
    if ext in PPT_EXT:      return "presentation"
    return "binary"

# ── Core read ─────────────────────────────────────────────────────────────────
def _read_content(path: str) -> tuple[str, str]:
    """Returns (content, file_type)."""
    try:
        from core.file_reader import read_file
        return read_file(path)
    except Exception:
        pass
    # Fallback: raw text
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace"), "text"
    except Exception as e:
        return f"[Error leyendo archivo: {e}]", "error"

# ══════════════════════════════════════════════════════════════════════════════
def file_processor(parameters: dict, player=None, speak=None) -> str:
    file_path  = parameters.get("file_path", "").strip()
    action     = parameters.get("action", "").strip().lower()
    instruction= parameters.get("instruction", "").strip()
    fmt        = parameters.get("format", "").strip().lower()
    save_out   = parameters.get("save", True)

    # Resolve path
    if not file_path:
        file_path = _current_file(player) or ""
    if not file_path:
        return "No hay archivo cargado. Arrastrá un archivo al panel de archivos primero."
    if not Path(file_path).exists():
        return f"Archivo no encontrado: {file_path}"

    p    = Path(file_path)
    ext  = p.suffix.lower()
    ftype= _detect_type(ext)
    name = p.name
    size_kb = p.stat().st_size / 1024

    def log(msg):
        if player: player.write_log(f"📎 {msg}")

    log(f"{action} | {name} ({size_kb:.1f} KB)")

    # ── INFO ──────────────────────────────────────────────────────────────────
    if action in ("info", ""):
        info = (f"Archivo: {name}\n"
                f"Tipo: {ftype} ({ext})\n"
                f"Tamaño: {size_kb:.1f} KB\n"
                f"Ruta: {file_path}")
        return info

    # ══ TEXT & CODE ═══════════════════════════════════════════════════════════
    if ftype in ("text", "pdf", "docx", "presentation"):
        content, _ = _read_content(file_path)
        if content.startswith("[Error"):
            return content

        # ── SUMMARIZE ─────────────────────────────────────────────────────────
        if action in ("summarize", "resumir", "resumen"):
            prompt = f"Resumí este documento de manera clara y concisa en español:\n\n{content[:8000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "resumen")
            return result

        # ── TRANSLATE HINT ────────────────────────────────────────────────────
        elif action in ("translate", "translate_hint", "traducir"):
            target = instruction or "español"
            prompt = f"Traducí el siguiente texto al {target}:\n\n{content[:8000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "traducido")
            return result

        # ── FIX (grammar / code) ──────────────────────────────────────────────
        elif action in ("fix", "corregir"):
            if ftype == "text" and ext not in {".py",".js",".ts",".cs",".java",".cpp",".c",".go",".rs"}:
                prompt = f"Corregí los errores ortográficos y gramaticales del siguiente texto:\n\n{content[:8000]}"
            else:
                prompt = f"Corregí los bugs y errores en el siguiente código ({ext}):\n\n{content[:8000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "corregido")
            return result

        # ── EXPLAIN / REVIEW ─────────────────────────────────────────────────
        elif action in ("explain", "explicar", "review", "revisar"):
            prompt = f"Explicá detalladamente el siguiente {'código' if ext in {'.py','.js','.ts','.cs'} else 'documento'}:\n\n{content[:8000]}"
            return _ai(prompt)

        # ── OPTIMIZE ─────────────────────────────────────────────────────────
        elif action in ("optimize", "optimizar"):
            prompt = f"Optimizá el siguiente código ({ext}) para mejor rendimiento y legibilidad:\n\n{content[:8000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "optimizado")
            return result

        # ── DOCUMENT ─────────────────────────────────────────────────────────
        elif action in ("document", "documentar"):
            prompt = f"Agregá docstrings y comentarios claros al siguiente código ({ext}):\n\n{content[:8000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "documentado")
            return result

        # ── RUN (code only) ───────────────────────────────────────────────────
        elif action == "run":
            if ext == ".py":
                ok, out = _run([sys.executable, file_path], timeout=30)
                return f"{'✅' if ok else '❌'} Salida:\n{out[:2000]}"
            elif ext in (".ps1",):
                ok, out = _run(["powershell", "-File", file_path], timeout=30)
                return f"{'✅' if ok else '❌'} Salida:\n{out[:2000]}"
            elif ext == ".bat":
                ok, out = _run(["cmd", "/c", file_path], timeout=30)
                return f"{'✅' if ok else '❌'} Salida:\n{out[:2000]}"
            return f"No puedo ejecutar archivos {ext} directamente."

        # ── WORD COUNT ────────────────────────────────────────────────────────
        elif action in ("word_count", "contar_palabras", "count"):
            words = len(content.split())
            lines = content.count("\n") + 1
            chars = len(content)
            return f"{name}: {words} palabras | {lines} líneas | {chars} caracteres"

        # ── TO BULLET ─────────────────────────────────────────────────────────
        elif action in ("to_bullet", "bullets", "esquema"):
            prompt = f"Convertí el siguiente texto en una lista de puntos clave con viñetas:\n\n{content[:6000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "bullets")
            return result

        # ── REFORMAT ─────────────────────────────────────────────────────────
        elif action in ("reformat", "reformatear"):
            prompt = f"Reformateá el siguiente texto para mejor legibilidad, corrigiendo estructura y formato:\n\n{content[:6000]}"
            result = _ai(prompt)
            if save_out: _save_result(result, file_path, "reformateado")
            return result

        # ── TEST (code) ───────────────────────────────────────────────────────
        elif action in ("test", "generar_tests"):
            prompt = f"Generá tests unitarios completos para el siguiente código ({ext}):\n\n{content[:6000]}"
            result = _ai(prompt)
            if save_out:
                out_p = p.parent / f"test_{p.stem}.py"
                out_p.write_text(result, encoding="utf-8")
                return f"Tests guardados en: {out_p}\n\n{result[:500]}..."
            return result

        # ── CUSTOM INSTRUCTION ────────────────────────────────────────────────
        elif instruction:
            prompt = f"{instruction}\n\n[Archivo: {name}]\n{content[:8000]}"
            return _ai(prompt)

        return f"Acción '{action}' no reconocida para archivos de texto/documento."

    # ══ IMAGE ═════════════════════════════════════════════════════════════════
    elif ftype == "image":

        # ── DESCRIBE ─────────────────────────────────────────────────────────
        if action in ("describe", "describir", "analyze", "analizar"):
            try:
                from core.file_reader import read_file
                content, _ = read_file(file_path)
                if content.startswith("__IMAGE_B64__"):
                    # Pass to AI via openrouter with image
                    instr = instruction or "Describí detalladamente esta imagen en español."
                    # For now inject as text description request
                    return _ai(f"[Imagen: {name}] {instr}\n\n{content[:500]}")
            except Exception:
                pass
            return f"Imagen '{name}' ({size_kb:.1f} KB). Usá el botón 'Analizar con JARVIS' en el panel de archivos para análisis visual."

        # ── OCR ───────────────────────────────────────────────────────────────
        elif action == "ocr":
            # Try Tesseract if available
            tesseract = shutil.which("tesseract")
            if tesseract:
                out_file = str(p.parent / f"{p.stem}_ocr")
                ok, out = _run([tesseract, file_path, out_file, "-l", "spa+eng"], timeout=30)
                if ok:
                    txt_path = out_file + ".txt"
                    if Path(txt_path).exists():
                        result = Path(txt_path).read_text(encoding="utf-8")
                        return f"OCR completado:\n{result}"
                return f"Tesseract error: {out}"
            return "OCR requiere Tesseract. Instalalo con: winget install tesseract-ocr"

        # ── RESIZE ────────────────────────────────────────────────────────────
        elif action in ("resize", "redimensionar"):
            try:
                from PIL import Image
                width  = parameters.get("width")
                height = parameters.get("height")
                scale  = parameters.get("scale")
                img = Image.open(file_path)
                orig_w, orig_h = img.size
                if scale:
                    new_w = int(orig_w * float(scale))
                    new_h = int(orig_h * float(scale))
                elif width and height:
                    new_w, new_h = int(width), int(height)
                elif width:
                    ratio  = int(width) / orig_w
                    new_w, new_h = int(width), int(orig_h * ratio)
                elif height:
                    ratio  = int(height) / orig_h
                    new_w, new_h = int(orig_w * ratio), int(height)
                else:
                    return "Especificá width, height o scale para redimensionar."
                img_r  = img.resize((new_w, new_h), Image.LANCZOS)
                out_p  = p.parent / f"{p.stem}_resized{p.suffix}"
                img_r.save(str(out_p))
                return f"Imagen redimensionada: {new_w}×{new_h} px → {out_p.name}"
            except ImportError:
                return "Pillow no instalado: pip install Pillow"

        # ── COMPRESS ─────────────────────────────────────────────────────────
        elif action in ("compress", "comprimir"):
            try:
                from PIL import Image
                quality = int(parameters.get("quality", 70))
                img    = Image.open(file_path)
                out_p  = p.parent / f"{p.stem}_compressed.jpg"
                img.convert("RGB").save(str(out_p), "JPEG", quality=quality, optimize=True)
                new_size = out_p.stat().st_size / 1024
                return f"Imagen comprimida ({quality}% calidad): {size_kb:.0f} KB → {new_size:.0f} KB → {out_p.name}"
            except ImportError:
                return "Pillow no instalado: pip install Pillow"

        # ── CONVERT ──────────────────────────────────────────────────────────
        elif action in ("convert", "convertir"):
            if not fmt:
                return "Especificá el formato de destino (ej: png, jpg, webp)."
            try:
                from PIL import Image
                out_p = p.parent / f"{p.stem}.{fmt}"
                Image.open(file_path).save(str(out_p))
                return f"Imagen convertida a {fmt.upper()}: {out_p.name}"
            except ImportError:
                return "Pillow no instalado: pip install Pillow"

        return f"Acción '{action}' no reconocida para imágenes. Usa: describe | ocr | resize | compress | convert | info"

    # ══ SPREADSHEET (CSV / Excel) ═════════════════════════════════════════════
    elif ftype == "spreadsheet":
        try:
            import pandas as pd
        except ImportError:
            return "pandas no instalado: pip install pandas openpyxl"

        try:
            if ext == ".csv":
                df = pd.read_csv(file_path, encoding="utf-8-sig", nrows=500)
            else:
                df = pd.read_excel(file_path, nrows=500)
        except Exception as e:
            return f"Error leyendo hoja de cálculo: {e}"

        rows, cols = df.shape

        # ── STATS ─────────────────────────────────────────────────────────────
        if action in ("stats", "estadisticas", "estadísticas", "analyze", "analizar"):
            desc = df.describe(include="all").to_string()
            prompt = (f"Análisis de '{name}' ({rows} filas, {cols} columnas):\n"
                      f"Columnas: {', '.join(df.columns.tolist())}\n\n"
                      f"Estadísticas:\n{desc[:3000]}\n\n"
                      f"Primeras filas:\n{df.head(5).to_string()}\n\n"
                      "Hacé un análisis claro de estos datos en español.")
            return _ai(prompt)

        # ── FILTER ────────────────────────────────────────────────────────────
        elif action in ("filter", "filtrar"):
            col  = parameters.get("column", "")
            val  = parameters.get("value", "")
            cond = parameters.get("condition", "contains")
            if not col: return "Especificá 'column' para filtrar."
            if col not in df.columns:
                return f"Columna '{col}' no encontrada. Columnas: {', '.join(df.columns)}"
            try:
                if cond == "equals":   filtered = df[df[col].astype(str) == val]
                elif cond == "gt":     filtered = df[df[col].astype(float) > float(val)]
                elif cond == "lt":     filtered = df[df[col].astype(float) < float(val)]
                else:                  filtered = df[df[col].astype(str).str.contains(val, case=False, na=False)]
                result = f"Filtro '{col} {cond} {val}': {len(filtered)} filas\n{filtered.head(20).to_string()}"
                if save_out:
                    out_p = p.parent / f"{p.stem}_filtrado.csv"
                    filtered.to_csv(str(out_p), index=False)
                    result += f"\nGuardado en: {out_p.name}"
                return result
            except Exception as e:
                return f"Error filtrando: {e}"

        # ── SORT ──────────────────────────────────────────────────────────────
        elif action in ("sort", "ordenar"):
            col = parameters.get("column", df.columns[0])
            asc = parameters.get("ascending", True)
            if col not in df.columns:
                return f"Columna '{col}' no encontrada."
            sorted_df = df.sort_values(by=col, ascending=asc)
            result = sorted_df.head(20).to_string()
            if save_out:
                out_p = p.parent / f"{p.stem}_ordenado.csv"
                sorted_df.to_csv(str(out_p), index=False)
                return f"Ordenado por '{col}' ({'asc' if asc else 'desc'}):\n{result}\nGuardado en: {out_p.name}"
            return result

        # ── CONVERT ──────────────────────────────────────────────────────────
        elif action in ("convert", "convertir"):
            if not fmt: return "Especificá el formato de destino: csv o xlsx."
            if fmt == "csv":
                out_p = p.parent / f"{p.stem}.csv"
                df.to_csv(str(out_p), index=False)
                return f"Convertido a CSV: {out_p.name}"
            elif fmt in ("xlsx","excel"):
                out_p = p.parent / f"{p.stem}.xlsx"
                df.to_excel(str(out_p), index=False)
                return f"Convertido a Excel: {out_p.name}"
            return f"Formato '{fmt}' no soportado para hojas de cálculo."

        # ── DEFAULT: quick info ───────────────────────────────────────────────
        cols_str = ", ".join(df.columns.tolist()[:10])
        return (f"{name}: {rows} filas × {cols} columnas\n"
                f"Columnas: {cols_str}"
                + (" ..." if len(df.columns) > 10 else ""))

    # ══ AUDIO ═════════════════════════════════════════════════════════════════
    elif ftype == "audio":
        ffmpeg = shutil.which("ffmpeg")

        if action == "info":
            ffprobe = shutil.which("ffprobe") or shutil.which("ffmpeg")
            if ffprobe:
                ok, out = _run([ffprobe, "-v", "quiet", "-print_format", "json",
                                 "-show_format", "-show_streams", file_path], timeout=15)
                if ok:
                    try:
                        d = json.loads(out)
                        dur = float(d.get("format",{}).get("duration",0))
                        h,m,s = int(dur//3600), int((dur%3600)//60), int(dur%60)
                        bitrate = int(d.get("format",{}).get("bit_rate",0)) // 1000
                        return f"Audio: {name} | Duración: {h:02d}:{m:02d}:{s:02d} | Bitrate: {bitrate} kbps"
                    except Exception:
                        pass
            return f"Audio: {name} ({size_kb:.1f} KB)"

        elif action in ("convert", "convertir"):
            if not fmt: return "Especificá el formato de destino (mp3, wav, ogg, flac)."
            if not ffmpeg: return "ffmpeg no encontrado. Instalalo desde https://ffmpeg.org"
            out_p = p.parent / f"{p.stem}.{fmt}"
            ok, out = _run([ffmpeg, "-y", "-i", file_path, str(out_p)], timeout=120)
            return f"Audio convertido a {fmt}: {out_p.name}" if ok else f"Error: {out[:500]}"

        elif action in ("trim", "recortar"):
            if not ffmpeg: return "ffmpeg no encontrado."
            start = parameters.get("start", "0")
            end   = parameters.get("end", "30")
            out_p = p.parent / f"{p.stem}_recortado{ext}"
            ok, out = _run([ffmpeg, "-y", "-i", file_path,
                             "-ss", str(start), "-to", str(end), str(out_p)], timeout=60)
            return f"Audio recortado ({start}s→{end}s): {out_p.name}" if ok else f"Error: {out[:500]}"

        elif action in ("transcribe", "transcribir"):
            return ("Para transcripción de audio necesitás Whisper. "
                    "Instalalo con: pip install openai-whisper")

        return f"Acción '{action}' no reconocida para audio. Usa: info | convert | trim | transcribe"

    # ══ VIDEO ═════════════════════════════════════════════════════════════════
    elif ftype == "video":
        ffmpeg  = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe") or shutil.which("ffmpeg")

        if action == "info":
            if ffprobe:
                ok, out = _run([ffprobe, "-v", "quiet", "-print_format", "json",
                                 "-show_format", "-show_streams", file_path], timeout=15)
                if ok:
                    try:
                        d   = json.loads(out)
                        dur = float(d.get("format",{}).get("duration",0))
                        h,m,s = int(dur//3600), int((dur%3600)//60), int(dur%60)
                        size_mb = size_kb / 1024
                        streams = d.get("streams",[])
                        v = next((s for s in streams if s.get("codec_type")=="video"),{})
                        res = f"{v.get('width','?')}×{v.get('height','?')}" if v else "?"
                        return f"Video: {name} | {h:02d}:{m:02d}:{s:02d} | {res} | {size_mb:.1f} MB"
                    except Exception:
                        pass
            return f"Video: {name} ({size_kb/1024:.1f} MB)"

        elif action in ("extract_audio", "extraer_audio"):
            if not ffmpeg: return "ffmpeg no encontrado."
            out_p = p.parent / f"{p.stem}_audio.mp3"
            ok, out = _run([ffmpeg, "-y", "-i", file_path, "-vn", "-acodec", "mp3", str(out_p)], timeout=120)
            return f"Audio extraído: {out_p.name}" if ok else f"Error: {out[:500]}"

        elif action in ("extract_frame", "fotograma"):
            if not ffmpeg: return "ffmpeg no encontrado."
            ts  = parameters.get("timestamp", "00:00:05")
            out_p = p.parent / f"{p.stem}_frame.jpg"
            ok, out = _run([ffmpeg, "-y", "-i", file_path, "-ss", ts,
                             "-vframes", "1", str(out_p)], timeout=30)
            return f"Frame extraído en {ts}: {out_p.name}" if ok else f"Error: {out[:500]}"

        elif action in ("trim", "recortar"):
            if not ffmpeg: return "ffmpeg no encontrado."
            start = parameters.get("start", "0")
            end   = parameters.get("end", "30")
            out_p = p.parent / f"{p.stem}_recortado{ext}"
            ok, out = _run([ffmpeg, "-y", "-i", file_path,
                             "-ss", str(start), "-to", str(end),
                             "-c", "copy", str(out_p)], timeout=120)
            return f"Video recortado: {out_p.name}" if ok else f"Error: {out[:500]}"

        elif action in ("compress", "comprimir"):
            if not ffmpeg: return "ffmpeg no encontrado."
            quality = parameters.get("quality", 28)
            out_p   = p.parent / f"{p.stem}_comprimido.mp4"
            ok, out = _run([ffmpeg, "-y", "-i", file_path,
                             "-vcodec", "libx264", "-crf", str(quality),
                             "-preset", "fast", str(out_p)], timeout=300)
            if ok:
                new_mb = out_p.stat().st_size / (1024**2)
                return f"Video comprimido: {size_kb/1024:.1f} MB → {new_mb:.1f} MB → {out_p.name}"
            return f"Error: {out[:500]}"

        elif action in ("convert", "convertir"):
            if not fmt: return "Especificá el formato de destino."
            if not ffmpeg: return "ffmpeg no encontrado."
            out_p = p.parent / f"{p.stem}.{fmt}"
            ok, out = _run([ffmpeg, "-y", "-i", file_path, str(out_p)], timeout=300)
            return f"Video convertido a {fmt}: {out_p.name}" if ok else f"Error: {out[:500]}"

        return f"Acción '{action}' no reconocida para video. Usa: info | extract_audio | extract_frame | trim | compress | convert | transcribe"

    # ══ ARCHIVE ════════════════════════════════════════════════════════════════
    elif ftype == "archive":
        import zipfile, tarfile

        if action in ("list", "listar"):
            try:
                if ext == ".zip":
                    with zipfile.ZipFile(file_path, "r") as z:
                        names = z.namelist()
                elif ext in (".tar",".gz",".bz2"):
                    with tarfile.open(file_path, "r:*") as t:
                        names = t.getnames()
                else:
                    # 7z / rar via powershell
                    out = _ps(f"Get-Content '{file_path}' | head -50")
                    return f"Contenido de {name}:\n{out}"
                lines = [f"  {n}" for n in names[:50]]
                extra = f"\n  ... y {len(names)-50} más" if len(names) > 50 else ""
                return f"{name} contiene {len(names)} archivos:\n" + "\n".join(lines) + extra
            except Exception as e:
                return f"Error listando archivo: {e}"

        elif action in ("extract", "extraer"):
            dest = parameters.get("destination", str(p.parent / p.stem))
            os.makedirs(dest, exist_ok=True)
            try:
                if ext == ".zip":
                    with zipfile.ZipFile(file_path, "r") as z:
                        z.extractall(dest)
                elif ext in (".tar",".gz",".bz2"):
                    with tarfile.open(file_path, "r:*") as t:
                        t.extractall(dest)
                else:
                    return f"Para extraer {ext} necesitás 7-Zip instalado."
                return f"Extraído en: {dest}"
            except Exception as e:
                return f"Error extrayendo: {e}"

        return f"Acción '{action}' no reconocida para archivos comprimidos. Usa: list | extract"

    # ══ CUSTOM INSTRUCTION (any type) ════════════════════════════════════════
    if instruction:
        content, _ = _read_content(file_path)
        prompt = f"{instruction}\n\n[Archivo: {name}]\n{content[:8000]}"
        return _ai(prompt)

    return (f"Archivo '{name}' (tipo: {ftype}). "
            f"Especificá una acción: summarize | translate | fix | explain | word_count | info | etc.")
