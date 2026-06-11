import asyncio

class NotificationWatcher:
    def __init__(self, callback):
        self.callback = callback
        self.listener = None
        self.token = None
        self._seen_ids = set()

    async def start(self):
        # Verificar disponibilidad del módulo ANTES — es opcional, no un error
        try:
            from winrt.windows.ui.notifications.management import (  # noqa: F401
                UserNotificationListener, UserNotificationListenerAccessStatus,
            )
        except ImportError:
            print("[Notifications] winrt no instalado — notificaciones del sistema "
                  "desactivadas (opcional: pip install winrt-Windows.UI.Notifications "
                  "winrt-Windows.UI.Notifications.Management)")
            return

        try:
            from winrt.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
            import winrt.windows.ui.notifications as notifications

            self.listener = UserNotificationListener.current
            status = await self.listener.request_access_async()

            if status != UserNotificationListenerAccessStatus.ALLOWED:
                print("[Notifications] Acceso denegado a las notificaciones del sistema.")
                return

            # Populate seen_ids so we don't alert on old ones BEFORE listening
            nots = await self.listener.get_notifications_async(notifications.NotificationKinds.TOAST)
            for n in nots:
                self._seen_ids.add(n.id)

            self.token = self.listener.add_notification_changed(self._on_notification_changed)
            print("[Notifications] Escuchando alertas de WhatsApp y Mail...")

        except Exception as e:
            print(f"[Notifications] Error iniciando watcher: {e}")

    def stop(self):
        if self.listener and self.token is not None:
            try:
                self.listener.remove_notification_changed(self.token)
            except Exception:
                pass

    def _on_notification_changed(self, listener, args):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # WinRT maneja callbacks en hilos diferentes. Schedule con call_soon_threadsafe:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(self._process_notifications()))
        except Exception:
            pass

    async def _process_notifications(self):
        try:
            import winrt.windows.ui.notifications as notifications
            kinds = notifications.NotificationKinds.TOAST
            nots = await self.listener.get_notifications_async(kinds)
            
            new_nots = []
            for n in nots:
                if n.id not in self._seen_ids:
                    self._seen_ids.add(n.id)
                    new_nots.append(n)
                    
            for n in new_nots:
                app_name = n.app_info.display_info.display_name if n.app_info else "System"
                
                # Filtrar solo Chrome (Gmail/Web), WhatsApp, o Mail
                app_lower = app_name.lower()
                if "whatsapp" in app_lower or "chrome" in app_lower or "mail" in app_lower or "correo" in app_lower:
                    bindings = n.notification.visual.bindings
                    text_elements = []
                    for b in bindings:
                        for t in b.get_text_elements():
                            text_elements.append(t.text)
                    
                    if text_elements:
                        title = text_elements[0]
                        body = "\n".join(text_elements[1:])
                        self.callback(app_name, title, body)
        except Exception as e:
            print(f"[Notifications] Error procesando notificación: {e}")
