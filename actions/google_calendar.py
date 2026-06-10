"""google_calendar.py — Real Google Calendar integration via Google API.
Uses same OAuth2 credentials as gmail_control.py (config/google_credentials.json)."""
from __future__ import annotations
import json, re, webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "config" / "gcal_token.json"
CREDS_FILE = BASE_DIR / "config" / "google_credentials.json"
SCOPES     = ["https://www.googleapis.com/auth/calendar"]

# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Librería de Google no instalada.\n"
            "Ejecutá: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )

    if not CREDS_FILE.exists():
        raise RuntimeError(
            "No encontré config/google_credentials.json.\n"
            "Configurá primero Gmail (action=setup) — usan las mismas credenciales."
        )

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            TOKEN_FILE.unlink(missing_ok=True)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)

# ── Date helpers ──────────────────────────────────────────────────────────────
def _parse_dt(s: str) -> str:
    """Parse natural date strings into RFC3339 format."""
    s = s.strip().lower()
    now = datetime.now()

    if s in ("hoy", "today", "ahora", "now"):
        dt = now
    elif s in ("mañana", "tomorrow"):
        dt = now + timedelta(days=1)
    elif s in ("pasado mañana",):
        dt = now + timedelta(days=2)
    elif re.match(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", s):
        # ISO format
        if "T" in s:
            dt = datetime.fromisoformat(s)
        else:
            dt = datetime.strptime(s, "%Y-%m-%d")
    elif re.match(r"\d{1,2}/\d{1,2}/?\d{0,4}", s):
        # DD/MM or DD/MM/YYYY
        parts = s.split("/")
        day, month = int(parts[0]), int(parts[1])
        year = int(parts[2]) if len(parts) > 2 and parts[2] else now.year
        dt = datetime(year, month, day, now.hour, now.minute)
    else:
        # Fallback: assume today + time
        dt = now

    # Check for time component
    time_m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", s)
    if time_m:
        h, m = int(time_m.group(1)), int(time_m.group(2))
        if time_m.group(3) == "pm" and h < 12:
            h += 12
        elif time_m.group(3) == "am" and h == 12:
            h = 0
        dt = dt.replace(hour=h, minute=m, second=0, microsecond=0)

    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()

def _format_event(event: dict) -> str:
    """Format a calendar event for display."""
    summary  = event.get("summary", "Sin título")
    start    = event.get("start", {})
    end      = event.get("end", {})
    location = event.get("location", "")
    desc     = event.get("description", "")[:100]
    event_id = event.get("id", "")[:12]

    start_str = start.get("dateTime", start.get("date", "?"))
    if "T" in start_str:
        try:
            dt = datetime.fromisoformat(start_str.rstrip("Z"))
            start_str = dt.strftime("%d/%m %H:%M")
        except Exception:
            pass
    end_str = end.get("dateTime", end.get("date", ""))
    if "T" in end_str:
        try:
            dt = datetime.fromisoformat(end_str.rstrip("Z"))
            end_str = dt.strftime("%H:%M")
        except Exception:
            pass

    result = f"  [{event_id}] {summary}\n  📅 {start_str}"
    if end_str:
        result += f" → {end_str}"
    if location:
        result += f"\n  📍 {location}"
    if desc:
        result += f"\n  📝 {desc}"
    return result

# ══════════════════════════════════════════════════════════════════════════════
def google_calendar(parameters: dict, player=None) -> str:
    action = parameters.get("action", "list").lower().strip()

    def log(msg: str):
        if player:
            player.write_log(f"📅 Calendar: {msg}")

    if action in ("setup", "configurar"):
        webbrowser.open("https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
        return ("Para configurar Google Calendar:\n"
                "1. Habilitá la Calendar API en Google Cloud Console\n"
                "2. Usá las mismas credenciales que Gmail (config/google_credentials.json)\n"
                "3. La próxima vez que usés Calendar, se abrirá el navegador para autorizar.")

    try:
        service = _get_service()
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación Google Calendar: {e}"

    now_iso = datetime.utcnow().isoformat() + "Z"

    # ── LIST / UPCOMING ───────────────────────────────────────────────────────
    if action in ("list", "listar", "upcoming", "próximos", "proximos", "ver"):
        count    = int(parameters.get("count", 10))
        calendar = parameters.get("calendar", "primary")
        try:
            result = service.events().list(
                calendarId=calendar,
                timeMin=now_iso,
                maxResults=count,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = result.get("items", [])
            if not events:
                return "No hay eventos próximos en el calendario."
            lines = [f"Próximos {len(events)} eventos:"]
            for ev in events:
                lines.append(_format_event(ev))
            log(f"{len(events)} eventos listados")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listando eventos: {e}"

    # ── CREATE ────────────────────────────────────────────────────────────────
    elif action in ("create", "crear", "add", "agregar", "new", "nuevo"):
        summary  = parameters.get("summary", parameters.get("title", parameters.get("name", ""))).strip()
        start    = parameters.get("start", parameters.get("start_time", "")).strip()
        end      = parameters.get("end", parameters.get("end_time", "")).strip()
        location = parameters.get("location", parameters.get("lugar", "")).strip()
        desc     = parameters.get("description", parameters.get("descripcion", "")).strip()
        calendar = parameters.get("calendar", "primary")
        duration = int(parameters.get("duration_minutes", parameters.get("duration", 60)))

        if not summary:
            return "Especificá summary con el nombre del evento."

        try:
            start_dt = _parse_dt(start) if start else (datetime.utcnow().isoformat() + "Z")
            if end:
                end_dt = _parse_dt(end)
            else:
                # Compute from duration
                start_base = datetime.fromisoformat(start_dt.rstrip("Z"))
                end_dt = (start_base + timedelta(minutes=duration)).isoformat() + "Z"

            event_body = {
                "summary":  summary,
                "start":    {"dateTime": start_dt, "timeZone": "America/Mexico_City"},
                "end":      {"dateTime": end_dt,   "timeZone": "America/Mexico_City"},
            }
            if location:
                event_body["location"] = location
            if desc:
                event_body["description"] = desc

            ev = service.events().insert(calendarId=calendar, body=event_body).execute()
            log(f"Evento creado: {summary}")
            return (f"Evento creado: '{summary}'\n"
                    f"  ID: {ev['id'][:12]}\n"
                    f"  Inicio: {start_dt}\n"
                    f"  Link: {ev.get('htmlLink', '')}")
        except Exception as e:
            return f"Error creando evento: {e}"

    # ── SEARCH ────────────────────────────────────────────────────────────────
    elif action in ("search", "buscar"):
        q        = parameters.get("query", parameters.get("q", "")).strip()
        calendar = parameters.get("calendar", "primary")
        if not q:
            return "Especificá query para buscar eventos."
        try:
            result = service.events().list(
                calendarId=calendar,
                q=q,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
                timeMin=now_iso,
            ).execute()
            events = result.get("items", [])
            if not events:
                return f"No se encontraron eventos para '{q}'."
            lines = [f"Eventos encontrados para '{q}':"]
            for ev in events:
                lines.append(_format_event(ev))
            log(f"Búsqueda '{q}': {len(events)} eventos")
            return "\n".join(lines)
        except Exception as e:
            return f"Error buscando: {e}"

    # ── EDIT ─────────────────────────────────────────────────────────────────
    elif action in ("edit", "update", "editar", "actualizar"):
        event_id = parameters.get("event_id", parameters.get("id", "")).strip()
        calendar = parameters.get("calendar", "primary")
        if not event_id:
            return "Especificá event_id. Usá action=list para ver los IDs."

        try:
            # Find full event ID if shortened
            if len(event_id) <= 12:
                result = service.events().list(
                    calendarId=calendar, maxResults=50, singleEvents=True,
                    timeMin=now_iso
                ).execute()
                for ev in result.get("items", []):
                    if ev["id"].startswith(event_id):
                        event_id = ev["id"]
                        break

            ev = service.events().get(calendarId=calendar, eventId=event_id).execute()

            # Update fields if provided
            if parameters.get("summary"):
                ev["summary"] = parameters["summary"]
            if parameters.get("start"):
                ev["start"] = {"dateTime": _parse_dt(parameters["start"]),
                               "timeZone": "America/Mexico_City"}
            if parameters.get("end"):
                ev["end"]   = {"dateTime": _parse_dt(parameters["end"]),
                               "timeZone": "America/Mexico_City"}
            if parameters.get("location"):
                ev["location"] = parameters["location"]
            if parameters.get("description"):
                ev["description"] = parameters["description"]

            updated = service.events().update(
                calendarId=calendar, eventId=event_id, body=ev
            ).execute()
            log(f"Evento actualizado: {updated.get('summary','')}")
            return f"Evento '{updated.get('summary','')}' actualizado."
        except Exception as e:
            return f"Error editando evento: {e}"

    # ── DELETE ────────────────────────────────────────────────────────────────
    elif action in ("delete", "eliminar", "borrar"):
        event_id = parameters.get("event_id", parameters.get("id", "")).strip()
        calendar = parameters.get("calendar", "primary")
        if not event_id:
            return "Especificá event_id. Usá action=list para ver los IDs."
        try:
            if len(event_id) <= 12:
                result = service.events().list(
                    calendarId=calendar, maxResults=50, singleEvents=True,
                    timeMin=now_iso
                ).execute()
                for ev in result.get("items", []):
                    if ev["id"].startswith(event_id):
                        name = ev.get("summary", "?")
                        event_id = ev["id"]
                        break
            service.events().delete(calendarId=calendar, eventId=event_id).execute()
            log(f"Evento eliminado: {event_id[:12]}")
            return f"Evento eliminado."
        except Exception as e:
            return f"Error eliminando: {e}"

    # ── TODAY ─────────────────────────────────────────────────────────────────
    elif action in ("today", "hoy", "agenda_hoy"):
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end   = today_start + timedelta(days=1)
            result = service.events().list(
                calendarId="primary",
                timeMin=today_start.isoformat() + "Z",
                timeMax=today_end.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = result.get("items", [])
            if not events:
                return "No hay eventos en el calendario para hoy."
            lines = [f"Agenda de hoy ({len(events)} eventos):"]
            for ev in events:
                lines.append(_format_event(ev))
            log(f"Agenda de hoy: {len(events)} eventos")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # ── CALENDARS ────────────────────────────────────────────────────────────
    elif action in ("calendars", "calendarios", "list_calendars"):
        try:
            result = service.calendarList().list().execute()
            cals = result.get("items", [])
            lines = ["Calendarios disponibles:"]
            for c in cals:
                primary = " (principal)" if c.get("primary") else ""
                lines.append(f"  [{c['id'][:20]}] {c.get('summary','?')}{primary}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    return (f"Acción '{action}' no reconocida. "
            "Usa: list | create | search | edit | delete | today | calendars | setup")
