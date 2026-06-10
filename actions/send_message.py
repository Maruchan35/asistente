"""send_message.py — Multi-platform messenger: Telegram, Discord, Slack.
WhatsApp → use whatsapp.py instead."""
from __future__ import annotations
import json, urllib.request, urllib.parse, urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
KEYS_FILE = BASE_DIR / "config" / "api_keys.json"

def _load_keys() -> dict:
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

# ── Telegram ──────────────────────────────────────────────────────────────────
def _send_telegram(token: str, chat_id: str, text: str) -> str:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            resp = json.loads(r.read())
            if resp.get("ok"):
                return f"Mensaje enviado por Telegram."
            return f"Telegram error: {resp.get('description','?')}"
    except Exception as e:
        return f"Telegram error: {e}"

# ── Discord webhook ────────────────────────────────────────────────────────────
def _send_discord(webhook_url: str, text: str, username: str = "JARVIS") -> str:
    data = json.dumps({"content": text, "username": username}).encode()
    req  = urllib.request.Request(webhook_url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8):
            return "Mensaje enviado por Discord."
    except urllib.error.HTTPError as e:
        return f"Discord error {e.code}: {e.reason}"
    except Exception as e:
        return f"Discord error: {e}"

# ── Slack webhook ──────────────────────────────────────────────────────────────
def _send_slack(webhook_url: str, text: str) -> str:
    data = json.dumps({"text": text}).encode()
    req  = urllib.request.Request(webhook_url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8):
            return "Mensaje enviado por Slack."
    except Exception as e:
        return f"Slack error: {e}"

# ══════════════════════════════════════════════════════════════════════════════
def send_message(parameters: dict, response=None, player=None,
                 session_memory=None) -> str:
    platform  = parameters.get("platform", "telegram").lower().strip()
    message   = parameters.get("message_text", parameters.get("message", "")).strip()
    receiver  = parameters.get("receiver", "").strip()

    if not message:
        return "No hay mensaje que enviar."

    keys = _load_keys()

    def log(msg):
        if player: player.write_log(f"💬 {msg}")

    # ── TELEGRAM ─────────────────────────────────────────────────────────────
    if "telegram" in platform:
        token   = keys.get("telegram_bot_token", "").strip()
        chat_id = keys.get("telegram_chat_id", "").strip()
        if not token:
            return ("Telegram no configurado. "
                    "Agregá 'telegram_bot_token' y 'telegram_chat_id' en Configuración > API Keys.")
        if not chat_id:
            return "Falta el 'telegram_chat_id' en la configuración."
        result = _send_telegram(token, chat_id, message)
        log(result); return result

    # ── DISCORD ──────────────────────────────────────────────────────────────
    elif "discord" in platform:
        webhook = keys.get("discord_webhook", "").strip()
        if not webhook:
            return ("Discord no configurado. "
                    "Agregá 'discord_webhook' (URL de webhook) en config/api_keys.json.")
        result = _send_discord(webhook, message)
        log(result); return result

    # ── SLACK ────────────────────────────────────────────────────────────────
    elif "slack" in platform:
        webhook = keys.get("slack_webhook", "").strip()
        if not webhook:
            return ("Slack no configurado. "
                    "Agregá 'slack_webhook' (Incoming Webhook URL) en config/api_keys.json.")
        result = _send_slack(webhook, message)
        log(result); return result

    # ── EMAIL (basic SMTP) ────────────────────────────────────────────────────
    elif "email" in platform or "correo" in platform or "mail" in platform:
        import smtplib
        from email.mime.text import MIMEText
        smtp_user = keys.get("smtp_user", "").strip()
        smtp_pass = keys.get("smtp_password", "").strip()
        smtp_host = keys.get("smtp_host", "smtp.gmail.com").strip()
        smtp_port = int(keys.get("smtp_port", 587))
        to_email  = receiver if "@" in receiver else keys.get("default_email_to", "")
        if not smtp_user:
            return "Email no configurado. Agregá smtp_user, smtp_password en api_keys.json."
        try:
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = "Mensaje de JARVIS"
            msg["From"]    = smtp_user
            msg["To"]      = to_email
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
                srv.starttls()
                srv.login(smtp_user, smtp_pass)
                srv.sendmail(smtp_user, [to_email], msg.as_string())
            result = f"Email enviado a {to_email}."
            log(result); return result
        except Exception as e:
            return f"Error enviando email: {e}"

    return (f"Plataforma '{platform}' no soportada. "
            f"Disponibles: telegram, discord, slack, email. "
            f"Para WhatsApp usá la herramienta 'whatsapp'.")
