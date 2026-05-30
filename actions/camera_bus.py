# -*- coding: utf-8 -*-
"""
camera_bus.py — Tool action to interact with the holographic gesture camera control via voice commands.
"""
from PyQt6.QtCore import QMetaObject, Qt

def camera_bus(parameters: dict, player=None) -> str:
    """
    Voice tool action to toggle holographic gesture camera control.
    """
    action = parameters.get("action", "toggle").lower().strip()
    
    if player and hasattr(player, "_win") and player._win:
        win = player._win
        is_open = win.camera_window is not None
        
        if action in ("enable", "show", "on", "activar", "conectar"):
            if is_open:
                return "El subsistema de pilotaje gestual ya está activo en pantalla, señor."
            else:
                QMetaObject.invokeMethod(win, "_toggle_camera_gestures", Qt.ConnectionType.QueuedConnection)
                return "Entendido. He iniciado el subsistema de pilotaje gestual por cámara, señor."
        elif action in ("disable", "hide", "off", "desactivar", "apagar"):
            if not is_open:
                return "El subsistema de pilotaje gestual ya está apagado, señor."
            else:
                QMetaObject.invokeMethod(win, "_toggle_camera_gestures", Qt.ConnectionType.QueuedConnection)
                return "Apagando el subsistema de pilotaje gestual por cámara, señor."
        else: # toggle
            QMetaObject.invokeMethod(win, "_toggle_camera_gestures", Qt.ConnectionType.QueuedConnection)
            status = "desactivado" if is_open else "activado"
            return f"He {status} el subsistema de pilotaje gestual por cámara, señor."
            
    return "La cámara gestual no está disponible en la interfaz actual, señor."
