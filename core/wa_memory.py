"""
core/wa_memory.py — Memoria de conversaciones de WhatsApp entre sesiones.

Cuando JARVIS conversa por ti en modo autónomo, guarda los mensajes (leídos
y enviados) en un journal por contacto. Así puedes preguntar después:
  "¿qué le dijiste a Juan?" / "resume mi conversación con María"
aunque haya sido en otra sesión o mientras dormías.

Almacenamiento: memory/whatsapp_log.jsonl (una línea por mensaje).
Se poda automáticamente a los últimos N días para no crecer sin límite.
"""
from __future__ import annotations
import json
import threading
import time
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_LOG  = _BASE / "memory" / "whatsapp_log.jsonl"
_lock = threading.Lock()

_MAX_AGE_DAYS = 30


def log_message(chat: str, sender: str, text: str) -> None:
    """Registrar un mensaje (enviado o leído) de una conversación."""
    if not text or not chat:
        return
    entry = {
        "ts":     datetime.now().isoformat(timespec="seconds"),
        "chat":   chat.strip(),
        "sender": sender.strip(),
        "text":   text.strip()[:500],
    }
    with _lock:
        try:
            _LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def log_transcript(chat: str, transcript: str) -> None:
    """Guardar una transcripción multilínea (de whatsapp action=read).
    Formato esperado: '<Remitente>: <mensaje>' por línea."""
    if not transcript:
        return
    import re
    for line in transcript.split("\n"):
        line = line.strip()
        m = re.match(r"^([^:]{1,40}):\s*(.+)$", line)
        if m:
            sender, text = m.group(1).strip(), m.group(2).strip()
            if sender.upper() not in ("CHAT", "NO_LEIDOS"):
                log_message(chat, sender, text)


def _read_all() -> list[dict]:
    if not _LOG.exists():
        return []
    cutoff = time.time() - _MAX_AGE_DAYS * 86400
    out = []
    try:
        with open(_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    ts = datetime.fromisoformat(e.get("ts", "1970-01-01")).timestamp()
                    if ts >= cutoff:
                        out.append(e)
                except Exception:
                    pass
    except Exception:
        pass
    return out


def get_conversation(chat: str, limit: int = 20) -> str:
    """Recuperar los últimos N mensajes de un contacto."""
    chat_l = chat.lower().strip()
    msgs = [e for e in _read_all() if chat_l in e.get("chat", "").lower()]
    if not msgs:
        return f"No tengo registro de conversaciones con '{chat}'."
    msgs = msgs[-limit:]
    lines = [f"Conversación con '{chat}' (últimos {len(msgs)} mensajes):"]
    for e in msgs:
        t = e.get("ts", "")[5:16].replace("T", " ")
        lines.append(f"  [{t}] {e.get('sender','?')}: {e.get('text','')}")
    return "\n".join(lines)


def list_chats() -> str:
    """Listar las conversaciones registradas."""
    chats: dict[str, int] = {}
    for e in _read_all():
        c = e.get("chat", "")
        chats[c] = chats.get(c, 0) + 1
    if not chats:
        return "No hay conversaciones de WhatsApp registradas."
    items = sorted(chats.items(), key=lambda x: -x[1])
    return "Conversaciones registradas:\n" + "\n".join(
        f"  • {c}: {n} mensajes" for c, n in items)


def wa_memory(parameters: dict, player=None) -> str:
    """Entry point. action: get | list"""
    action = (parameters.get("action") or "get").lower()
    if action == "list":
        return list_chats()
    chat = (parameters.get("chat") or parameters.get("contact") or "").strip()
    if not chat:
        return "¿De qué contacto quieres ver la conversación?"
    return get_conversation(chat, int(parameters.get("limit", 20)))
