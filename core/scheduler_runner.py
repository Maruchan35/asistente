"""scheduler_runner.py — Executed by Windows Task Scheduler for JARVIS tasks."""
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
            f"[System.Windows.Forms.MessageBox]::Show(\"{msg}\", \"JARVIS\")"
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
