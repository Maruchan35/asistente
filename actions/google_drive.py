"""google_drive.py — Real Google Drive integration via Google API.
Shares OAuth credentials with Gmail/Calendar (config/google_credentials.json)."""
from __future__ import annotations
import io, json, os, webbrowser
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "config" / "gdrive_token.json"
CREDS_FILE = BASE_DIR / "config" / "google_credentials.json"
SCOPES     = ["https://www.googleapis.com/auth/drive"]

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

    return build("drive", "v3", credentials=creds)

def _format_size(size: int | str) -> str:
    try:
        n = int(size)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"
    except Exception:
        return "?"

def _mime_label(mime: str) -> str:
    MIME_LABELS = {
        "application/vnd.google-apps.folder":       "📁 Carpeta",
        "application/vnd.google-apps.document":     "📄 Doc",
        "application/vnd.google-apps.spreadsheet":  "📊 Sheet",
        "application/vnd.google-apps.presentation": "📊 Slides",
        "application/vnd.google-apps.form":         "📋 Form",
        "application/pdf":                           "📕 PDF",
        "image/jpeg":                                "🖼 JPEG",
        "image/png":                                 "🖼 PNG",
        "text/plain":                                "📝 TXT",
    }
    return MIME_LABELS.get(mime, mime.split("/")[-1])

# ══════════════════════════════════════════════════════════════════════════════
def google_drive(parameters: dict, player=None) -> str:
    action = parameters.get("action", "list").lower().strip()

    def log(msg: str):
        if player:
            player.write_log(f"☁ Drive: {msg}")

    if action in ("setup", "configurar"):
        webbrowser.open("https://console.cloud.google.com/apis/library/drive.googleapis.com")
        return ("Para configurar Google Drive:\n"
                "1. Habilitá la Drive API en Google Cloud Console\n"
                "2. Usá las mismas credenciales que Gmail (config/google_credentials.json)")

    try:
        service = _get_service()
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación Google Drive: {e}"

    # ── LIST ──────────────────────────────────────────────────────────────────
    if action in ("list", "listar", "files", "archivos"):
        folder_id = parameters.get("folder_id", "root")
        count     = int(parameters.get("count", 20))
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            result = service.files().list(
                q=query,
                pageSize=count,
                fields="files(id, name, mimeType, size, modifiedTime, parents)",
                orderBy="modifiedTime desc",
            ).execute()
            files = result.get("files", [])
            if not files:
                return "No hay archivos en esta carpeta."
            lines = [f"Archivos en Drive ({len(files)}):"]
            for f in files:
                size = _format_size(f.get("size", 0)) if f.get("size") else ""
                mod  = f.get("modifiedTime", "?")[:10]
                type_label = _mime_label(f.get("mimeType", ""))
                lines.append(
                    f"  [{f['id'][:12]}] {type_label} {f['name']}"
                    + (f" ({size})" if size else "")
                    + f" — {mod}"
                )
            log(f"{len(files)} archivos listados")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listando archivos: {e}"

    # ── SEARCH ────────────────────────────────────────────────────────────────
    elif action in ("search", "buscar"):
        q     = parameters.get("query", parameters.get("q", "")).strip()
        count = int(parameters.get("count", 10))
        if not q:
            return "Especificá query para buscar archivos."
        try:
            query = f"name contains '{q}' and trashed=false"
            result = service.files().list(
                q=query, pageSize=count,
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc",
            ).execute()
            files = result.get("files", [])
            if not files:
                return f"No se encontraron archivos para '{q}'."
            lines = [f"Resultados para '{q}' ({len(files)}):"]
            for f in files:
                size = _format_size(f.get("size", 0)) if f.get("size") else ""
                type_label = _mime_label(f.get("mimeType", ""))
                lines.append(
                    f"  [{f['id'][:12]}] {type_label} {f['name']}"
                    + (f" ({size})" if size else "")
                )
            log(f"Search '{q}': {len(files)} resultados")
            return "\n".join(lines)
        except Exception as e:
            return f"Error buscando: {e}"

    # ── UPLOAD ────────────────────────────────────────────────────────────────
    elif action in ("upload", "subir"):
        local_path = parameters.get("path", parameters.get("file", "")).strip()
        folder_id  = parameters.get("folder_id", "root")
        if not local_path:
            return "Especificá path con la ruta del archivo local a subir."
        local_path = Path(local_path)
        if not local_path.exists():
            return f"Archivo no encontrado: {local_path}"
        try:
            from googleapiclient.http import MediaFileUpload
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(local_path))
            mime_type     = mime_type or "application/octet-stream"
            file_meta = {
                "name": local_path.name,
                "parents": [folder_id],
            }
            media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
            uploaded = service.files().create(
                body=file_meta, media_body=media, fields="id, name, webViewLink"
            ).execute()
            log(f"Subido: {local_path.name}")
            return (f"Archivo '{uploaded['name']}' subido a Drive.\n"
                    f"  ID: {uploaded['id'][:16]}\n"
                    f"  Link: {uploaded.get('webViewLink', '')}")
        except ImportError:
            return "googleapiclient.http no disponible. Reinstalá google-api-python-client."
        except Exception as e:
            return f"Error subiendo archivo: {e}"

    # ── DOWNLOAD ─────────────────────────────────────────────────────────────
    elif action in ("download", "descargar"):
        file_id  = parameters.get("file_id", parameters.get("id", "")).strip()
        dest     = parameters.get("destination", str(Path.home() / "Downloads")).strip()
        if not file_id:
            return "Especificá file_id. Usá action=list o action=search para encontrar el ID."
        try:
            from googleapiclient.http import MediaIoBaseDownload
            meta  = service.files().get(fileId=file_id, fields="name, mimeType, size").execute()
            name  = meta["name"]
            mime  = meta.get("mimeType", "")

            # Google Workspace files need export
            EXPORT_MIME = {
                "application/vnd.google-apps.document":     ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
                "application/vnd.google-apps.spreadsheet":  ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
                "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
            }

            dest_path = Path(dest) / name
            if mime in EXPORT_MIME:
                export_mime, ext = EXPORT_MIME[mime]
                if not name.endswith(ext):
                    dest_path = Path(dest) / (name + ext)
                req = service.files().export_media(fileId=file_id, mimeType=export_mime)
            else:
                req = service.files().get_media(fileId=file_id)

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with io.FileIO(str(dest_path), "wb") as fh:
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            size = _format_size(dest_path.stat().st_size)
            log(f"Descargado: {name} ({size})")
            return f"Archivo descargado: {dest_path}\n({size})"
        except ImportError:
            return "googleapiclient.http no disponible."
        except Exception as e:
            return f"Error descargando: {e}"

    # ── CREATE FOLDER ─────────────────────────────────────────────────────────
    elif action in ("create_folder", "nueva_carpeta", "mkdir"):
        name      = parameters.get("name", parameters.get("folder_name", "")).strip()
        parent_id = parameters.get("parent_id", "root")
        if not name:
            return "Especificá name para la nueva carpeta."
        try:
            folder = service.files().create(body={
                "name":     name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents":  [parent_id],
            }, fields="id, name").execute()
            log(f"Carpeta creada: {name}")
            return f"Carpeta '{name}' creada en Drive. ID: {folder['id'][:16]}"
        except Exception as e:
            return f"Error creando carpeta: {e}"

    # ── DELETE ────────────────────────────────────────────────────────────────
    elif action in ("delete", "eliminar", "trash"):
        file_id = parameters.get("file_id", parameters.get("id", "")).strip()
        if not file_id:
            return "Especificá file_id para eliminar."
        try:
            service.files().update(fileId=file_id, body={"trashed": True}).execute()
            log(f"Archivo {file_id[:12]} movido a papelera")
            return "Archivo movido a la papelera de Drive."
        except Exception as e:
            return f"Error: {e}"

    # ── SHARE ────────────────────────────────────────────────────────────────
    elif action in ("share", "compartir"):
        file_id = parameters.get("file_id", parameters.get("id", "")).strip()
        email   = parameters.get("email", "").strip()
        role    = parameters.get("role", "reader")  # reader | writer | commenter
        if not file_id:
            return "Especificá file_id para compartir."
        try:
            body = {"type": "anyone" if not email else "user",
                    "role": role}
            if email:
                body["emailAddress"] = email
            service.permissions().create(
                fileId=file_id, body=body,
                fields="id", sendNotificationEmail=bool(email)
            ).execute()
            meta = service.files().get(fileId=file_id, fields="webViewLink, name").execute()
            target = f"con {email}" if email else "con cualquiera con el link"
            log(f"Compartido: {meta.get('name','')} {target}")
            return (f"Archivo compartido {target} (rol: {role}).\n"
                    f"Link: {meta.get('webViewLink','')}")
        except Exception as e:
            return f"Error compartiendo: {e}"

    # ── STORAGE ───────────────────────────────────────────────────────────────
    elif action in ("storage", "espacio", "quota"):
        try:
            about = service.about().get(fields="storageQuota, user").execute()
            quota = about.get("storageQuota", {})
            used  = _format_size(int(quota.get("usage", 0)))
            total = _format_size(int(quota.get("limit", 0))) if quota.get("limit") else "ilimitado"
            drive = _format_size(int(quota.get("usageInDrive", 0)))
            gmail = _format_size(int(quota.get("usageInDriveTrash", 0)))
            user  = about.get("user", {}).get("emailAddress", "?")
            return (f"Google Drive — {user}\n"
                    f"  Usado: {used} / {total}\n"
                    f"  En Drive: {drive}\n"
                    f"  En papelera: {gmail}")
        except Exception as e:
            return f"Error: {e}"

    # ── OPEN IN BROWSER ──────────────────────────────────────────────────────
    elif action in ("open", "abrir"):
        file_id = parameters.get("file_id", parameters.get("id", "")).strip()
        if file_id:
            url = f"https://drive.google.com/file/d/{file_id}/view"
        else:
            url = "https://drive.google.com"
        webbrowser.open(url)
        return f"Google Drive abierto en el navegador."

    return (f"Acción '{action}' no reconocida. "
            "Usa: list | search | upload | download | create_folder | delete | share | storage | open | setup")
