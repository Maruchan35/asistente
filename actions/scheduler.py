"""scheduler.py — Real persistent task scheduler using Windows Task Scheduler
(schtasks) + a JSON registry of JARVIS-managed tasks."""
from __future__ import annotations
import json, os, subprocess, uuid, threading
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
TASKS_FILE = BASE_DIR / "config" / "scheduled_tasks.json"
_lock      = threading.Lock()

# ── Persistence helpers ───────────────────────────────────────────────────────
def _load() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    try:
        return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save(tasks: list[dict]) -> None:
    try:
        from core.safe_json import safe_write
        safe_write(TASKS_FILE, tasks)
    except ImportError:
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")

def _short_id(full_id: str) -> str:
    return full_id[:6].upper()

# ── Windows Task Scheduler helpers ───────────────────────────────────────────
def _schtasks(args: list[str]) -> tuple[bool, str]:
    """Run schtasks.exe, returns (success, output)."""
    try:
        r = subprocess.run(
            ["schtasks"] + args,
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        ok = r.returncode == 0
        return ok, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)

def _register_windows_task(task: dict) -> tuple[bool, str]:
    """Register the task in Windows Task Scheduler."""
    tid       = task["id"]
    name      = task["name"]
    freq      = task.get("frequency", "daily")
    hour      = int(task.get("hour", 8))
    minute    = int(task.get("minute", 0))
    weekday   = task.get("weekday", "MON")
    interval  = int(task.get("interval_minutes", 60))

    # Build the action: run a Python script that calls back to JARVIS memory
    action_script = BASE_DIR / "core" / "scheduler_runner.py"
    python_exe    = Path(subprocess.check_output(
        ["python", "-c", "import sys; print(sys.executable)"],
        text=True, creationflags=subprocess.CREATE_NO_WINDOW
    ).strip())

    start_time = f"{hour:02d}:{minute:02d}"

    if freq == "daily":
        ok, out = _schtasks([
            "/Create", "/F",
            "/TN", f"JARVIS\\{tid}",
            "/TR", f'"{python_exe}" "{action_script}" --task-id {tid}',
            "/SC", "DAILY",
            "/ST", start_time,
        ])
    elif freq == "weekly":
        ok, out = _schtasks([
            "/Create", "/F",
            "/TN", f"JARVIS\\{tid}",
            "/TR", f'"{python_exe}" "{action_script}" --task-id {tid}',
            "/SC", "WEEKLY",
            "/D", weekday.upper()[:3],
            "/ST", start_time,
        ])
    elif freq == "interval":
        ok, out = _schtasks([
            "/Create", "/F",
            "/TN", f"JARVIS\\{tid}",
            "/TR", f'"{python_exe}" "{action_script}" --task-id {tid}',
            "/SC", "MINUTE",
            "/MO", str(interval),
        ])
    elif freq == "once":
        run_date = task.get("run_date", datetime.now().strftime("%Y-%m-%d"))
        ok, out = _schtasks([
            "/Create", "/F",
            "/TN", f"JARVIS\\{tid}",
            "/TR", f'"{python_exe}" "{action_script}" --task-id {tid}',
            "/SC", "ONCE",
            "/SD", run_date,
            "/ST", start_time,
        ])
    else:
        return False, f"Frecuencia '{freq}' no soportada."

    return ok, out

def _delete_windows_task(tid: str) -> tuple[bool, str]:
    return _schtasks(["/Delete", "/F", "/TN", f"JARVIS\\{tid}"])

def _run_windows_task_now(tid: str) -> tuple[bool, str]:
    return _schtasks(["/Run", "/TN", f"JARVIS\\{tid}"])

# ── Also create the scheduler_runner.py helper ───────────────────────────────
def _ensure_runner():
    runner = BASE_DIR / "core" / "scheduler_runner.py"
    if runner.exists():
        return
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text('''"""scheduler_runner.py — Executed by Windows Task Scheduler for JARVIS tasks."""
import sys, json, subprocess
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
TASKS_FILE = BASE_DIR / "config" / "scheduled_tasks.json"

def main():
    if "--task-id" not in sys.argv:
        print("Usage: scheduler_runner.py --task-id <id>")
        return
    idx = sys.argv.index("--task-id")
    tid = sys.argv[idx + 1]
    try:
        tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    task = next((t for t in tasks if t["id"] == tid), None)
    if not task:
        print(f"Task {tid} not found.")
        return
    action     = task.get("task_action", "notify")
    params     = task.get("task_parameters", {})
    task_name  = task.get("name", tid)
    print(f"[JARVIS Scheduler] Running: {task_name} | Action: {action}")
    if action == "notify":
        msg = params.get("message", f"Tarea programada: {task_name}")
        subprocess.Popen([
            "powershell", "-NoProfile", "-Command",
            f"Add-Type -AssemblyName System.Windows.Forms; "
            f"[System.Windows.Forms.MessageBox]::Show(\\"{msg}\\", \\"JARVIS\\")"
        ])
    elif action == "backup":
        src = params.get("source", "")
        dst = params.get("destination", "")
        if src and dst:
            import shutil, os
            os.makedirs(dst, exist_ok=True)
            ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copytree(src, os.path.join(dst, f"backup_{ts}"),
                           dirs_exist_ok=True)
            print(f"Backup: {src} → {dst}")
    elif action == "custom_script":
        script = params.get("script", "")
        if script:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", script])
    print(f"[JARVIS Scheduler] Done: {task_name}")

if __name__ == "__main__":
    main()
''', encoding="utf-8")

# ══════════════════════════════════════════════════════════════════════════════
def scheduler(parameters: dict, player=None, speak=None) -> str:
    action = parameters.get("action", "list").lower().strip()

    def log(msg):
        if player: player.write_log(f"🕐 {msg}")

    _ensure_runner()

    # ── LIST ─────────────────────────────────────────────────────────────────
    if action == "list":
        with _lock:
            tasks = _load()
        if not tasks:
            return "No hay tareas programadas en JARVIS."
        lines = ["Tareas programadas:"]
        for t in tasks:
            freq = t.get("frequency","?")
            h    = t.get("hour","?")
            m    = t.get("minute","?")
            st   = "✅" if t.get("enabled", True) else "⏸"
            lines.append(
                f"  {st} [{_short_id(t['id'])}] {t['name']} — "
                f"{freq} a las {h:02}:{m:02} | acción: {t.get('task_action','?')}"
            )
        return "\n".join(lines)

    # ── CREATE ────────────────────────────────────────────────────────────────
    elif action == "create":
        name       = parameters.get("name", "Tarea sin nombre")
        frequency  = parameters.get("frequency", "daily")
        hour       = int(parameters.get("hour", 8))
        minute     = int(parameters.get("minute", 0))
        weekday    = parameters.get("weekday", "MON")
        interval   = int(parameters.get("interval_minutes", 60))
        task_act   = parameters.get("task_action", "notify")
        task_params= parameters.get("task_parameters", {})
        run_date   = parameters.get("run_date", datetime.now().strftime("%Y-%m-%d"))

        tid = str(uuid.uuid4()).replace("-","")[:16]
        task = {
            "id":                tid,
            "name":              name,
            "frequency":         frequency,
            "hour":              hour,
            "minute":            minute,
            "weekday":           weekday,
            "interval_minutes":  interval,
            "task_action":       task_act,
            "task_parameters":   task_params if isinstance(task_params, dict) else {},
            "run_date":          run_date,
            "enabled":           True,
            "created":           datetime.now().isoformat(),
        }

        # Try registering in Windows Task Scheduler
        ok, out = _register_windows_task(task)
        wts_note = " (programado en Windows Task Scheduler)" if ok else " (solo en JARVIS — Task Scheduler no disponible)"

        with _lock:
            tasks = _load()
            tasks.append(task)
            _save(tasks)

        freq_str = {
            "daily":    f"todos los días a las {hour:02d}:{minute:02d}",
            "weekly":   f"cada {weekday} a las {hour:02d}:{minute:02d}",
            "interval": f"cada {interval} minutos",
            "once":     f"una vez el {run_date} a las {hour:02d}:{minute:02d}",
        }.get(frequency, frequency)

        msg = f"Tarea '{name}' creada. Se ejecutará {freq_str}{wts_note}. ID: {_short_id(tid)}"
        log(msg); return msg

    # ── DELETE ────────────────────────────────────────────────────────────────
    elif action == "delete":
        task_id = str(parameters.get("task_id", "")).strip().upper()
        with _lock:
            tasks = _load()
            match = next((t for t in tasks if _short_id(t["id"]) == task_id or t["id"] == task_id), None)
            if not match:
                return f"No se encontró tarea con ID '{task_id}'."
            _delete_windows_task(match["id"])
            tasks = [t for t in tasks if t["id"] != match["id"]]
            _save(tasks)
        msg = f"Tarea '{match['name']}' eliminada."
        log(msg); return msg

    # ── ENABLE / DISABLE ─────────────────────────────────────────────────────
    elif action in ("enable", "disable"):
        task_id = str(parameters.get("task_id", "")).strip().upper()
        enabled = action == "enable"
        with _lock:
            tasks = _load()
            match = next((t for t in tasks if _short_id(t["id"]) == task_id), None)
            if not match:
                return f"No se encontró tarea con ID '{task_id}'."
            match["enabled"] = enabled
            _save(tasks)
            # Update WTS
            flag = "/Enable" if enabled else "/Disable"
            _schtasks(["/Change", flag, "/TN", f"JARVIS\\{match['id']}"])
        msg = f"Tarea '{match['name']}' {'habilitada' if enabled else 'deshabilitada'}."
        log(msg); return msg

    # ── RUN NOW ───────────────────────────────────────────────────────────────
    elif action == "run_now":
        task_id = str(parameters.get("task_id", "")).strip().upper()
        with _lock:
            tasks = _load()
            match = next((t for t in tasks if _short_id(t["id"]) == task_id), None)
        if not match:
            return f"No se encontró tarea con ID '{task_id}'."
        ok, out = _run_windows_task_now(match["id"])
        msg = f"Tarea '{match['name']}' ejecutada ahora." if ok else f"Error ejecutando tarea: {out}"
        log(msg); return msg

    return f"Acción '{action}' no reconocida. Usa: list | create | delete | enable | disable | run_now"

def start_runner(player=None, speak=None) -> None:
    """Called at JARVIS startup — ensures runner script exists."""
    _ensure_runner()
