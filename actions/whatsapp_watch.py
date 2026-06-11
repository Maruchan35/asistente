# -*- coding: utf-8 -*-
"""
whatsapp_watch.py — Detector de mensajes ENTRANTES de WhatsApp.

El eslabón que faltaba para conversaciones autónomas: JARVIS ahora puede
ENTERARSE solo de que llegó un mensaje, sin que el usuario se lo diga.

Detección por DOS capas (la que funcione primero):
  1. Título de ventana: WhatsApp Web/Desktop antepone "(N)" al título
     cuando hay chats sin leer — "(2) WhatsApp". Polling cada ~4s, costo cero.
  2. Notificaciones de Windows (winrt) — las maneja core/notification_watcher
     en paralelo (ya integrado en main.py).

Modo conversación continua:
  "JARVIS, sigue la conversación con Juan" →
    1. whatsapp_watch action=start contact="Juan" mode="converse"
    2. Al detectar mensaje nuevo, inyecta aviso a Gemini (vía callback speak)
    3. Gemini lee el chat (whatsapp action=read) y responde (whatsapp action=send)
    4. El watcher sigue activo → loop de conversación real

El watcher respeta kill switch y focus mode. Todo queda en auditoría.
"""
from __future__ import annotations
import re
import threading
import time

_active = False
_thread: threading.Thread | None = None
_stop = threading.Event()
_state = {
    "contact":      "",        # contacto objetivo ("" = cualquiera)
    "mode":         "notify",  # notify = solo avisar | converse = leer y responder
    "last_unread":  0,
    "events":       0,
    "started_at":   0.0,
}
_speak_cb = None               # callback para inyectar a Gemini (turn completo)

_POLL_S = 4.0
_TITLE_RE = re.compile(r"\((\d+)\)")


def _get_whatsapp_unread() -> int:
    """Leer el contador de no-leídos del título de la ventana de WhatsApp.
    Funciona con WhatsApp Desktop y WhatsApp Web en cualquier navegador."""
    try:
        import pygetwindow as gw
        best = 0
        for w in gw.getAllWindows():
            t = w.title or ""
            if "whatsapp" not in t.lower():
                continue
            m = _TITLE_RE.search(t)
            if m:
                best = max(best, int(m.group(1)))
            # título sin (N) pero con WhatsApp → 0 no-leídos visibles
        return best
    except Exception:
        return -1   # no se pudo leer


def _notify_gemini(unread: int):
    """Avisar a Gemini que llegó mensaje. El speak provoca turno del modelo."""
    contact = _state["contact"]
    mode = _state["mode"]
    if mode == "converse":
        who = f" de {contact}" if contact else ""
        msg = (
            f"(WHATSAPP WATCHER: llegó mensaje nuevo{who} — {unread} sin leer. "
            "Estás en MODO CONVERSACIÓN: 1) lee el chat con whatsapp action=read"
            + (f" receiver='{contact}'" if contact else "")
            + ", 2) responde apropiadamente con whatsapp action=send manteniendo "
            "el contexto y tono de la conversación, 3) NO avises al usuario por voz "
            "salvo que el mensaje sea importante o la conversación necesite su decisión.)"
        )
    else:
        msg = (
            f"(WHATSAPP WATCHER: hay {unread} mensaje(s) de WhatsApp sin leer. "
            "Avisa al usuario brevemente y ofrece leerlos.)"
        )
    try:
        if _speak_cb:
            _speak_cb(msg)
    except Exception:
        pass
    try:
        from core.autonomy import audit
        audit("whatsapp_watch", f"Mensaje detectado ({unread} sin leer, modo {mode})", "notificado")
    except Exception:
        pass


def _loop():
    global _active
    consecutive_fail = 0
    while _active and not _stop.is_set():
        try:
            # Respetar kill switch y focus
            try:
                from core.autonomy import is_killed
                from core.focus_mode import is_active as focus_on
                if is_killed() or focus_on():
                    _stop.wait(_POLL_S * 3)
                    continue
            except Exception:
                pass

            unread = _get_whatsapp_unread()
            if unread < 0:
                consecutive_fail += 1
                if consecutive_fail == 10:
                    print("[WA-Watch] No encuentro ventana de WhatsApp — ¿está abierto?")
                _stop.wait(_POLL_S * 2)
                continue
            consecutive_fail = 0

            if unread > _state["last_unread"]:
                _state["events"] += 1
                _notify_gemini(unread)
            _state["last_unread"] = unread
        except Exception:
            pass
        _stop.wait(_POLL_S)


def whatsapp_watch(parameters: dict, player=None, speak=None) -> str:
    """
    action: start | stop | status
    contact: nombre del contacto a vigilar/conversar ("" = cualquiera)
    mode: 'notify' (avisar al usuario) | 'converse' (leer y responder solo)
    """
    global _active, _thread, _speak_cb

    action  = (parameters.get("action") or "start").lower()
    contact = (parameters.get("contact") or "").strip()
    mode    = (parameters.get("mode") or "notify").lower()

    if action == "stop":
        if not _active:
            return "El watcher de WhatsApp no estaba activo."
        _active = False
        _stop.set()
        try:
            from core.autonomy import audit
            audit("whatsapp_watch", "Watcher detenido", f"{_state['events']} eventos detectados")
        except Exception:
            pass
        return (f"Vigilancia de WhatsApp detenida ({_state['events']} mensajes "
                "detectados durante la sesión).")

    if action == "status":
        if not _active:
            return "Watcher de WhatsApp inactivo."
        mins = int((time.time() - _state["started_at"]) / 60)
        who = f" con {_state['contact']}" if _state["contact"] else ""
        return (f"Vigilando WhatsApp{who} en modo {_state['mode']} desde hace "
                f"{mins} min — {_state['events']} mensajes detectados, "
                f"{_state['last_unread']} sin leer ahora.")

    # start
    if _active:
        # Actualizar parámetros sin reiniciar el hilo
        _state["contact"] = contact
        _state["mode"] = mode if mode in ("notify", "converse") else "notify"
        return (f"Watcher ya activo — actualizado: contacto='{contact or 'cualquiera'}', "
                f"modo={_state['mode']}.")

    # Verificar que WhatsApp esté visible
    unread_now = _get_whatsapp_unread()
    warn = ""
    if unread_now < 0:
        warn = (" AVISO: no encuentro ninguna ventana de WhatsApp abierta — "
                "abre WhatsApp Web o Desktop para que pueda vigilar.")

    _speak_cb = speak
    _state.update({
        "contact": contact,
        "mode": mode if mode in ("notify", "converse") else "notify",
        "last_unread": max(0, unread_now),
        "events": 0,
        "started_at": time.time(),
    })
    _stop.clear()
    _active = True
    _thread = threading.Thread(target=_loop, daemon=True, name="WhatsAppWatch")
    _thread.start()

    try:
        from core.autonomy import audit
        audit("whatsapp_watch",
              f"Watcher iniciado (contacto={contact or 'cualquiera'}, modo={_state['mode']})", "")
    except Exception:
        pass

    if _state["mode"] == "converse":
        who = f" con {contact}" if contact else ""
        return (f"Modo conversación continua activado{who}: detectaré cada mensaje "
                f"nuevo, lo leeré y responderé manteniendo la conversación.{warn}")
    return (f"Vigilancia de WhatsApp activada — le avisaré cuando lleguen "
            f"mensajes nuevos.{warn}")
