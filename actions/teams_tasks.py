# -*- coding: utf-8 -*-
"""
teams_tasks.py — JARVIS lee las tareas asignadas en Microsoft Teams,
las lista, y HACE las fáciles dejándolas listas (sin entregarlas) en una
carpeta local "Tareas Teams".

Flujo (igual patrón que WhatsApp: usa la web vía visión, sin API de Azure):
  scan        → el usuario está en la sección "Tareas/Assignments" de Teams.
                JARVIS captura la pantalla, extrae con visión cada tarea
                (título, materia, descripción, fecha de entrega) y las guarda
                en config/teams_tasks.json. Devuelve la lista.
  list        → muestra las tareas guardadas con su estado (pendiente/hecha).
  do          → toma UNA tarea (por número o título), evalúa si es "fácil"
                (redacción/investigación/resumen/documento) y la genera con
                document_creator o deep_research, guardándola en
                ~/Documents/Tareas Teams/. La marca como hecha. NO la entrega.
  do_all_easy → hace TODAS las tareas fáciles pendientes de una vez.

Las tareas "difíciles" (exámenes interactivos, subir algo específico,
presentaciones, código que debe correr) se listan pero NO se hacen solas —
JARVIS avisa que requieren al usuario.
"""
from __future__ import annotations
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

_BASE   = Path(__file__).resolve().parent.parent
_STORE  = _BASE / "config" / "teams_tasks.json"
_FOLDER = Path(os.path.expanduser("~")) / "Documents" / "Tareas Teams"


# ── Persistencia ──────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(tasks: list[dict]) -> None:
    try:
        from core.safe_json import safe_write
        safe_write(_STORE, tasks)
    except Exception:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")


def _llm(prompt: str, system: str, max_tokens: int = 1500) -> str:
    from actions.deep_research import _llm_call
    return _llm_call(prompt, max_tokens=max_tokens, system=system)


# ── SCAN: leer las tareas de Teams con visión ─────────────────────────────────

_SCAN_Q = (
    "Estás viendo Microsoft Teams en la sección de Tareas/Assignments. "
    "Lista TODAS las tareas asignadas visibles en formato EXACTO, una por línea:\n"
    "TAREA|||<título>|||<materia o equipo>|||<fecha de entrega si aparece>|||<descripción breve>\n"
    "Si no hay descripción visible, deja ese campo vacío pero conserva los separadores |||. "
    "Si NO ves ninguna tarea o no es la pantalla de Teams, responde EXACTAMENTE: SIN_TAREAS. "
    "Solo la lista, sin comentarios."
)


def _parse_vision(raw: str) -> list[dict]:
    found = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line.upper().startswith("TAREA"):
            continue
        parts = [p.strip() for p in line.split("|||")]
        if len(parts) < 2:
            continue
        fields = parts[1:]
        found.append({
            "titulo":      fields[0] if len(fields) > 0 else "Sin título",
            "materia":     fields[1] if len(fields) > 1 else "",
            "entrega":     fields[2] if len(fields) > 2 else "",
            "descripcion": fields[3] if len(fields) > 3 else "",
        })
    return found


def _activate_teams() -> bool:
    """Traer la ventana de Teams (app o web) al frente. True si la encontró."""
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            t = (w.title or "").lower()
            if "teams" in t or ("microsoft" in t and "teams" in t):
                try:
                    if w.isMinimized: w.restore()
                    w.activate()
                    time.sleep(1.0)
                except Exception:
                    pass
                return True
    except Exception:
        pass
    return False


def _scan(player=None, scroll_passes: int = 4) -> list[dict]:
    """Capturar Teams con SCROLL automático para leer TODAS las tareas, no solo
    las visibles. Hace varias capturas bajando la página y fusiona sin duplicar."""
    from actions.screen_vision import screen_vision
    try:
        import pyautogui
    except ImportError:
        pyautogui = None

    _activate_teams()
    seen: dict[str, dict] = {}

    for i in range(max(1, scroll_passes)):
        raw = screen_vision({"action": "question", "question": _SCAN_Q}, player=player)
        for t in _parse_vision(raw):
            key = t["titulo"].lower().strip()
            if key and key not in seen:
                seen[key] = t
        # Scroll hacia abajo para revelar más tareas (excepto en la última pasada)
        if pyautogui and i < scroll_passes - 1:
            try:
                # Mover el cursor al centro del área de tareas antes de scrollear
                import mss
                with mss.mss() as sct:
                    mon = sct.monitors[0]
                    pyautogui.moveTo(mon["width"] // 2, mon["height"] // 2)
                pyautogui.scroll(-600)   # negativo = hacia abajo
                time.sleep(1.2)
            except Exception:
                break
    # Volver arriba para dejar Teams como estaba
    if pyautogui:
        try:
            pyautogui.scroll(2400)
        except Exception:
            pass
    return list(seen.values())


def _read_detail(task: dict, player=None) -> str:
    """ENTRAR a una tarea (click en su título) y leer el detalle completo con
    visión: indicaciones, rúbrica, archivos adjuntos, fecha. Devuelve el texto.
    Luego vuelve atrás. Mejora la calidad de las tareas que JARVIS genera."""
    from actions.screen_vision import screen_vision
    try:
        import pyautogui
    except ImportError:
        pyautogui = None

    _activate_teams()
    # 1. Click en el título de la tarea para abrirla
    try:
        from actions.visual_click import visual_click
        visual_click({"element_description": f"la tarea titulada '{task['titulo']}'"}, player=player)
        time.sleep(2.0)
    except Exception as e:
        if player:
            try: player.write_log(f"⚠️ No pude abrir la tarea con clic: {e}")
            except Exception: pass
        return ""

    # 2. Leer el detalle completo
    detail_q = (
        f"Estás viendo el detalle de la tarea '{task['titulo']}' en Teams. "
        "Transcribe TODAS las indicaciones, instrucciones, criterios/rúbrica, "
        "puntos requeridos y fecha de entrega que veas. Si hay archivos adjuntos "
        "o recursos, menciónalos. Solo el contenido, sin comentarios."
    )
    detail = screen_vision({"action": "question", "question": detail_q}, player=player) or ""

    # 3. Volver a la lista (Escape o botón atrás)
    if pyautogui:
        try:
            pyautogui.press("escape")
            time.sleep(0.8)
        except Exception:
            pass
    return detail.strip()


def _merge_tasks(new_tasks: list[dict]) -> list[dict]:
    """Fusionar tareas nuevas con las guardadas, sin duplicar por título."""
    existing = _load()
    by_title = {t["titulo"].lower().strip(): t for t in existing}
    for nt in new_tasks:
        key = nt["titulo"].lower().strip()
        if key not in by_title:
            nt["estado"] = "pendiente"
            nt["dificultad"] = ""        # se evalúa al hacerla
            nt["archivo"] = ""
            nt["agregada"] = datetime.now().isoformat(timespec="seconds")
            existing.append(nt)
            by_title[key] = nt
    _save(existing)
    return existing


# ── Clasificar dificultad ─────────────────────────────────────────────────────

def _classify(task: dict) -> tuple[str, str]:
    """¿La tarea es 'facil' (JARVIS la puede hacer) o 'dificil'? Devuelve
    (dificultad, tipo) donde tipo ∈ documento/investigacion/resumen/otro."""
    system = (
        "Clasificas tareas escolares según si una IA con herramientas de "
        "generación de documentos Word e investigación web puede COMPLETARLAS "
        "por su cuenta. Respondes SOLO un JSON: "
        '{"dificultad": "facil"|"dificil", "tipo": "documento"|"investigacion"|"resumen"|"otro", '
        '"motivo": "..."}\n'
        "FÁCIL = ensayo, redacción, informe, investigación, resumen, análisis, "
        "monografía, cuestionario teórico (texto que se puede escribir).\n"
        "DIFÍCIL = examen interactivo en línea, subir foto/video propio, "
        "presentación con diseño, código que debe ejecutarse y probarse, "
        "trabajo en grupo, algo que requiere materiales físicos."
    )
    user = (f"Título: {task.get('titulo')}\nMateria: {task.get('materia')}\n"
            f"Descripción: {task.get('descripcion')}\n\nClasifica.")
    try:
        raw = _llm(user, system, max_tokens=300).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        data = json.loads(raw)
        return data.get("dificultad", "dificil"), data.get("tipo", "otro")
    except Exception:
        return "dificil", "otro"


# ── Hacer una tarea fácil ─────────────────────────────────────────────────────

def _safe_filename(text: str) -> str:
    return re.sub(r'[^\w\s-]', '', text).strip().replace(" ", "_")[:60] or "Tarea"


def _do_task(task: dict, player=None) -> dict:
    """Generar el entregable de una tarea fácil en la carpeta Tareas Teams.
    Devuelve el task actualizado."""
    _FOLDER.mkdir(parents=True, exist_ok=True)
    dificultad, tipo = _classify(task)
    task["dificultad"] = dificultad

    if dificultad != "facil":
        task["estado"] = "requiere_usuario"
        return task

    titulo = task.get("titulo", "Tarea")
    materia = task.get("materia", "")
    desc = task.get("descripcion", "")

    # ENTRAR a la tarea para leer el detalle completo (indicaciones, rúbrica) —
    # mejora muchísimo la calidad de lo que JARVIS genera vs solo el título.
    if not task.get("detalle"):
        try:
            detalle = _read_detail(task, player)
            if detalle:
                task["detalle"] = detalle
                desc = (desc + "\n\n" + detalle).strip() if desc else detalle
        except Exception:
            pass
    else:
        desc = (desc + "\n\n" + task["detalle"]).strip()

    topic = f"{titulo}" + (f" — {desc[:200]}" if desc else "")
    safe_title = _safe_filename(titulo)

    if player:
        try: player.write_log(f"📝 Haciendo tarea: {titulo[:40]} ({tipo})")
        except Exception: pass

    try:
        if tipo == "investigacion":
            # Investigación profunda → documento Word (síncrono para tenerlo ya)
            from actions.deep_research import deep_research
            res = deep_research({
                "topic": topic, "target_pages": 5, "norm": "professional",
                "title": safe_title, "save_path": str(_FOLDER),
                "background": False,
                "cover": json.dumps({"title": titulo, "institution": materia,
                                     "authors": "", "date": datetime.now().strftime("%B %Y")}),
            }, player=player)
        else:
            # Documento/ensayo/resumen → generar contenido con LLM + Word
            system = (
                "Eres un estudiante que redacta tareas escolares completas, bien "
                "estructuradas y con buena ortografía, en español. Usas markdown: "
                "# título, ## secciones, párrafos desarrollados, listas con -."
            )
            user = (
                f"Redacta COMPLETA esta tarea para entregar:\n"
                f"Título: {titulo}\nMateria: {materia}\n"
                f"Indicaciones: {desc or 'desarrolla el tema de forma completa y ordenada'}\n\n"
                "Devuelve el contenido en markdown, listo para un documento Word. "
                "Incluye introducción, desarrollo y conclusión donde aplique."
            )
            contenido = _llm(user, system, max_tokens=3500)
            from actions.document_creator import document_creator
            res = document_creator({
                "action": "word", "norm": "professional",
                "title": safe_title, "save_path": str(_FOLDER), "toc": False,
                "cover": json.dumps({"title": titulo, "institution": materia,
                                     "authors": "", "date": datetime.now().strftime("%B %Y")}),
                "content": contenido,
            }, player=player)

        # Extraer ruta del archivo del resultado
        m = re.search(r"'([^']+\.docx)'", str(res))
        task["archivo"] = str(_FOLDER / m.group(1)) if m else str(_FOLDER)
        task["estado"] = "hecha"
        task["hecha_en"] = datetime.now().isoformat(timespec="seconds")
        try:
            from core.autonomy import audit
            audit("teams_task", f"Tarea hecha: {titulo[:50]}", task["archivo"])
        except Exception:
            pass
    except Exception as e:
        task["estado"] = "error"
        task["error"] = str(e)[:150]
    return task


# ── Entry point ───────────────────────────────────────────────────────────────

def teams_tasks(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "scan").lower()

    # ── SCAN ──────────────────────────────────────────────────────────────────
    if action == "scan":
        nuevas = _scan(player)
        if not nuevas:
            return ("No vi tareas en la pantalla. Abre Microsoft Teams en la "
                    "sección de 'Tareas' (Assignments) con la lista visible y "
                    "vuelve a pedírmelo.")
        all_tasks = _merge_tasks(nuevas)
        pend = [t for t in all_tasks if t.get("estado") == "pendiente"]
        lines = [f"Detecté {len(nuevas)} tarea(s), {len(pend)} pendiente(s):"]
        for i, t in enumerate(all_tasks, 1):
            est = t.get("estado", "pendiente")
            mark = {"hecha": "✓", "pendiente": "○", "requiere_usuario": "⚠",
                    "error": "✗"}.get(est, "·")
            entrega = f" (entrega {t['entrega']})" if t.get("entrega") else ""
            lines.append(f"  {i}. {mark} {t['titulo']}{entrega}")
        lines.append("\nDi 'haz las tareas fáciles' y las dejo listas en "
                     "Documentos/Tareas Teams para que las revises y subas.")
        return "\n".join(lines)

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action == "list":
        tasks = _load()
        if not tasks:
            return "No tengo tareas guardadas. Pídeme 'escanea las tareas de Teams' primero."
        lines = ["Tareas de Teams:"]
        for i, t in enumerate(tasks, 1):
            est = t.get("estado", "pendiente")
            mark = {"hecha": "✓ HECHA", "pendiente": "○ pendiente",
                    "requiere_usuario": "⚠ requiere ti", "error": "✗ error"}.get(est, est)
            lines.append(f"  {i}. [{mark}] {t['titulo']}"
                         + (f"  → {t['archivo']}" if t.get("archivo") else ""))
        return "\n".join(lines)

    # ── DO (una tarea) ────────────────────────────────────────────────────────
    if action == "do":
        tasks = _load()
        if not tasks:
            return "No hay tareas guardadas. Escanéalas primero con 'escanea Teams'."
        idx = parameters.get("index")
        title_q = (parameters.get("title") or "").lower().strip()
        target = None
        if idx is not None:
            try:
                target = tasks[int(idx) - 1]
            except Exception:
                return f"No existe la tarea número {idx}."
        elif title_q:
            target = next((t for t in tasks if title_q in t["titulo"].lower()), None)
        else:
            target = next((t for t in tasks if t.get("estado") == "pendiente"), None)
        if target is None:
            return "No encontré esa tarea."

        updated = _do_task(target, player)
        # Persistir
        for i, t in enumerate(tasks):
            if t["titulo"] == updated["titulo"]:
                tasks[i] = updated
        _save(tasks)

        if updated["estado"] == "hecha":
            return (f"Tarea '{updated['titulo']}' lista en Documentos/Tareas Teams "
                    f"({Path(updated['archivo']).name}). Revísala antes de entregarla, señor.")
        if updated["estado"] == "requiere_usuario":
            return (f"La tarea '{updated['titulo']}' es de las que requieren tu "
                    "intervención (examen, subir algo propio, etc.) — la dejé marcada, "
                    "no la puedo hacer solo.")
        return f"No pude completar '{updated['titulo']}': {updated.get('error','')}"

    # ── DO ALL EASY ───────────────────────────────────────────────────────────
    if action in ("do_all_easy", "do_all", "hacer_faciles"):
        tasks = _load()
        pend = [t for t in tasks if t.get("estado") == "pendiente"]
        if not pend:
            return "No hay tareas pendientes por hacer."
        hechas, requieren, errores = [], [], []
        for t in pend:
            updated = _do_task(t, player)
            for i, orig in enumerate(tasks):
                if orig["titulo"] == updated["titulo"]:
                    tasks[i] = updated
            if updated["estado"] == "hecha":
                hechas.append(updated["titulo"])
            elif updated["estado"] == "requiere_usuario":
                requieren.append(updated["titulo"])
            else:
                errores.append(updated["titulo"])
        _save(tasks)
        parts = []
        if hechas:
            parts.append(f"Dejé listas {len(hechas)} tarea(s) en Documentos/Tareas Teams: "
                         + ", ".join(hechas))
        if requieren:
            parts.append(f"{len(requieren)} requieren tu intervención: " + ", ".join(requieren))
        if errores:
            parts.append(f"{len(errores)} fallaron")
        return ". ".join(parts) + ". Revisa los documentos antes de entregarlos, señor."

    return (f"Acción '{action}' no reconocida. Usa: scan | list | do | do_all_easy.")
