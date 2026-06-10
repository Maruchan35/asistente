"""goals.py — Full goal & progress tracker with deadlines, steps, completion."""
from __future__ import annotations
import json, time, uuid
from datetime import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
GOALS_PATH = BASE_DIR / "config" / "goals.json"

def _load() -> list[dict]:
    if not GOALS_PATH.exists():
        return []
    try:
        data = json.loads(GOALS_PATH.read_text(encoding="utf-8"))
        # Legacy: plain list of strings
        if data and isinstance(data[0], str):
            return [{"id": str(i+1), "text": g, "done": False, "steps": [], "created": ""} for i, g in enumerate(data)]
        return data
    except Exception:
        return []

def _save(goals: list[dict]) -> None:
    try:
        from core.safe_json import safe_write
        safe_write(GOALS_PATH, goals)
    except ImportError:
        GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOALS_PATH.write_text(json.dumps(goals, indent=2, ensure_ascii=False), encoding="utf-8")

def _short_id(full_id: str) -> str:
    return str(full_id)[:4].upper()

def _find(goals: list[dict], goal_id: str) -> dict | None:
    gid = goal_id.strip().upper()
    return next((g for g in goals if _short_id(g["id"]) == gid or str(g["id"]) == goal_id), None)

# ══════════════════════════════════════════════════════════════════════════════
def goals(parameters: dict, player=None) -> str:
    action = parameters.get("action", "list").lower().strip()

    def log(msg):
        if player: player.write_log(f"🎯 {msg}")

    # ── LIST ─────────────────────────────────────────────────────────────────
    if action in ("list", "listar", "mostrar"):
        items = _load()
        if not items:
            return "No tenés objetivos activos definidos, señor."
        lines = ["Objetivos activos:"]
        for g in items:
            done   = "✅" if g.get("done") else "⬜"
            dline  = f" (límite: {g['deadline']})" if g.get("deadline") else ""
            steps  = g.get("steps", [])
            done_s = sum(1 for s in steps if s.get("done"))
            prog   = f" [{done_s}/{len(steps)} pasos]" if steps else ""
            lines.append(f"  {done} [{_short_id(g['id'])}] {g['text']}{dline}{prog}")
        return "\n".join(lines)

    # ── ADD ───────────────────────────────────────────────────────────────────
    elif action in ("add", "create", "agregar", "crear", "nuevo"):
        text     = parameters.get("goal", parameters.get("text", "")).strip()
        deadline = parameters.get("deadline", "").strip()
        if not text:
            return "Necesito el texto del objetivo, señor."
        items = _load()
        new = {
            "id":       str(uuid.uuid4())[:8],
            "text":     text,
            "done":     False,
            "steps":    [],
            "deadline": deadline,
            "created":  datetime.now().strftime("%Y-%m-%d"),
            "progress": 0,
        }
        items.append(new)
        _save(items)
        dl = f" (fecha límite: {deadline})" if deadline else ""
        msg = f"Objetivo agregado: '{text}'{dl}."
        log(msg); return msg

    # ── COMPLETE ─────────────────────────────────────────────────────────────
    elif action in ("complete", "completar", "done", "finish", "terminar"):
        goal_id = str(parameters.get("goal_id", parameters.get("id", ""))).strip()
        items   = _load()
        g       = _find(items, goal_id)
        if not g:
            return f"No encontré objetivo con ID '{goal_id}'."
        g["done"]       = True
        g["completed"]  = datetime.now().strftime("%Y-%m-%d")
        g["progress"]   = 100
        for s in g.get("steps", []):
            s["done"] = True
        _save(items)
        msg = f"¡Objetivo '{g['text']}' completado! Felicitaciones."
        log(msg); return msg

    # ── DELETE ────────────────────────────────────────────────────────────────
    elif action in ("delete", "remove", "eliminar", "borrar"):
        goal_id = str(parameters.get("goal_id", parameters.get("id", ""))).strip()
        items   = _load()
        g       = _find(items, goal_id)
        if not g:
            return f"No encontré objetivo con ID '{goal_id}'."
        items = [x for x in items if x["id"] != g["id"]]
        _save(items)
        msg = f"Objetivo '{g['text']}' eliminado."
        log(msg); return msg

    # ── UPDATE PROGRESS ──────────────────────────────────────────────────────
    elif action in ("update", "progress", "progreso", "actualizar"):
        goal_id  = str(parameters.get("goal_id", parameters.get("id", ""))).strip()
        progress = int(parameters.get("progress", parameters.get("value", 50)))
        note     = parameters.get("note", "").strip()
        items    = _load()
        g        = _find(items, goal_id)
        if not g:
            return f"No encontré objetivo con ID '{goal_id}'."
        g["progress"] = max(0, min(100, progress))
        if note:
            g.setdefault("notes", []).append(
                {"date": datetime.now().strftime("%Y-%m-%d"), "note": note}
            )
        if progress >= 100:
            g["done"] = True
        _save(items)
        msg = f"Objetivo '{g['text']}' actualizado al {progress}%."
        log(msg); return msg

    # ── ADD STEP ─────────────────────────────────────────────────────────────
    elif action in ("add_step", "step", "paso", "agregar_paso"):
        goal_id  = str(parameters.get("goal_id", parameters.get("id", ""))).strip()
        step_txt = parameters.get("step", parameters.get("text", "")).strip()
        if not step_txt:
            return "Necesito el texto del paso."
        items = _load()
        g     = _find(items, goal_id)
        if not g:
            return f"No encontré objetivo con ID '{goal_id}'."
        g.setdefault("steps", []).append({"text": step_txt, "done": False})
        _save(items)
        msg = f"Paso '{step_txt}' agregado al objetivo '{g['text']}'."
        log(msg); return msg

    # ── COMPLETE STEP ─────────────────────────────────────────────────────────
    elif action in ("complete_step", "done_step", "completar_paso"):
        goal_id  = str(parameters.get("goal_id", parameters.get("id", ""))).strip()
        step_num = int(parameters.get("step_number", parameters.get("step", 1))) - 1
        items    = _load()
        g        = _find(items, goal_id)
        if not g:
            return f"No encontré objetivo con ID '{goal_id}'."
        steps = g.get("steps", [])
        if 0 <= step_num < len(steps):
            steps[step_num]["done"] = True
            done_count = sum(1 for s in steps if s.get("done"))
            g["progress"] = int(done_count / len(steps) * 100) if steps else 0
            _save(items)
            return f"Paso {step_num+1} completado en '{g['text']}'. Progreso: {g['progress']}%."
        return f"Paso {step_num+1} no encontrado (el objetivo tiene {len(steps)} pasos)."

    # ── DETAIL ───────────────────────────────────────────────────────────────
    elif action in ("detail", "ver", "detalle", "show"):
        goal_id = str(parameters.get("goal_id", parameters.get("id", ""))).strip()
        items   = _load()
        g       = _find(items, goal_id)
        if not g:
            return f"No encontré objetivo con ID '{goal_id}'."
        lines = [
            f"Objetivo: {g['text']}",
            f"Estado: {'Completado ✅' if g.get('done') else 'En progreso ⬜'}",
            f"Progreso: {g.get('progress', 0)}%",
        ]
        if g.get("deadline"):
            lines.append(f"Fecha límite: {g['deadline']}")
        if g.get("created"):
            lines.append(f"Creado: {g['created']}")
        if g.get("steps"):
            lines.append("Pasos:")
            for i, s in enumerate(g["steps"], 1):
                mark = "✅" if s.get("done") else "⬜"
                lines.append(f"  {mark} {i}. {s['text']}")
        if g.get("notes"):
            lines.append("Notas:")
            for n in g["notes"][-3:]:
                lines.append(f"  {n['date']}: {n['note']}")
        return "\n".join(lines)

    return f"Acción '{action}' no reconocida. Usa: list | add | complete | delete | update | add_step | complete_step | detail"
