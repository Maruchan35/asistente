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

# Lock de concurrencia: cuando JARVIS está LEYENDO/RESPONDIENDO en WhatsApp
# (pyautogui + visión, 10-20s), el watcher debe PAUSAR — si no, sigue su
# polling cada 4s, detecta el badge otra vez y reinyecta turnos encima,
# acumulando operaciones de teclado/mouse hasta congelar todo.
_busy = threading.Event()
_busy_since = 0.0               # cuándo se marcó busy (para auto-expirar)
_BUSY_MAX_S = 60.0             # si Gemini no responde en 60s, liberar solo
_last_notify_ts = 0.0
_NOTIFY_COOLDOWN_S = 20.0       # no reinyectar hasta que pasen 20s o se libere busy

_POLL_S = 4.0
_TITLE_RE = re.compile(r"\((\d+)\)")


def set_busy(value: bool) -> None:
    """whatsapp.py llama esto al entrar/salir de read y send para que el
    watcher no dispare mientras JARVIS está operando la interfaz."""
    global _busy_since
    if value:
        _busy.set()
        _busy_since = time.time()
    else:
        _busy.clear()
        _busy_since = 0.0


def is_busy() -> bool:
    # Auto-expirar: si lleva demasiado tiempo busy (Gemini no respondió o
    # falló sin liberar), desbloquear solo para no paralizar el watcher.
    if _busy.is_set() and _busy_since and (time.time() - _busy_since) > _BUSY_MAX_S:
        _busy.clear()
        return False
    return _busy.is_set()


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
        if contact:
            msg = (
                f"(WHATSAPP WATCHER: llegó mensaje nuevo — {unread} sin leer. "
                f"MODO CONVERSACIÓN con '{contact}': "
                f"1) whatsapp action=read receiver='{contact}' — esto ENTRA al chat "
                "y te devuelve la transcripción real de los últimos mensajes; "
                f"2) responde con whatsapp action=send receiver='{contact}' "
                "manteniendo contexto y tono del chat (el chat se cierra solo "
                "tras enviar, para poder detectar el siguiente mensaje); "
                "3) si decides NO responder, llama whatsapp action=close_chat. "
                "NUNCA llames whatsapp_watch stop ni des por 'concluida' la "
                "conversación — sigue vigilando indefinidamente hasta que el "
                "USUARIO te diga que pares. Aunque el contacto se despida, "
                "puede volver a escribir.)"
            )
        else:
            msg = (
                f"(WHATSAPP WATCHER: llegó mensaje nuevo — {unread} sin leer. "
                "MODO CONVERSACIÓN sin contacto fijo: "
                "1) whatsapp action=read SIN receiver — te dirá QUÉ chats tienen "
                "mensajes sin leer; "
                "2) whatsapp action=read receiver='<nombre>' para ENTRAR y leer ese chat; "
                "3) responde con whatsapp action=send receiver='<nombre>' (el chat "
                "se cierra solo tras enviar); "
                "4) si decides NO responder, llama whatsapp action=close_chat; "
                "5) NO avises al usuario por voz salvo mensaje importante.)"
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
    global _active, _last_notify_ts
    consecutive_fail = 0
    while _active and not _stop.is_set():
        try:
            # PAUSA si JARVIS está operando WhatsApp (leyendo/respondiendo).
            # No tocar last_unread mientras tanto: el send hace reset_baseline()
            # al terminar, que re-sincroniza el contador correctamente.
            if is_busy():
                _stop.wait(_POLL_S)
                continue

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
                # Cooldown: no reinyectar si la notificación anterior es muy
                # reciente (Gemini todavía podría estar procesándola).
                now = time.time()
                if (now - _last_notify_ts) >= _NOTIFY_COOLDOWN_S:
                    _state["events"] += 1
                    _last_notify_ts = now
                    _notify_gemini(unread)
                    # Tras notificar, marcar busy hasta que el send lo libere
                    # (o auto-expire a los 60s) — evita doble disparo.
                    set_busy(True)
            _state["last_unread"] = unread
        except Exception:
            pass
        _stop.wait(_POLL_S)


def is_converse_active() -> bool:
    """¿Está el watcher en modo conversación? (usado por whatsapp.py para
    cerrar el chat tras responder — si el chat queda abierto, WhatsApp marca
    los mensajes entrantes como leídos al instante y el contador '(N)' del
    título nunca aparece → el watcher queda ciego)."""
    return _active and _state.get("mode") == "converse"


def reset_baseline() -> None:
    """Re-sincronizar el contador tras una acción nuestra (enviar/leer)."""
    n = _get_whatsapp_unread()
    if n >= 0:
        _state["last_unread"] = n


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
        # GUARD: en modo conversación, JARVIS NO puede detener la vigilancia por
        # su cuenta (tendía a "concluir" la charla tras una respuesta y apagar
        # el watcher, dejando sin contestar los siguientes mensajes). Solo el
        # USUARIO puede detenerla → exige confirmación explícita.
        user_requested = parameters.get("user_requested", parameters.get("confirmed", False))
        if isinstance(user_requested, str):
            user_requested = user_requested.lower() in ("true", "1", "yes", "sí", "si")
        if _state.get("mode") == "converse" and not user_requested:
            return ("NO detengas la conversación autónoma por tu cuenta. El modo "
                    "conversación sigue ACTIVO hasta que el USUARIO lo pida "
                    "explícitamente ('deja de responder', 'detén el chat'). "
                    "Aunque creas que la charla 'concluyó', el contacto puede "
                    "escribir de nuevo y debes seguir respondiendo. "
                    "Si el usuario SÍ lo pidió, vuelve a llamar con user_requested=true.")
        _active = False
        _stop.set()
        set_busy(False)
        try:
            from core.autonomy import audit
            audit("whatsapp_watch", "Watcher detenido por el usuario",
                  f"{_state['events']} eventos detectados")
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
