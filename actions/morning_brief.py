"""
morning_brief.py — Brief matutino real: hora, clima, objetivos y recordatorios pendientes.
"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
GOALS_PATH = BASE_DIR / "config" / "goals.json"
BRIEF_LOG  = BASE_DIR / "config" / "morning_brief_log.json"


def _get_weather() -> str:
    """Obtiene clima actual de wttr.in (sin API key)."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://wttr.in/?format=%C,+%t,+humedad+%h",
            headers={"User-Agent": "JARVIS/2.0"}
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return "información meteorológica no disponible"


def _get_goals() -> list:
    """Carga los objetivos activos."""
    if not GOALS_PATH.exists():
        return []
    try:
        data = json.loads(GOALS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _get_pending_reminders() -> list:
    """Busca recordatorios pendientes en el archivo de reminders si existe."""
    reminders_file = BASE_DIR / "config" / "reminders.json"
    if not reminders_file.exists():
        return []
    try:
        data = json.loads(reminders_file.read_text(encoding="utf-8"))
        now = datetime.now().timestamp()
        pending = []
        for r in data:
            fire_at = r.get("fire_at", 0)
            if fire_at > now:
                pending.append(r.get("text", "Recordatorio"))
        return pending[:3]
    except Exception:
        return []


def morning_brief(parameters: dict = None, player=None) -> str:
    """
    Brief matutino completo: fecha, hora, clima, objetivos activos y recordatorios pendientes.
    """
    now = datetime.now()

    # Día de la semana en español
    DAYS = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
    }
    MONTHS = {
        "January": "enero", "February": "febrero", "March": "marzo",
        "April": "abril", "May": "mayo", "June": "junio",
        "July": "julio", "August": "agosto", "September": "septiembre",
        "October": "octubre", "November": "noviembre", "December": "diciembre"
    }

    day_name  = DAYS.get(now.strftime("%A"), now.strftime("%A"))
    month_name = MONTHS.get(now.strftime("%B"), now.strftime("%B"))
    time_str  = now.strftime("%I:%M %p").lstrip("0")
    date_str  = f"{day_name} {now.day} de {month_name} de {now.year}"

    # Clima
    weather = _get_weather()

    # Objetivos
    goals = _get_goals()
    goals_str = ""
    if goals:
        goals_str = f" Tiene {len(goals)} objetivo{'s' if len(goals) > 1 else ''} activo{'s' if len(goals) > 1 else ''}: {', '.join(goals[:3])}."
    else:
        goals_str = " No hay objetivos activos en este momento."

    # Recordatorios
    reminders = _get_pending_reminders()
    reminders_str = ""
    if reminders:
        reminders_str = f" Recordatorio{'s' if len(reminders) > 1 else ''} pendiente{'s' if len(reminders) > 1 else ''}: {', '.join(reminders)}."

    brief = (
        f"Buenos días, señor. Son las {time_str} del {date_str}. "
        f"Clima: {weather}."
        f"{goals_str}"
        f"{reminders_str}"
    )

    if player:
        try: player.write_log(f"☀️ Brief matutino entregado.")
        except Exception: pass

    # Registrar que ya se dio el brief hoy
    try:
        BRIEF_LOG.parent.mkdir(parents=True, exist_ok=True)
        BRIEF_LOG.write_text(
            json.dumps({"last_brief_date": now.strftime("%Y-%m-%d")}),
            encoding="utf-8"
        )
    except Exception:
        pass

    return brief


def already_briefed_today() -> bool:
    """Devuelve True si ya se dio el brief hoy."""
    if not BRIEF_LOG.exists():
        return False
    try:
        data = json.loads(BRIEF_LOG.read_text(encoding="utf-8"))
        return data.get("last_brief_date") == datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_briefed() -> None:
    """Marca que el brief ya se entregó hoy."""
    try:
        BRIEF_LOG.parent.mkdir(parents=True, exist_ok=True)
        BRIEF_LOG.write_text(
            json.dumps({"last_brief_date": datetime.now().strftime("%Y-%m-%d")}),
            encoding="utf-8"
        )
    except Exception:
        pass
