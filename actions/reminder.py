"""reminder.py — Reminder system con toast notification y sonido."""
import threading
import time
from datetime import datetime, timedelta

def reminder(parameters: dict, response=None, player=None) -> str:
    """
    Establece un recordatorio por tiempo o fecha/hora exacta.
    Parámetros:
        - message: texto del recordatorio
        - time: delay tipo "10m", "2h", "30s" — O hora exacta "HH:MM"
        - date: fecha "YYYY-MM-DD" (opcional, si se pasa junto a time como hora)
    """
    text     = parameters.get("message", "").strip()
    time_str = str(parameters.get("time", "1m")).strip()
    date_str = str(parameters.get("date", "")).strip()

    if not text:
        text = "Recordatorio sin mensaje."

    # ── Calcular segundos de espera ────────────────────────────────────────
    seconds = 60
    try:
        t_lower = time_str.lower()
        if t_lower.endswith("s"):
            seconds = int(t_lower[:-1])
        elif t_lower.endswith("m"):
            seconds = int(t_lower[:-1]) * 60
        elif t_lower.endswith("h"):
            seconds = int(t_lower[:-1]) * 3600
        elif ":" in time_str:
            # Es una hora exacta HH:MM
            now = datetime.now()
            h, m = int(time_str.split(":")[0]), int(time_str.split(":")[1])
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if date_str:
                try:
                    y, mo, d = [int(x) for x in date_str.split("-")]
                    target = target.replace(year=y, month=mo, day=d)
                except Exception:
                    pass
            if target <= now:
                target += timedelta(days=1)   # Si ya pasó, mañana
            seconds = max(10, int((target - now).total_seconds()))
        elif time_str.isdigit():
            seconds = int(time_str)
    except Exception:
        seconds = 60

    # ── Hilo del recordatorio ──────────────────────────────────────────────
    def _run_reminder():
        time.sleep(seconds)

        # 1. Sonido del sistema
        try:
            import winsound
            for _ in range(3):
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
                time.sleep(0.4)
        except Exception:
            pass

        # 2. Notificación toast (win10toast)
        try:
            from win10toast import ToastNotifier
            toast = ToastNotifier()
            toast.show_toast(
                "⏰ JARVIS — Recordatorio",
                text,
                duration=10,
                threaded=True,
                icon_path=None,
            )
        except Exception:
            pass

        # 3. Log en la UI
        if player:
            try:
                player.write_log(f"⏰ RECORDATORIO: {text}")
            except Exception:
                pass

        # 4. TTS fallback usando edge-tts si está disponible
        try:
            import asyncio, edge_tts
            async def _speak():
                tts = edge_tts.Communicate(f"Señor, su recordatorio: {text}", voice="es-MX-DaliaNeural")
                tmp = __import__("tempfile").mktemp(suffix=".mp3")
                await tts.save(tmp)
                __import__("subprocess").Popen(
                    ["powershell", "-c", f'(New-Object Media.SoundPlayer "{tmp}").PlaySync()'],
                    creationflags=0x08000000
                )
            asyncio.run(_speak())
        except Exception:
            pass

    threading.Thread(target=_run_reminder, daemon=True, name=f"reminder-{int(time.time())}").start()

    # Formatear tiempo de respuesta legible
    if seconds < 60:
        human = f"{seconds} segundos"
    elif seconds < 3600:
        human = f"{seconds // 60} minutos"
    else:
        human = f"{seconds // 3600}h {(seconds % 3600) // 60}m"

    msg = f"Recordatorio '{text}' programado para en {human}."
    if player:
        try:
            player.write_log(f"⏰ {msg}")
        except Exception:
            pass
    return msg
