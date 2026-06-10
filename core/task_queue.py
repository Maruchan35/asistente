"""
core/task_queue.py — Cola de tareas asíncronas para JARVIS.

Cuando el usuario pide algo largo ("investiga X y créame un PDF de 20 páginas"),
JARVIS no debe quedarse bloqueado. Esta cola permite:

  • Submit en background (devuelve un task_id inmediato)
  • Consultar estado: pending / running / done / failed
  • Notificación callback al terminar (para sonido + holograma flash)
  • Pregunta "¿en qué vas?" durante la ejecución

Uso desde main.py:
    from core.task_queue import submit, get_task, list_tasks, set_notify_callback

    set_notify_callback(lambda task: ui.flash_hologram(task.title))
    tid = submit("Investigar X", target=lambda: heavy_function(...))
    # ...más tarde...
    t = get_task(tid)
    if t.status == "done":
        print(t.result)
"""
from __future__ import annotations
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from core.jarvis_logger import log_info, log_error
except Exception:
    def log_info(*a, **k): pass
    def log_error(*a, **k): pass


@dataclass
class Task:
    id:           str
    title:        str
    status:       str = "pending"      # pending | running | done | failed | cancelled
    progress:     str = ""             # texto descriptivo del estado actual
    result:       Any = None
    error:        str | None = None
    submitted_at: float = field(default_factory=time.time)
    started_at:   float | None = None
    finished_at:  float | None = None
    cancel_flag:  threading.Event = field(default_factory=threading.Event)

    def duration_s(self) -> float:
        end = self.finished_at or time.time()
        start = self.started_at or self.submitted_at
        return end - start

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "title":        self.title,
            "status":       self.status,
            "progress":     self.progress,
            "duration_s":   round(self.duration_s(), 1),
            "submitted_at": self.submitted_at,
            "started_at":   self.started_at,
            "finished_at":  self.finished_at,
            "error":        self.error,
            "result_kind":  type(self.result).__name__ if self.result is not None else None,
        }


# ── Estado global ─────────────────────────────────────────────────────────────
_tasks: dict[str, Task] = {}
_lock  = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="JarvisTask")
_notify_callback: Callable[[Task], None] | None = None


def set_notify_callback(cb: Callable[[Task], None] | None) -> None:
    """Define qué hacer cuando una tarea termina (ej. flashear holograma)."""
    global _notify_callback
    _notify_callback = cb


def submit(title: str, target: Callable[..., Any], *args, **kwargs) -> str:
    """
    Envia una tarea al background. `target` puede ser sync o async.
    Devuelve task_id inmediatamente.
    """
    task = Task(id=str(uuid.uuid4())[:8], title=title)
    with _lock:
        _tasks[task.id] = task
    log_info(f"Task submitted: {title}", category="system",
             task_id=task.id)

    def _runner():
        with _lock:
            task.status      = "running"
            task.started_at  = time.time()
        try:
            # Pasamos el task como kwarg si la función lo acepta
            import inspect
            sig = inspect.signature(target)
            if "task" in sig.parameters:
                kwargs["task"] = task

            result = target(*args, **kwargs)
            # Si es coroutine, ejecutar en loop nuevo
            import asyncio
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)

            with _lock:
                if task.cancel_flag.is_set():
                    task.status = "cancelled"
                else:
                    task.result = result
                    task.status = "done"
                task.finished_at = time.time()
            log_info(f"Task done: {title} ({task.duration_s():.1f}s)",
                     category="system", task_id=task.id)
        except Exception as e:
            with _lock:
                task.status      = "failed"
                task.error       = f"{type(e).__name__}: {e}"
                task.finished_at = time.time()
            log_error(f"Task failed: {title}", exc=e, task_id=task.id)
        finally:
            # Notificar al UI
            if _notify_callback:
                try:
                    _notify_callback(task)
                except Exception:
                    pass

    _executor.submit(_runner)
    return task.id


def get_task(task_id: str) -> Task | None:
    with _lock:
        return _tasks.get(task_id)


def list_tasks(status: str | None = None, limit: int = 20) -> list[Task]:
    """Listar tareas, opcionalmente filtradas por estado."""
    with _lock:
        items = list(_tasks.values())
    items.sort(key=lambda t: t.submitted_at, reverse=True)
    if status:
        items = [t for t in items if t.status == status]
    return items[:limit]


def cancel(task_id: str) -> bool:
    """Pedir cancelación cooperativa (la tarea debe revisar task.cancel_flag)."""
    t = get_task(task_id)
    if not t:
        return False
    if t.status not in ("pending", "running"):
        return False
    t.cancel_flag.set()
    return True


def update_progress(task_id: str, text: str) -> None:
    """Las tareas pueden reportar progreso descriptivo."""
    t = get_task(task_id)
    if t:
        t.progress = text


def cleanup_old(max_age_s: int = 3600) -> int:
    """Borrar tareas terminadas hace más de N segundos. Devuelve cuántas borró."""
    now = time.time()
    removed = 0
    with _lock:
        for tid in list(_tasks.keys()):
            t = _tasks[tid]
            if t.status in ("done", "failed", "cancelled"):
                if t.finished_at and (now - t.finished_at) > max_age_s:
                    del _tasks[tid]
                    removed += 1
    return removed


def summary_for_voice() -> str:
    """Genera un resumen hablado del estado de tareas para responder "¿en qué vas?"."""
    with _lock:
        running   = [t for t in _tasks.values() if t.status == "running"]
        done_recent = [t for t in _tasks.values()
                       if t.status == "done"
                       and t.finished_at and (time.time() - t.finished_at) < 60]
    if not running and not done_recent:
        return "Sin tareas en curso, señor."
    parts = []
    if running:
        parts.append(f"{len(running)} en progreso: " +
                     "; ".join(f"{t.title} ({int(t.duration_s())}s)" for t in running[:3]))
    if done_recent:
        parts.append(f"{len(done_recent)} terminadas hace poco")
    return ". ".join(parts) + "."
