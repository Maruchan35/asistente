"""gmail_control.py — Real Gmail integration via Google API.
Uses OAuth2 (credentials.json from Google Cloud Console).
First run opens browser for OAuth; token saved to config/gmail_token.json."""
from __future__ import annotations
import base64, email as email_lib, json, os, re, webbrowser
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent
TOKEN_FILE  = BASE_DIR / "config" / "gmail_token.json"
CREDS_FILE  = BASE_DIR / "config" / "google_credentials.json"
SCOPES      = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

def _load_keys() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

# ── Auth helper ───────────────────────────────────────────────────────────────
def _get_service():
    """Return an authenticated Gmail service, or raise with a helpful message."""
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
            "Pasos para configurar Gmail:\n"
            "1. Ir a https://console.cloud.google.com\n"
            "2. Crear un proyecto → APIs & Services → Credenciales\n"
            "3. Crear OAuth 2.0 Client ID (Desktop App)\n"
            "4. Descargar JSON y guardarlo como config/google_credentials.json"
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

    return build("gmail", "v1", credentials=creds)

def _decode_body(payload: dict) -> str:
    """Recursively decode email body from MIME parts."""
    if payload.get("body", {}).get("data"):
        try:
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        except Exception:
            return ""
    for part in payload.get("parts", []):
        if part.get("mimeType") in ("text/plain", "text/html"):
            data = part.get("body", {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    pass
    return ""

def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""

# ══════════════════════════════════════════════════════════════════════════════
def gmail_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "inbox").lower().strip()
    count  = int(parameters.get("count", 5))

    def log(msg: str):
        if player:
            player.write_log(f"📧 Gmail: {msg}")

    # ── SETUP GUIDE ───────────────────────────────────────────────────────────
    if action in ("setup", "configurar"):
        webbrowser.open("https://console.cloud.google.com/apis/credentials")
        return (
            "Para configurar Gmail:\n"
            "1. Abrí https://console.cloud.google.com\n"
            "2. Creá un proyecto → APIs & Services → Habilitar Gmail API\n"
            "3. Credenciales → OAuth 2.0 Client ID → Desktop App\n"
            "4. Descargá el JSON y guardalo como config/google_credentials.json\n"
            "5. La próxima vez que uses Gmail, se abrirá el navegador para autorizar."
        )

    # ── GET SERVICE ───────────────────────────────────────────────────────────
    try:
        service = _get_service()
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación Gmail: {e}"

    # ── INBOX ────────────────────────────────────────────────────────────────
    if action in ("inbox", "bandeja", "emails", "read", "listar"):
        label    = parameters.get("label", "INBOX")
        unread_only = parameters.get("unread", False)
        query_str= "is:unread" if unread_only else ""

        try:
            resp   = service.users().messages().list(
                userId="me", maxResults=count,
                labelIds=[label.upper()], q=query_str
            ).execute()
            msgs   = resp.get("messages", [])
            if not msgs:
                return f"No hay mensajes en {label}."
            lines  = [f"Últimos {len(msgs)} emails en {label}:"]
            for m in msgs:
                msg   = service.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
                hdrs  = msg.get("payload", {}).get("headers", [])
                frm   = _get_header(hdrs, "From")[:40]
                subj  = _get_header(hdrs, "Subject")[:60]
                date  = _get_header(hdrs, "Date")[:20]
                snippet = msg.get("snippet", "")[:60]
                lines.append(f"\n  [{m['id'][:8]}]\n  De: {frm}\n  Asunto: {subj}\n  {date}\n  {snippet}…")
            log(f"{len(msgs)} emails leídos")
            return "\n".join(lines)
        except Exception as e:
            return f"Error leyendo emails: {e}"

    # ── READ SPECIFIC EMAIL ──────────────────────────────────────────────────
    elif action in ("read_email", "abrir_email", "leer"):
        msg_id = parameters.get("message_id", parameters.get("id", "")).strip()
        if not msg_id:
            return "Especificá message_id con el ID del email (primeros 8 caracteres)."
        try:
            # Try as-is, then search by prefix
            full_id = msg_id
            if len(msg_id) <= 8:
                resp = service.users().messages().list(userId="me", maxResults=50).execute()
                for m in resp.get("messages", []):
                    if m["id"].startswith(msg_id):
                        full_id = m["id"]
                        break

            msg = service.users().messages().get(
                userId="me", id=full_id, format="full"
            ).execute()
            hdrs    = msg.get("payload", {}).get("headers", [])
            frm     = _get_header(hdrs, "From")
            to      = _get_header(hdrs, "To")
            subj    = _get_header(hdrs, "Subject")
            date    = _get_header(hdrs, "Date")
            body    = _decode_body(msg.get("payload", {}))
            # Strip HTML
            body    = re.sub(r"<[^>]+>", "", body)
            body    = re.sub(r"\n{3,}", "\n\n", body).strip()

            log(f"Email leído: {subj[:40]}")
            return (f"De: {frm}\nPara: {to}\nAsunto: {subj}\nFecha: {date}\n\n"
                    f"{body[:3000]}" + ("…" if len(body) > 3000 else ""))
        except Exception as e:
            return f"Error leyendo email {msg_id}: {e}"

    # ── SEND ─────────────────────────────────────────────────────────────────
    elif action in ("send", "enviar"):
        to_addr = parameters.get("to", parameters.get("receiver", "")).strip()
        subject = parameters.get("subject", parameters.get("asunto", "Mensaje de JARVIS")).strip()
        body    = parameters.get("body", parameters.get("message", "")).strip()
        if not to_addr:
            return "Especificá 'to' con el email del destinatario."
        if not body:
            return "Especificá 'body' con el contenido del mensaje."
        try:
            from email.mime.text import MIMEText
            msg = MIMEText(body, "plain", "utf-8")
            msg["to"]      = to_addr
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            log(f"Email enviado a {to_addr}")
            return f"Email enviado a {to_addr} con asunto '{subject}'."
        except Exception as e:
            return f"Error enviando email: {e}"

    # ── SEARCH ───────────────────────────────────────────────────────────────
    elif action in ("search", "buscar"):
        q = parameters.get("query", parameters.get("q", "")).strip()
        if not q:
            return "Especificá query para buscar emails."
        try:
            resp = service.users().messages().list(
                userId="me", maxResults=count, q=q
            ).execute()
            msgs = resp.get("messages", [])
            if not msgs:
                return f"No se encontraron emails para '{q}'."
            lines = [f"Resultados para '{q}' ({len(msgs)} emails):"]
            for m in msgs:
                msg = service.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
                hdrs  = msg.get("payload", {}).get("headers", [])
                frm   = _get_header(hdrs, "From")[:40]
                subj  = _get_header(hdrs, "Subject")[:60]
                lines.append(f"  [{m['id'][:8]}] {subj} — {frm}")
            log(f"Búsqueda '{q}': {len(msgs)} resultados")
            return "\n".join(lines)
        except Exception as e:
            return f"Error buscando emails: {e}"

    # ── MARK READ ─────────────────────────────────────────────────────────────
    elif action in ("mark_read", "marcar_leido"):
        msg_id = parameters.get("message_id", parameters.get("id", "")).strip()
        if not msg_id:
            return "Especificá message_id."
        try:
            service.users().messages().modify(
                userId="me", id=msg_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            log(f"Email {msg_id[:8]} marcado como leído")
            return f"Email marcado como leído."
        except Exception as e:
            return f"Error: {e}"

    # ── MARK UNREAD ───────────────────────────────────────────────────────────
    elif action in ("mark_unread", "marcar_no_leido"):
        msg_id = parameters.get("message_id", parameters.get("id", "")).strip()
        if not msg_id:
            return "Especificá message_id."
        try:
            service.users().messages().modify(
                userId="me", id=msg_id,
                body={"addLabelIds": ["UNREAD"]}
            ).execute()
            return "Email marcado como no leído."
        except Exception as e:
            return f"Error: {e}"

    # ── TRASH ────────────────────────────────────────────────────────────────
    elif action in ("trash", "mover_papelera", "delete"):
        msg_id = parameters.get("message_id", parameters.get("id", "")).strip()
        if not msg_id:
            return "Especificá message_id."
        try:
            service.users().messages().trash(userId="me", id=msg_id).execute()
            log(f"Email {msg_id[:8]} movido a papelera")
            return "Email movido a la papelera."
        except Exception as e:
            return f"Error: {e}"

    # ── LABELS ────────────────────────────────────────────────────────────────
    elif action in ("labels", "etiquetas"):
        try:
            resp = service.users().labels().list(userId="me").execute()
            labels = resp.get("labels", [])
            system = [l["name"] for l in labels if l.get("type") == "system"]
            user   = [l["name"] for l in labels if l.get("type") == "user"]
            return (f"Etiquetas del sistema: {', '.join(system)}\n"
                    f"Etiquetas personalizadas: {', '.join(user) or 'ninguna'}")
        except Exception as e:
            return f"Error: {e}"

    # ── PROFILE ──────────────────────────────────────────────────────────────
    elif action in ("profile", "perfil", "me"):
        try:
            profile = service.users().getProfile(userId="me").execute()
            return (f"Cuenta Gmail: {profile.get('emailAddress')}\n"
                    f"Total emails: {profile.get('messagesTotal', '?')}\n"
                    f"Threads: {profile.get('threadsTotal', '?')}")
        except Exception as e:
            return f"Error: {e}"

    # ── REPLY ────────────────────────────────────────────────────────────────
    elif action in ("reply", "responder"):
        msg_id  = parameters.get("message_id", parameters.get("id", "")).strip()
        body    = parameters.get("body", parameters.get("message", "")).strip()
        if not msg_id or not body:
            return "Necesito message_id y body para responder."
        try:
            # Get original message to extract thread and headers
            orig = service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["From", "Subject", "Message-ID"]
            ).execute()
            hdrs      = orig.get("payload", {}).get("headers", [])
            to_addr   = _get_header(hdrs, "From")
            subject   = "Re: " + _get_header(hdrs, "Subject").lstrip("Re: ")
            thread_id = orig.get("threadId")
            msg_hdr   = _get_header(hdrs, "Message-ID")

            from email.mime.text import MIMEText
            reply = MIMEText(body, "plain", "utf-8")
            reply["to"]         = to_addr
            reply["subject"]    = subject
            reply["In-Reply-To"]= msg_hdr
            reply["References"] = msg_hdr
            raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
            service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": thread_id}
            ).execute()
            log(f"Respuesta enviada a {to_addr[:30]}")
            return f"Respuesta enviada a {to_addr}."
        except Exception as e:
            return f"Error respondiendo: {e}"

    return (f"Acción '{action}' no reconocida. "
            "Usa: inbox | read_email | send | search | mark_read | mark_unread | "
            "trash | labels | profile | reply | setup")
