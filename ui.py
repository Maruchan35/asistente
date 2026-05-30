"""ui.py — 100% Custom Gold-Themed Dynamic Bento PyQt6 User Interface for JARVIS.

Fully optimized HUD layouts:
- Background WebGL reactive Particle Orb covering the screen.
- Floating transparent digital clock at the top-right corner.
- Organized Bento grid dashboard aligned perfectly at the bottom half.
- Centered speech captions at the bottom.
"""
from __future__ import annotations
import sys
import os
import json
import psutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, 
    QListWidget, QListWidgetItem, QProgressBar, QDialog, QMessageBox,
    QComboBox, QCheckBox, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QScrollArea, QSlider, QFrame, QGroupBox
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QObject, QTimer, QSize, QPropertyAnimation
from PyQt6.QtGui import QFont, QColor, QIcon, QMouseEvent
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

try:
    import qtawesome as qta
    HAS_QTA = True
except ImportError:
    HAS_QTA = False

# Active Timezone Peru (UTC-5)
_BA_TZ = timezone(timedelta(hours=-5))

# Themes Configuration
THEMES = {
    "cyan": {
        "PRI": "#00d4ff", "PRI_DIM": "#005f77", "BG": "#050c14", 
        "PANEL": "rgba(10, 22, 32, 0.7)", "BORDER": "rgba(0, 212, 255, 0.45)", "TEXT": "#7aeeff"
    },
    "green": {
        "PRI": "#00ff88", "PRI_DIM": "#006633", "BG": "#040e08", 
        "PANEL": "rgba(8, 26, 16, 0.7)", "BORDER": "rgba(0, 255, 136, 0.45)", "TEXT": "#7affcc"
    },
    "red": {
        "PRI": "#ff3b30", "PRI_DIM": "#7a1a15", "BG": "#0e0404", 
        "PANEL": "rgba(26, 8, 8, 0.7)", "BORDER": "rgba(255, 59, 48, 0.45)", "TEXT": "#ffaaaa"
    },
    "purple": {
        "PRI": "#a855f7", "PRI_DIM": "#5b21b6", "BG": "#07030f", 
        "PANEL": "rgba(15, 6, 24, 0.7)", "BORDER": "rgba(168, 85, 247, 0.45)", "TEXT": "#c084fc"
    },
    "gold": {
        "PRI": "#f59e0b", "PRI_DIM": "#78350f", "BG": "#0f0a02", 
        "PANEL": "rgba(35, 28, 10, 0.70)", "BORDER": "rgba(245, 158, 11, 0.45)", "TEXT": "#fde68a"
    },
    "white": {
        "PRI": "#e2e8f0", "PRI_DIM": "#64748b", "BG": "#050a14", 
        "PANEL": "rgba(12, 22, 38, 0.7)", "BORDER": "rgba(226, 232, 240, 0.45)", "TEXT": "#cbd5e1"
    }
}

# Theme Tokens
C_PRI = "#f59e0b"
C_PRI_DIM = "#78350f"
C_BG = "#0f0a02"
C_PANEL = "rgba(35, 28, 10, 0.70)"
C_BORDER = "rgba(245, 158, 11, 0.45)"
C_TEXT = "#fde68a"

GREEN = "#00ff88"
RED = "#ff3b30"

def apply_theme_tokens(theme_name: str):
    global C_PRI, C_PRI_DIM, C_BG, C_PANEL, C_BORDER, C_TEXT
    t = THEMES.get(theme_name.lower(), THEMES["gold"])
    C_PRI = t["PRI"]
    C_PRI_DIM = t["PRI_DIM"]
    C_BG = t["BG"]
    C_PANEL = t["PANEL"]
    C_BORDER = t["BORDER"]
    C_TEXT = t["TEXT"]

try:
    from memory.config_manager import load_api_keys
    _theme_name = load_api_keys().get("jarvis_theme", "gold")
    apply_theme_tokens(_theme_name)
except Exception:
    apply_theme_tokens("gold")


class WebBridge(QObject):
    def __init__(self, orb):
        super().__init__()
        self.orb = orb

    @pyqtSlot()
    def toggle_mute(self):
        if self.orb.ui:
            self.orb.ui._win._toggle_mute()

    @pyqtSlot()
    def request_theme(self):
        QTimer.singleShot(0, self.orb.sync_theme)


class CustomParticleOrb(QWidget):
    audio_signal = pyqtSignal(float)
    state_signal = pyqtSignal(str)
    theme_signal = pyqtSignal()

    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        except Exception:
            pass
            
        self.channel = QWebChannel()
        self.bridge = WebBridge(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        
        sphere_path = Path(__file__).parent / "assets" / "sphere.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(sphere_path.absolute())))
        
        layout.addWidget(self.web_view)
        self.setLayout(layout)
        
        self.audio_signal.connect(self._safe_set_audio)
        self.state_signal.connect(self._safe_set_state)
        self.theme_signal.connect(self._safe_sync_theme)
        self.web_view.loadFinished.connect(self._on_load_finished)
        
    def _on_load_finished(self, ok):
        print(f"[ORB] QWebEngineView loadFinished: {ok}")
        if ok:
            self.sync_theme()
            self.set_state("MUTED" if self.ui.muted else "LISTENING")
            try:
                from memory.config_manager import load_api_keys
                cfg = load_api_keys()
                quality = cfg.get("performance_quality", 80)
                self.web_view.page().runJavaScript(f"if (window.updatePerformance) window.updatePerformance({quality});")
            except Exception:
                pass

    def sync_theme(self):
        self.theme_signal.emit()

    def set_audio(self, level: float):
        self.audio_signal.emit(level)
        
    def set_state(self, state: str):
        self.state_signal.emit(state)

    def _safe_sync_theme(self):
        colors = {
            'PRI': C_PRI,
            'PRI_DIM': C_PRI_DIM,
            'TEXT': C_TEXT,
            'BG': C_BG
        }
        js_code = f"if (window.setThemeColors) window.setThemeColors({json.dumps(colors)});"
        self.web_view.page().runJavaScript(js_code)

    def _safe_set_audio(self, level: float):
        js_code = f"if (window.updateVolume) window.updateVolume({level});"
        self.web_view.page().runJavaScript(js_code)

    def _safe_set_state(self, state: str):
        js_code = f"if (window.updateState) window.updateState('{state}');"
        self.web_view.page().runJavaScript(js_code)


def hex_to_bgr(hex_str: str) -> tuple[int, int, int]:
    """Converts a hex color string (e.g. '#f59e0b' or 'rgba(r,g,b,a)') to a BGR tuple for OpenCV."""
    hex_str = hex_str.strip()
    if hex_str.startswith("rgba"):
        try:
            parts = hex_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            return b, g, r
        except Exception:
            return 11, 158, 245
    elif hex_str.startswith("#"):
        try:
            hex_val = hex_str.lstrip("#")
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            return b, g, r
        except Exception:
            return 11, 158, 245
    return 11, 158, 245


class CameraPreviewWindow(QWidget):
    """
    Floating, borderless, semi-transparent preview window displaying the webcam feed
    with MediaPipe hand skeleton joints drawn dynamically in the active theme's colors.
    Supports an EXTERNAL shared tracking thread so gesture tracking keeps running
    even when this window is minimized or hidden.
    """
    def __init__(self, shared_thread=None, on_close_callback=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(370, 320)

        # Accept an externally managed thread — do NOT own/stop it on close
        self.shared_thread = shared_thread
        self.on_close_callback = on_close_callback
        self.drag_position = None

        # Outer layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Transparent holographic frame with rich glassmorphism gradient
        container = QFrame(self)
        container.setObjectName("CameraContainer")
        container.setStyleSheet(f"""
            QFrame#CameraContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(12, 10, 5, 0.60), stop:1 rgba(2, 2, 2, 0.85));
                border: 1.8px solid {C_PRI};
                border-radius: 16px;
            }}
            QLabel {{
                color: {C_TEXT};
                font-family: 'Century Gothic', sans-serif;
            }}
        """)

        # Soft glowing background shadow for holographic floating effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 6)
        container.setGraphicsEffect(shadow)

        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(10, 10, 10, 10)
        c_layout.setSpacing(6)

        # ── Title & window controls ─────────────────────────────────────────
        title_layout = QHBoxLayout()
        title_layout.setSpacing(6)
        
        self.lbl_title_icon = QLabel(self)
        if HAS_QTA:
            self.lbl_title_icon.setPixmap(qta.icon('fa5s.video', color=C_PRI).pixmap(11, 11))
        
        title_label = QLabel("PILOTO GESTUAL  ·  HUD", self)
        title_label.setStyleSheet(
            f"font-weight: bold; font-size: 9px; letter-spacing: 1.8px; color: {C_PRI}; background: transparent; border: none;"
        )

        # Minimize button (hides the window but keeps the thread alive)
        self.btn_min = QPushButton("–", self)
        self.btn_min.setFixedSize(22, 22)
        self.btn_min.setToolTip("Minimizar — el tracking continúa en segundo plano")
        self.btn_min.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C_PRI};
                border: 1px solid rgba(245, 158, 11, 0.4);
                border-radius: 11px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(245,158,11,0.25);
                border-color: {C_PRI};
            }}
        """)
        self.btn_min.clicked.connect(self._minimize_to_background)

        # Close button (stops camera completely)
        self.btn_close = QPushButton("×", self)
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setToolTip("Cerrar ventana y apagar cámara")
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C_PRI};
                border: 1px solid rgba(245, 158, 11, 0.4);
                border-radius: 11px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #ff3b30;
                color: white;
                border-color: #ff3b30;
            }}
        """)
        self.btn_close.clicked.connect(self.close)  # CLOSE triggers closeEvent, shutting down the camera completely

        title_layout.addWidget(self.lbl_title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_min)
        title_layout.addWidget(self.btn_close)
        c_layout.addLayout(title_layout)

        # ── Video stream label with HUD dashed layout ─────────────────────────
        self.lbl_feed = QLabel(self)
        self.lbl_feed.setFixedSize(346, 226)
        self.lbl_feed.setStyleSheet(
            f"background-color: rgba(0, 0, 0, 0.45); border-radius: 10px; border: 1.2px dashed rgba(245, 158, 11, 0.40);"
        )
        self.lbl_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(self.lbl_feed)

        # ── Status footer ───────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(4)
        
        self.lbl_status = QLabel("Buscando mano...", self)
        self.lbl_status.setStyleSheet(
            f"font-size: 9px; color: {C_TEXT}; font-style: italic; background: transparent; border: none;"
        )
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_bg_icon = QLabel(self)
        if HAS_QTA:
            self.lbl_bg_icon.setPixmap(qta.icon('fa5s.running', color='#00ff88').pixmap(9, 9))

        self.lbl_bg_indicator = QLabel("Activo en 2do plano", self)
        self.lbl_bg_indicator.setStyleSheet(
            "font-size: 8px; color: #00ff88; font-weight: bold; background: transparent; border: none;"
        )
        self.lbl_bg_indicator.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        footer.addWidget(self.lbl_status)
        footer.addStretch()
        footer.addWidget(self.lbl_bg_icon)
        footer.addWidget(self.lbl_bg_indicator)
        c_layout.addLayout(footer)

        layout.addWidget(container)

    def _minimize_to_background(self):
        """Hide the preview window — gesture tracking continues uninterrupted."""
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def on_frame_received(self, q_img, status):
        from PyQt6.QtGui import QPixmap
        if not self.isVisible():
            return  # Skip rendering if hidden (saves CPU)
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.lbl_feed.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_feed.setPixmap(pixmap)
        self.lbl_status.setText(f"Piloto: {status}")

    def on_active_changed(self, active):
        if not active:
            self.lbl_status.setText("Cámara Desconectada")
            self.lbl_feed.clear()

    def attach_thread(self, thread):
        """Connect to an already-running GestureTrackingThread."""
        self.shared_thread = thread
        thread.frame_signal.connect(self.on_frame_received)
        thread.active_signal.connect(self.on_active_changed)

    def closeEvent(self, event):
        """User wants the camera completely stopped when closed."""
        if getattr(self, 'on_close_callback', None):
            self.on_close_callback()
        event.accept()


class ClockWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ClockWidget")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_time = QLabel("12:00:00")
        font_t = QFont("Century Gothic", 24, QFont.Weight.Bold)
        font_t.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self.lbl_time.setFont(font_t)
        self.lbl_time.setStyleSheet("color: white; border: none; background: transparent;")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_time)
        
        self.lbl_date = QLabel("Monday, 24 May 2026")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_date)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        
    def tick(self):
        now = datetime.now(_BA_TZ)
        self.lbl_time.setText(now.strftime("%I:%M:%S %p"))
        self.lbl_date.setText(now.strftime("%A, %d %B %Y"))
        
    def update_style(self):
        # Completely borderless and transparent for elegant floating style
        self.setStyleSheet("""
            QWidget#ClockWidget {
                background: transparent;
                border: none;
            }
        """)
        if hasattr(self, "lbl_date"):
            self.lbl_date.setStyleSheet(f"font-size: 11px; letter-spacing: 1px; color: {C_PRI}; border: none; background: transparent; font-weight: bold;")


class WeatherWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WeatherWidget")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        
        header = QHBoxLayout()
        lbl_icon = QLabel()
        if HAS_QTA:
            lbl_icon.setPixmap(qta.icon('fa5s.cloud-sun', color=C_PRI).pixmap(18, 18))
        header.addWidget(lbl_icon)
        
        self.lbl_title = QLabel("WEATHER REPORT")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        info = QHBoxLayout()
        self.lbl_temp = QLabel("18°C")
        self.lbl_temp.setStyleSheet("font-size: 20px; font-weight: bold; border: none; background: transparent; color: white;")
        info.addWidget(self.lbl_temp)
        
        self.lbl_desc = QLabel("Parcialmente Nublado")
        info.addWidget(self.lbl_desc)
        info.addStretch()
        layout.addLayout(info)
        
        details = QHBoxLayout()
        self.lbl_humidity = QLabel("Humedad: 82%")
        self.lbl_humidity.setStyleSheet("font-size: 10px; color: #94a3b8; border: none; background: transparent;")
        self.lbl_wind = QLabel("Viento: 12 km/h")
        self.lbl_wind.setStyleSheet("font-size: 10px; color: #94a3b8; border: none; background: transparent;")
        
        details.addWidget(self.lbl_humidity)
        details.addWidget(self.lbl_wind)
        details.addStretch()
        layout.addLayout(details)
        
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#WeatherWidget {{
                background: {C_PANEL};
                border: 1.5px solid {C_BORDER};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
            self.lbl_desc.setStyleSheet(f"font-size: 11px; color: {C_TEXT}; border: none; background: transparent;")


class SpotifyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpotifyWidget")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        header = QHBoxLayout()
        self.lbl_logo = QLabel()
        if HAS_QTA:
            self.lbl_logo.setPixmap(qta.icon('fa5b.spotify', color='#1DB954').pixmap(18, 18))
        else:
            self.lbl_logo.setText("🎵")
        header.addWidget(self.lbl_logo)
        
        self.lbl_title = QLabel("SPOTIFY CONTROL")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.lbl_track = QLabel("Not Playing")
        self.lbl_track.setStyleSheet("font-size: 13px; font-weight: bold; border: none; background: transparent; color: white;")
        self.lbl_artist = QLabel("Awaiting tracks...")
        layout.addWidget(self.lbl_track)
        layout.addWidget(self.lbl_artist)
        
        controls = QHBoxLayout()
        self.btn_shuffle = QPushButton()
        self.btn_prev = QPushButton()
        self.btn_play = QPushButton()
        self.btn_next = QPushButton()
        self.btn_heart = QPushButton()
        
        self.buttons_list = [
            (self.btn_shuffle, 'fa5s.random', C_PRI_DIM),
            (self.btn_prev, 'fa5s.step-backward', '#ffffff'),
            (self.btn_play, 'fa5s.play', '#ffffff'),
            (self.btn_next, 'fa5s.step-forward', '#ffffff'),
            (self.btn_heart, 'fa5s.heart', RED)
        ]
        
        for btn, icon, clr in self.buttons_list:
            if HAS_QTA:
                btn.setIcon(qta.icon(icon, color=clr))
            btn.setFixedSize(30, 30)
            controls.addWidget(btn)
            
        layout.addLayout(controls)
        
        self.btn_play.clicked.connect(lambda: self._press("playpause"))
        self.btn_prev.clicked.connect(lambda: self._press("prevtrack"))
        self.btn_next.clicked.connect(lambda: self._press("nexttrack"))
        
    def _press(self, key):
        try:
            import pyautogui
            pyautogui.press(key)
        except Exception:
            pass

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#SpotifyWidget {{
                background: {C_PANEL};
                border: 1.5px solid {C_BORDER};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
            self.lbl_artist.setStyleSheet(f"font-size: 11px; color: {C_PRI_DIM}; border: none; background: transparent;")
            for btn, icon, clr in self.buttons_list:
                btn.setStyleSheet(f"QPushButton {{ background: rgba(245,158,11,0.08); border: 1px solid {C_BORDER}; border-radius: 15px; }} QPushButton:hover {{ background: rgba(245,158,11,0.2); }}")


class SystemWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SystemWidget")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        header = QHBoxLayout()
        lbl_icon = QLabel()
        if HAS_QTA:
            lbl_icon.setPixmap(qta.icon('fa5s.bolt', color=C_PRI).pixmap(18, 18))
        header.addWidget(lbl_icon)
        
        self.lbl_title = QLabel("SYSTEM GAUGES")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.cpu_bar = QProgressBar()
        self.ram_bar = QProgressBar()
        
        self.bars = [(self.cpu_bar, "CPU Status"), (self.ram_bar, "RAM Status")]
        for bar, label in self.bars:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 10px; color: {C_PRI_DIM}; border: none; background: transparent;")
            layout.addWidget(lbl)
            bar.setTextVisible(True)
            layout.addWidget(bar)
            
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)
        self.update_stats()
        
    def update_stats(self):
        try:
            self.cpu_bar.setValue(int(psutil.cpu_percent()))
            self.ram_bar.setValue(int(psutil.virtual_memory().percent))
        except Exception:
            pass

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#SystemWidget {{
                background: {C_PANEL};
                border: 1.5px solid {C_BORDER};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
            for bar, label in self.bars:
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {C_BORDER};
                        border-radius: 6px;
                        text-align: center;
                        background: transparent;
                        color: white;
                        height: 14px;
                    }}
                    QProgressBar::chunk {{
                        background-color: {C_PRI};
                        border-radius: 5px;
                    }}
                """)


class TodoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TodoWidget")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        header = QHBoxLayout()
        lbl_icon = QLabel()
        if HAS_QTA:
            lbl_icon.setPixmap(qta.icon('fa5s.check-circle', color=C_PRI).pixmap(18, 18))
        header.addWidget(lbl_icon)
        
        self.lbl_title = QLabel("TODOS")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        inp_layout = QHBoxLayout()
        self.txt_task = QLineEdit()
        self.txt_task.setPlaceholderText("New chore...")
        inp_layout.addWidget(self.txt_task)
        
        self.btn_add = QPushButton("+")
        inp_layout.addWidget(self.btn_add)
        layout.addLayout(inp_layout)
        
        self.lst_todo = QListWidget()
        self.lst_todo.setStyleSheet("QListWidget { border: none; background: transparent; } QListWidget::item { padding: 4px; color: white; }")
        layout.addWidget(self.lst_todo)
        
        self.btn_add.clicked.connect(self.add_task)
        self.txt_task.returnPressed.connect(self.add_task)
        
    def add_task(self):
        text = self.txt_task.text().strip()
        if text:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lst_todo.addItem(item)
            self.txt_task.clear()

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#TodoWidget {{
                background: {C_PANEL};
                border: 1.5px solid {C_BORDER};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
            self.txt_task.setStyleSheet(f"QLineEdit {{ background: rgba(0,0,0,0.3); border: 1px solid {C_BORDER}; border-radius: 6px; padding: 4px; color: white; }}")
            self.btn_add.setStyleSheet(f"QPushButton {{ background: {C_PRI}; color: black; font-weight: bold; border-radius: 6px; padding: 4px 10px; }}")


class NotesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NotesWidget")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        header = QHBoxLayout()
        lbl_icon = QLabel()
        if HAS_QTA:
            lbl_icon.setPixmap(qta.icon('fa5s.sticky-note', color=C_PRI).pixmap(18, 18))
        header.addWidget(lbl_icon)
        
        self.lbl_title = QLabel("PAD NOTES")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Write details...")
        layout.addWidget(self.txt_notes)

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#NotesWidget {{
                background: {C_PANEL};
                border: 1.5px solid {C_BORDER};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
            self.txt_notes.setStyleSheet(f"QTextEdit {{ border: none; background: rgba(0,0,0,0.2); border-radius: 6px; padding: 6px; color: white; }}")


class FileDropZone(QWidget):
    fileDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.update_style()
        layout = QVBoxLayout(self)
        self.lbl = QLabel("Drop File Trigger")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet("border: none; background: transparent; font-weight: bold; color: white;")
        layout.addWidget(self.lbl)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(f"QWidget {{ background: rgba(245,158,11,0.15); border: 2px dashed {C_PRI}; border-radius: 10px; }}")

    def dragLeaveEvent(self, event):
        self.update_style()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.exists(path):
                self.fileDropped.emit(path)
                break
        self.dragLeaveEvent(None)

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: rgba(0,0,0,0.25);
                border: 1.5px dashed {C_BORDER};
                border-radius: 10px;
            }}
        """)


class FilesPanel(QWidget):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.setObjectName("FilesPanel")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        header = QHBoxLayout()
        lbl_icon = QLabel()
        if HAS_QTA:
            lbl_icon.setPixmap(qta.icon('fa5s.folder-open', color=C_PRI).pixmap(18, 18))
        header.addWidget(lbl_icon)
        
        self.lbl_title = QLabel("FILES DROP")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.drop_zone = FileDropZone()
        self.drop_zone.fileDropped.connect(self.on_file_dropped)
        layout.addWidget(self.drop_zone)
        
        self.lbl_current = QLabel("Ready for drops.")
        layout.addWidget(self.lbl_current)
        
    def on_file_dropped(self, path):
        self.ui.current_file = path
        name = os.path.basename(path)
        self.lbl_current.setText(f"Active: {name}")
        self.ui.write_log(f"📁 Drops linked: {name}")

    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#FilesPanel {{
                background: {C_PANEL};
                border: 1.5px solid {C_BORDER};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
            self.lbl_current.setStyleSheet(f"font-size: 10px; color: {C_PRI_DIM}; border: none; background: transparent;")
            self.drop_zone.update_style()


class DeviceSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS Settings Configuration Control")
        self.resize(650, 500)
        self.update_style()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        layout_title = QLabel(f"<h2 style='color: {C_PRI}; font-family: sans-serif; margin-bottom: 5px;'>System Master Configurations</h2>")
        main_layout.addWidget(layout_title)
        
        from PyQt6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {C_BORDER}; border-radius: 4px; background: transparent; }}
            QTabBar::tab {{ background: rgba(10,20,30,0.5); color: {C_TEXT}; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
            QTabBar::tab:selected {{ background: {C_PRI}; color: #000; font-weight: bold; }}
            QTabBar::tab:hover {{ background: rgba(245, 158, 11, 0.3); }}
        """)
        main_layout.addWidget(self.tabs)
        
        # --- TAB 1: API & BRAIN ---
        tab_brain = QWidget()
        lay_brain = QVBoxLayout(tab_brain)
        lay_brain.setSpacing(15)
        lay_brain.addWidget(QLabel("Gemini API Key:"))
        self.inp_gemini = QLineEdit()
        self.inp_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        lay_brain.addWidget(self.inp_gemini)
        
        lay_brain.addWidget(QLabel("OpenRouter API Key:"))
        self.inp_openrouter = QLineEdit()
        self.inp_openrouter.setEchoMode(QLineEdit.EchoMode.Password)
        lay_brain.addWidget(self.inp_openrouter)
        
        lay_brain.addWidget(QLabel("AI Provider / Brain System:"))
        self.cmb_ai_provider = QComboBox()
        self.cmb_ai_provider.addItem("Google Gemini (Cloud realtime)", "gemini")
        self.cmb_ai_provider.addItem("OpenRouter (Cloud fallback)", "openrouter")
        self.cmb_ai_provider.addItem("Ollama (Local Offline AI)", "ollama")
        lay_brain.addWidget(self.cmb_ai_provider)
        
        self.ollama_url_lbl = QLabel("Ollama Server URL:")
        lay_brain.addWidget(self.ollama_url_lbl)
        self.inp_ollama_url = QLineEdit()
        self.inp_ollama_url.setPlaceholderText("http://127.0.0.1:11434")
        lay_brain.addWidget(self.inp_ollama_url)
        
        self.ollama_model_lbl = QLabel("Ollama Model Name:")
        lay_brain.addWidget(self.ollama_model_lbl)
        self.inp_ollama_model = QLineEdit()
        self.inp_ollama_model.setPlaceholderText("gemma2:2b (or llama3, phi3)")
        lay_brain.addWidget(self.inp_ollama_model)
        self.cmb_ai_provider.currentIndexChanged.connect(self._toggle_ollama_fields)
        lay_brain.addStretch()
        self.tabs.addTab(tab_brain, "🧠 Inteligencia")
        
        # --- TAB 2: TELEGRAM ---
        tab_tel = QWidget()
        lay_tel = QVBoxLayout(tab_tel)
        lay_tel.setSpacing(15)
        lay_tel.addWidget(QLabel("Telegram Bot Token:"))
        self.inp_telegram_token = QLineEdit()
        self.inp_telegram_token.setEchoMode(QLineEdit.EchoMode.Password)
        lay_tel.addWidget(self.inp_telegram_token)
        
        lay_tel.addWidget(QLabel("Telegram Chat ID:"))
        self.inp_telegram_chat_id = QLineEdit()
        lay_tel.addWidget(self.inp_telegram_chat_id)

        lay_tel.addWidget(QLabel("DeepSeek API Key (Para Telegram):"))
        self.inp_deepseek = QLineEdit()
        self.inp_deepseek.setEchoMode(QLineEdit.EchoMode.Password)
        lay_tel.addWidget(self.inp_deepseek)

        lay_tel.addWidget(QLabel("Groq API Key (Para Telegram):"))
        self.inp_groq = QLineEdit()
        self.inp_groq.setEchoMode(QLineEdit.EchoMode.Password)
        lay_tel.addWidget(self.inp_groq)

        lay_tel.addWidget(QLabel("Motor de IA para Telegram:"))
        self.cmb_tel_ai = QComboBox()
        self.cmb_tel_ai.addItem("DeepSeek", "deepseek")
        self.cmb_tel_ai.addItem("Groq", "groq")
        lay_tel.addWidget(self.cmb_tel_ai)

        lay_tel.addStretch()
        self.tabs.addTab(tab_tel, "📱 Telegram")
        
        # --- TAB 3: PERSONALIZATION ---
        tab_pers = QWidget()
        lay_pers = QVBoxLayout(tab_pers)
        lay_pers.setSpacing(15)
        lay_pers.addWidget(QLabel("Nombre del Usuario:"))
        self.inp_user_name = QLineEdit()
        self.inp_user_name.setPlaceholderText("Ej: Señor Leguion")
        lay_pers.addWidget(self.inp_user_name)
        
        lay_pers.addWidget(QLabel("Active Voice Model:"))
        self.cmb_voice = QComboBox()
        self.voices = [
            ("Aoede", "Femenina (Cálida y sofisticada ✨)"),
            ("Kore", "Femenina (Suave y precisa)"),
            ("Leda", "Femenina (Natural y fluida)"),
            ("Zephyr", "Femenina (Dinámica y expresiva)"),
            ("Charon", "Masculina (Profunda y seria)"),
            ("Puck", "Masculina (Ágil y versátil)"),
            ("Fenrir", "Masculina (Grave y autoritaria)"),
            ("Orus", "Masculina (Clásica y equilibrada)")
        ]
        for val, desc in self.voices:
            self.cmb_voice.addItem(desc, val)
        lay_pers.addWidget(self.cmb_voice)
        
        lay_pers.addWidget(QLabel("Theme Palette Scheme:"))
        self.cmb_theme = QComboBox()
        import ui
        for k in ui.THEMES.keys():
            self.cmb_theme.addItem(k.upper(), k)
        lay_pers.addWidget(self.cmb_theme)
        
        lay_pers.addWidget(QLabel("Timezone / Zona Horaria:"))
        self.cmb_timezone = QComboBox()
        self.timezones = [
            ("America/Lima", "Perú (GMT-5) 🇵🇪"),
            ("America/Bogota", "Colombia (GMT-5) 🇨🇴"),
            ("America/Argentina/Buenos_Aires", "Argentina (GMT-3) 🇦🇷"),
            ("America/Santiago", "Chile (GMT-3) 🇨🇱"),
            ("America/Mexico_City", "México (GMT-6) 🇲🇽"),
            ("America/Caracas", "Venezuela (GMT-4) 🇻🇪"),
            ("Europe/Madrid", "España (GMT+1) 🇪🇸"),
            ("America/New_York", "Estados Unidos (GMT-5) 🇺🇸")
        ]
        for val, desc in self.timezones:
            self.cmb_timezone.addItem(desc, val)
        lay_pers.addWidget(self.cmb_timezone)
        lay_pers.addStretch()
        self.tabs.addTab(tab_pers, "🎨 Apariencia")
        
        # --- TAB 4: HARDWARE ---
        tab_hw = QWidget()
        lay_hw = QVBoxLayout(tab_hw)
        lay_hw.setSpacing(15)
        lay_hw.addWidget(QLabel("Microphone Input Device:"))
        self.cmb_mic = QComboBox()
        lay_hw.addWidget(self.cmb_mic)

        sens_layout = QHBoxLayout()
        sens_layout.addWidget(QLabel("Sensibilidad Micrófono (Puerta Ruido):"))
        self.lbl_mic_sens_val = QLabel("0.003")
        self.lbl_mic_sens_val.setStyleSheet(f"font-weight: bold; color: {{C_PRI}};")
        sens_layout.addStretch()
        sens_layout.addWidget(self.lbl_mic_sens_val)
        lay_hw.addLayout(sens_layout)

        self.sld_mic_sens = QSlider(Qt.Orientation.Horizontal)
        self.sld_mic_sens.setRange(5, 100)
        self.sld_mic_sens.setValue(30)
        self.sld_mic_sens.valueChanged.connect(lambda v: self.lbl_mic_sens_val.setText(f"{v/10000:.4f}"))
        lay_hw.addWidget(self.sld_mic_sens)
        
        lay_hw.addWidget(QLabel("Speaker Output Device:"))
        self.cmb_speaker = QComboBox()
        lay_hw.addWidget(self.cmb_speaker)

        lay_hw.addWidget(QLabel("Active Camera Device (Gesture Pilot):"))
        self.cmb_camera = QComboBox()
        lay_hw.addWidget(self.cmb_camera)
        
        lay_hw.addWidget(QLabel("DroidCam IP Address (Optional):"))
        self.inp_camera_ip = QLineEdit()
        self.inp_camera_ip.setPlaceholderText("Ej: 192.168.1.50")
        lay_hw.addWidget(self.inp_camera_ip)
        lay_hw.addStretch()
        self.tabs.addTab(tab_hw, "📷 Hardware")
        
        # --- TAB 5: PERFORMANCE ---
        tab_perf = QWidget()
        lay_perf = QVBoxLayout(tab_perf)
        lay_perf.setSpacing(15)
        perf_layout = QHBoxLayout()
        perf_layout.addWidget(QLabel("Visual Performance Quality (Caps RAM/GPU):"))
        self.lbl_performance_val = QLabel("80%")
        self.lbl_performance_val.setStyleSheet("font-weight: bold; color: #00ff88;")
        perf_layout.addStretch()
        perf_layout.addWidget(self.lbl_performance_val)
        lay_perf.addLayout(perf_layout)
        
        self.sld_performance = QSlider(Qt.Orientation.Horizontal)
        self.sld_performance.setRange(1, 100)
        self.sld_performance.setValue(80)
        self.sld_performance.valueChanged.connect(lambda v: self.lbl_performance_val.setText(f"{v}%"))
        lay_perf.addWidget(self.sld_performance)
        
        self.chk_gpu = QCheckBox("Enable GPU Rendering Acceleration")
        lay_perf.addWidget(self.chk_gpu)
        lay_perf.addStretch()
        self.tabs.addTab(tab_perf, "⚙️ Sistema")
        
        # --- TAB 6: SPOTIFY ---
        tab_spot = QWidget()
        lay_spot = QVBoxLayout(tab_spot)
        lay_spot.setSpacing(15)
        self.chk_advanced_spotify = QCheckBox("Configuración de desarrollador avanzada (Opcional)")
        lay_spot.addWidget(self.chk_advanced_spotify)
        
        self.spotify_id_lbl = QLabel("Spotify Client ID:")
        lay_spot.addWidget(self.spotify_id_lbl)
        self.inp_spotify_id = QLineEdit()
        self.inp_spotify_id.setPlaceholderText("Dejar en blanco para usar credenciales de JARVIS")
        lay_spot.addWidget(self.inp_spotify_id)
        
        self.spotify_secret_lbl = QLabel("Spotify Client Secret:")
        lay_spot.addWidget(self.spotify_secret_lbl)
        self.inp_spotify_secret = QLineEdit()
        self.inp_spotify_secret.setPlaceholderText("Dejar en blanco para usar credenciales de JARVIS")
        self.inp_spotify_secret.setEchoMode(QLineEdit.EchoMode.Password)
        lay_spot.addWidget(self.inp_spotify_secret)
        
        self.spotify_uri_lbl = QLabel("Spotify Redirect URI:")
        lay_spot.addWidget(self.spotify_uri_lbl)
        self.inp_spotify_uri = QLineEdit()
        self.inp_spotify_uri.setText("http://127.0.0.1:8888/callback")
        lay_spot.addWidget(self.inp_spotify_uri)
        
        self.chk_advanced_spotify.toggled.connect(self._toggle_advanced_spotify)
        
        spotify_auth_layout = QHBoxLayout()
        self.btn_spotify_login = QPushButton("Conectar con Spotify")
        self.lbl_spotify_status = QLabel("Consultando estado...")
        self.lbl_spotify_status.setStyleSheet("color: #a3a3a3; font-style: italic;")
        spotify_auth_layout.addWidget(self.btn_spotify_login)
        spotify_auth_layout.addWidget(self.lbl_spotify_status)
        lay_spot.addLayout(spotify_auth_layout)
        
        self.btn_spotify_login.clicked.connect(self.connect_spotify)
        lay_spot.addStretch()
        self.tabs.addTab(tab_spot, "🎵 Spotify")
        
        # Bottom Save button
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar Configuraciones")
        self.btn_save.setMinimumHeight(40)
        self.btn_save.setStyleSheet(f"background: {{C_PRI}}; color: #000; font-weight: bold; border-radius: 6px;")
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        main_layout.addLayout(btn_layout)
        
        self.btn_save.clicked.connect(self.save)
        self.load_settings()

    def _toggle_ollama_fields(self):
        is_ollama = (self.cmb_ai_provider.currentData() == "ollama")
        self.ollama_url_lbl.setVisible(is_ollama)
        self.inp_ollama_url.setVisible(is_ollama)
        self.ollama_model_lbl.setVisible(is_ollama)
        self.inp_ollama_model.setVisible(is_ollama)

    def _toggle_advanced_spotify(self, checked):
        self.spotify_id_lbl.setVisible(checked)
        self.inp_spotify_id.setVisible(checked)
        self.spotify_secret_lbl.setVisible(checked)
        self.inp_spotify_secret.setVisible(checked)
        self.spotify_uri_lbl.setVisible(checked)
        self.inp_spotify_uri.setVisible(checked)

    def load_settings(self):
        # Populate camera choices dynamically using QtMultimedia
        self.cmb_camera.clear()
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            cameras = QMediaDevices.videoInputs()
            if not cameras:
                self.cmb_camera.addItem("No se detectaron cámaras", -1)
                # Fallback options
                self.cmb_camera.addItem("Cámara Principal (Índice 0)", 0)
                self.cmb_camera.addItem("Cámara Secundaria (Índice 1)", 1)
                self.cmb_camera.addItem("Cámara Externa (Índice 2)", 2)
            else:
                for i, cam in enumerate(cameras):
                    desc = cam.description()
                    self.cmb_camera.addItem(f"{desc} (Índice {i})", i)
        except Exception:
            # Absolute fallback
            self.cmb_camera.addItem("Cámara Principal (Índice 0)", 0)
            self.cmb_camera.addItem("Cámara Secundaria (Índice 1)", 1)
            self.cmb_camera.addItem("Cámara Externa (Índice 2)", 2)

        try:
            import sounddevice as sd
            devices = sd.query_devices()
            
            self.cmb_mic.addItem("Default Microphone Input", "")
            for i, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    self.cmb_mic.addItem(dev["name"], i)
                    
            self.cmb_speaker.addItem("Default Speaker Output", "")
            for i, dev in enumerate(devices):
                if dev.get("max_output_channels", 0) > 0:
                    self.cmb_speaker.addItem(dev["name"], i)
        except Exception:
            pass
            
        try:
            from memory.config_manager import load_api_keys
            cfg = load_api_keys()
            
            self.inp_gemini.setText(cfg.get("gemini_api_key", ""))
            self.inp_openrouter.setText(cfg.get("openrouter_api_key", ""))
            self.inp_deepseek.setText(cfg.get("deepseek_api_key", ""))
            self.inp_groq.setText(cfg.get("groq_api_key", ""))
            self.inp_telegram_token.setText(cfg.get("telegram_bot_token", ""))
            self.inp_telegram_chat_id.setText(cfg.get("telegram_chat_id", ""))
            self.chk_gpu.setChecked(cfg.get("gpu_acceleration", False))
            
            # Telegram AI Provider
            tel_ai = cfg.get("telegram_ai_provider", "deepseek")
            idx = self.cmb_tel_ai.findData(tel_ai)
            if idx >= 0: self.cmb_tel_ai.setCurrentIndex(idx)
            
            # AI Provider
            prov = cfg.get("ai_provider", "gemini")
            idx = self.cmb_ai_provider.findData(prov)
            if idx >= 0: self.cmb_ai_provider.setCurrentIndex(idx)
            
            self.inp_ollama_url.setText(cfg.get("ollama_url", "http://127.0.0.1:11434"))
            self.inp_ollama_model.setText(cfg.get("ollama_model", "gemma2:2b"))
            self._toggle_ollama_fields()
            
            # Slider
            val = cfg.get("performance_quality", 80)
            self.sld_performance.setValue(val)
            self.lbl_performance_val.setText(f"{val}%")
            
            voice = cfg.get("jarvis_voice", "Aoede")
            for idx in range(self.cmb_voice.count()):
                if self.cmb_voice.itemData(idx) == voice:
                    self.cmb_voice.setCurrentIndex(idx)
                    break
                    
            theme = cfg.get("jarvis_theme", "gold")
            idx = self.cmb_theme.findData(theme)
            if idx >= 0:
                self.cmb_theme.setCurrentIndex(idx)
                
            # Timezone
            tz = cfg.get("timezone", "America/Lima")
            idx_tz = self.cmb_timezone.findData(tz)
            if idx_tz >= 0:
                self.cmb_timezone.setCurrentIndex(idx_tz)
                
            # User Name
            self.inp_user_name.setText(cfg.get("user_name", ""))
                
            mic = cfg.get("mic_device", "")
            idx = self.cmb_mic.findData(mic)
            if idx >= 0: self.cmb_mic.setCurrentIndex(idx)
            
            # Cargar sensibilidad del micrófono
            mic_sens = float(cfg.get("mic_sensitivity", 0.003))
            self.sld_mic_sens.setValue(int(mic_sens * 10000))
            self.lbl_mic_sens_val.setText(f"{mic_sens:.4f}")
            
            spk = cfg.get("speaker_device", "")
            idx = self.cmb_speaker.findData(spk)
            if idx >= 0: self.cmb_speaker.setCurrentIndex(idx)
            
            # Select saved camera device
            camera_device = cfg.get("camera_device", 0)
            try:
                camera_device = int(camera_device)
            except Exception:
                camera_device = 0
            idx_cam = self.cmb_camera.findData(camera_device)
            if idx_cam >= 0:
                self.cmb_camera.setCurrentIndex(idx_cam)
            
            # Load camera IP Address / URL
            self.inp_camera_ip.setText(cfg.get("camera_ip", ""))
            
            # Load Spotify configs
            spotify_id = cfg.get("spotify_client_id", "")
            spotify_secret = cfg.get("spotify_client_secret", "")
            self.inp_spotify_id.setText(spotify_id)
            self.inp_spotify_secret.setText(spotify_secret)
            self.inp_spotify_uri.setText(cfg.get("spotify_redirect_uri", "http://127.0.0.1:8888/callback"))
            
            # If custom developer keys exist, enable the advanced checkbox, otherwise hide them by default
            has_custom = bool(spotify_id or spotify_secret)
            self.chk_advanced_spotify.setChecked(has_custom)
            self._toggle_advanced_spotify(has_custom)
            
            # Check Spotify Auth status
            self.lbl_spotify_status.setText(self.check_spotify_auth_status())
            
        except Exception:
            pass
            
    def save(self):
        try:
            from memory.config_manager import save_api_keys
            theme_val = self.cmb_theme.currentData()
            
            # Camera device fallback
            camera_device_val = self.cmb_camera.currentData()
            if camera_device_val is None:
                camera_device_val = 0

            cfg = {
                "gemini_api_key": self.inp_gemini.text().strip(),
                "openrouter_api_key": self.inp_openrouter.text().strip(),
                "deepseek_api_key": self.inp_deepseek.text().strip(),
                "groq_api_key": self.inp_groq.text().strip(),
                "telegram_bot_token": self.inp_telegram_token.text().strip(),
                "telegram_chat_id": self.inp_telegram_chat_id.text().strip(),
                "telegram_ai_provider": self.cmb_tel_ai.currentData(),
                "ai_provider": self.cmb_ai_provider.currentData(),
                "ollama_url": self.inp_ollama_url.text().strip(),
                "ollama_model": self.inp_ollama_model.text().strip(),
                "performance_quality": self.sld_performance.value(),
                "jarvis_voice": self.cmb_voice.currentData(),
                "jarvis_theme": theme_val,
                "gpu_acceleration": self.chk_gpu.isChecked(),
                "mic_device": self.cmb_mic.currentData(),
                "mic_sensitivity": self.sld_mic_sens.value() / 10000.0,
                "speaker_device": self.cmb_speaker.currentData(),
                "camera_device": camera_device_val,
                "camera_ip": self.inp_camera_ip.text().strip(),
                "timezone": self.cmb_timezone.currentData(),
                "user_name": self.inp_user_name.text().strip() or "Señor",
                "spotify_client_id": self.inp_spotify_id.text().strip(),
                "spotify_client_secret": self.inp_spotify_secret.text().strip(),
                "spotify_redirect_uri": self.inp_spotify_uri.text().strip()
            }
            save_api_keys(cfg)
            
            apply_theme_tokens(theme_val)
            
            parent = self.parent()
            if parent:
                parent.update_theme_styles()
                # Dynamically update WebEngine performance on the fly!
                if hasattr(parent, "orb") and parent.orb:
                    parent.orb.web_view.page().runJavaScript(
                        f"if (window.updatePerformance) window.updatePerformance({self.sld_performance.value()});"
                    )
                
            QMessageBox.information(self, "Success", "JARVIS Configurations saved, sir.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def check_spotify_auth_status(self):
        try:
            # If left blank, we fallback to pre-filled credentials
            client_id = self.inp_spotify_id.text().strip() or "455d312ba37a4e0c8be373b53f6305a4"
            client_secret = self.inp_spotify_secret.text().strip() or "5a075d9e504c4f3cb4cc6c5e533d1b4a"
            redirect_uri = self.inp_spotify_uri.text().strip() or "http://127.0.0.1:8888/callback"
            
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            sp_oauth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                open_browser=False
            )
            token = sp_oauth.get_cached_token()
            if token:
                self.lbl_spotify_status.setStyleSheet("color: #1DB954; font-weight: bold;")
                return "Conectado"
            else:
                self.lbl_spotify_status.setStyleSheet("color: #e11d48; font-weight: bold;")
                return "Desconectado"
        except Exception as e:
            self.lbl_spotify_status.setStyleSheet("color: #e11d48; font-style: italic;")
            return f"Error: {e}"

    def connect_spotify(self):
        """Launch a local HTTP server that handles the Spotify OAuth flow and opens
        the branded spotify_auth.html page in the system default browser.
        The user clicks 'Connect', the browser is redirected to Spotify's login,
        and the callback is caught by our local server — no manual URL copying needed."""
        import threading
        import webbrowser
        import socket
        from pathlib import Path as _Path
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import urllib.parse

        client_id = self.inp_spotify_id.text().strip() or "455d312ba37a4e0c8be373b53f6305a4"
        client_secret = self.inp_spotify_secret.text().strip() or "5a075d9e504c4f3cb4cc6c5e533d1b4a"
        redirect_uri = "http://127.0.0.1:8765/callback"

        # Save credentials
        try:
            from memory.config_manager import load_api_keys, save_api_keys
            cfg = load_api_keys()
            cfg["spotify_client_id"] = self.inp_spotify_id.text().strip()
            cfg["spotify_client_secret"] = self.inp_spotify_secret.text().strip()
            cfg["spotify_redirect_uri"] = redirect_uri
            save_api_keys(cfg)
        except Exception:
            pass

        self.lbl_spotify_status.setText("Abriendo navegador...")
        self.lbl_spotify_status.setStyleSheet("color: #fbbf24; font-style: italic;")
        self.btn_spotify_login.setEnabled(False)

        auth_html_path = _Path(__file__).parent / "assets" / "spotify_auth.html"

        # ── Build SpotifyOAuth URL ───────────────────────────────────────────
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            sp_oauth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope="user-modify-playback-state user-read-playback-state user-read-currently-playing",
                open_browser=False,
                cache_path=str(_Path(__file__).parent / ".spotify_cache")
            )
            auth_url = sp_oauth.get_authorize_url()
        except Exception as e:
            self.spotify_auth_failed(f"Error generando URL de auth: {e}")
            return

        auth_complete = threading.Event()
        auth_result = {"success": False, "error": ""}

        # ── Local HTTP server handles /callback + /spotify/* API ─────────────
        outer_self = self

        class _SpotifyCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass  # Silence access logs

            def _send_json(self, data: dict, code: int = 200):
                import json as _json
                body = _json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _serve_file(self, path: str):
                try:
                    with open(path, "rb") as f:
                        content = f.read()
                    ext = path.rsplit(".", 1)[-1]
                    ctype = {"html": "text/html", "css": "text/css", "js": "application/javascript"}.get(ext, "text/plain")
                    self.send_response(200)
                    self.send_header("Content-Type", f"{ctype}; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                except Exception:
                    self.send_response(404)
                    self.end_headers()

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)

                if parsed.path == "/" or parsed.path == "/index.html":
                    self._serve_file(str(auth_html_path))

                elif parsed.path == "/callback":
                    # Spotify redirected back with ?code=...
                    code = qs.get("code", [None])[0]
                    error = qs.get("error", [None])[0]
                    if error:
                        auth_result["error"] = error
                        self._send_json({"status": "error", "message": error})
                        auth_complete.set()
                    elif code:
                        try:
                            sp_oauth.get_access_token(code, as_dict=False)
                            auth_result["success"] = True
                            # Serve a clean, beautiful success page without emojis
                            success_html = (
                                "<!DOCTYPE html>"
                                "<html lang='es'>"
                                "<head>"
                                "  <meta charset='utf-8'>"
                                "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                                "  <title>JARVIS - Conectado</title>"
                                "  <link href='https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap' rel='stylesheet'>"
                                "  <style>"
                                "    body { background: #060400; color: #fde68a; font-family: 'Outfit', sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }"
                                "    .container { text-align: center; background: rgba(28, 20, 4, 0.85); border: 1.5px solid rgba(245, 158, 11, 0.4); border-radius: 20px; padding: 40px; box-shadow: 0 0 40px rgba(29, 185, 84, 0.15); max-width: 90%; width: 400px; animation: entry 0.5s ease-out; }"
                                "    h1 { color: #fff; font-size: 24px; margin-top: 15px; margin-bottom: 10px; }"
                                "    p { color: rgba(253, 230, 138, 0.6); font-size: 14px; line-height: 1.5; }"
                                "    .icon-wrapper { display: flex; justify-content: center; margin-bottom: 20px; }"
                                "    @keyframes entry { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }"
                                "  </style>"
                                "</head>"
                                "<body>"
                                "  <div class='container'>"
                                "    <div class='icon-wrapper'>"
                                "      <svg width='64' height='64' viewBox='0 0 24 24' fill='none' stroke='#1DB954' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
                                "        <path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'></path>"
                                "        <polyline points='22 4 12 14.01 9 11.01'></polyline>"
                                "      </svg>"
                                "    </div>"
                                "    <h1>Spotify Conectado</h1>"
                                "    <p>La vinculación con JARVIS se ha completado con éxito.<br>Ya puedes cerrar esta pestaña y volver a la aplicación.</p>"
                                "  </div>"
                                "</body>"
                                "</html>"
                            ).encode("utf-8")

                            self.send_response(200)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(success_html)
                            auth_complete.set()
                        except Exception as ex:
                            auth_result["error"] = str(ex)
                            self._send_json({"status": "error", "message": str(ex)})
                            auth_complete.set()
                    else:
                        self._send_json({"status": "error", "message": "Sin código"})

                elif parsed.path == "/spotify/status":
                    connected = auth_result["success"]
                    self._send_json({"connected": connected})

                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/spotify/auth":
                    # Pass the authentication URL back to the webpage so it redirects in-place
                    self._send_json({"status": "ok", "message": "Auth URL generated", "auth_url": auth_url})
                else:
                    self.send_response(404)
                    self.end_headers()

        def _run_server():
            try:
                server = HTTPServer(("127.0.0.1", 8765), _SpotifyCallbackHandler)
                server.timeout = 1.0
                deadline = 300  # Max 5 minutes
                elapsed = 0
                while not auth_complete.is_set() and elapsed < deadline:
                    server.handle_request()
                    elapsed += 1
                server.server_close()

                if auth_result["success"]:
                    QTimer.singleShot(0, outer_self.spotify_auth_success)
                else:
                    err = auth_result.get("error", "Tiempo agotado o cancelado")
                    QTimer.singleShot(0, lambda: outer_self.spotify_auth_failed(err))
            except Exception as ex:
                QTimer.singleShot(0, lambda: outer_self.spotify_auth_failed(str(ex)))

        threading.Thread(target=_run_server, daemon=True).start()

        # Open the Spotify authorization page directly in the user's default browser
        def _open_browser():
            import time
            time.sleep(0.5)  # Let server start
            webbrowser.open(auth_url)

        threading.Thread(target=_open_browser, daemon=True).start()

    def spotify_auth_success(self):
        self.btn_spotify_login.setEnabled(True)
        self.lbl_spotify_status.setText("Conectado")
        self.lbl_spotify_status.setStyleSheet("color: #1DB954; font-weight: bold;")
        QMessageBox.information(self, "Spotify API", "¡Autenticación con Spotify exitosa, sir!")

    def spotify_auth_failed(self, error):
        self.btn_spotify_login.setEnabled(True)
        self.lbl_spotify_status.setText("Error")
        self.lbl_spotify_status.setStyleSheet("color: #e11d48; font-weight: bold;")
        QMessageBox.critical(self, "Spotify API Error", f"Fallo al conectar: {error}")

    def update_style(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C_BG};
                border: 2px solid {C_PRI};
                border-radius: 10px;
            }}
            QLabel {{
                color: {C_TEXT};
                font-weight: bold;
            }}
            QLineEdit, QComboBox {{
                background: rgba(0,0,0,0.4);
                border: 1px solid {C_BORDER};
                color: white;
                padding: 5px;
                border-radius: 4px;
            }}
            QCheckBox {{
                color: {C_PRI};
                font-weight: bold;
            }}
            QPushButton {{
                background-color: {C_PRI};
                color: black;
                font-weight: bold;
                padding: 6px 15px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: white;
            }}
        """)


class MainWindow(QMainWindow):
    _shutdown_sig = pyqtSignal()
    _holo_sig = pyqtSignal(str, str)

    def __init__(self, ui, face_path):
        super().__init__()
        self.ui = ui
        self.ui._win = self
        self.camera_window = None
        
        self.resize(1050, 760)
        self.setMinimumSize(1000, 750)
        self.setWindowTitle("JARVIS-AI-HUD")
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.central_widget)
        
        icon_path = Path(__file__).parent / "assets" / "jarvis_icono.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            
        self.header_container = QWidget(self.central_widget)
        header_bar = QHBoxLayout(self.header_container)
        header_bar.setContentsMargins(15, 8, 15, 8)
        
        self.lbl_brand = QLabel("J A R V I S")
        font = QFont("Century Gothic", 16, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8.0)
        self.lbl_brand.setFont(font)
        header_bar.addWidget(self.lbl_brand)
        header_bar.addStretch()
        
        self.btn_protocols = QPushButton()
        self.btn_settings = QPushButton()
        self.btn_camera = QPushButton()
        self.btn_play = QPushButton()
        self.btn_folder = QPushButton()
        self.btn_min = QPushButton()
        self.btn_close = QPushButton()
        
        self.head_buttons = [
            (self.btn_protocols, 'fa5s.project-diagram', self._open_protocols),
            (self.btn_settings, 'fa5s.cog', self._open_settings),
            (self.btn_camera, 'fa5s.video', self._toggle_camera_gestures),
            (self.btn_play, 'fa5s.play', self._toggle_mute),
            (self.btn_folder, 'fa5s.folder', self._open_folder),
            (self.btn_min, 'fa5s.window-minimize', self.showMinimized),
            (self.btn_close, 'fa5s.times', self.close)
        ]
        
        for btn, icon, cb in self.head_buttons:
            btn.setFixedSize(28, 28)
            btn.clicked.connect(cb)
            header_bar.addWidget(btn)
            
        self.orb = CustomParticleOrb(self.ui, self.central_widget)
        
        # Symmetrical Bento overlay dashboard container at bottom half
        self.bento_container = QWidget(self.central_widget)
        bento_layout = QGridLayout(self.bento_container)
        bento_layout.setContentsMargins(0, 0, 0, 0)
        bento_layout.setSpacing(15)
        
        # Aligned stretches
        bento_layout.setColumnStretch(0, 1)
        bento_layout.setColumnStretch(1, 1)
        bento_layout.setColumnStretch(2, 1)
        bento_layout.setColumnStretch(3, 1)
        
        self.spotify_w = SpotifyWidget()
        self.system_w = SystemWidget()
        self.todo_w = TodoWidget()
        self.notes_w = NotesWidget()
        self.files_panel = FilesPanel(self.ui)
        self.weather_w = WeatherWidget()
        
        # Highly Organized Symmetrical 2-row, 4-column layout at bottom half
        # Row 0
        bento_layout.addWidget(self.spotify_w, 0, 0, 1, 2)
        bento_layout.addWidget(self.weather_w, 0, 2, 1, 1)
        bento_layout.addWidget(self.system_w, 0, 3, 1, 1)
        
        # Row 1
        bento_layout.addWidget(self.todo_w, 1, 0, 1, 1)
        bento_layout.addWidget(self.notes_w, 1, 1, 1, 2)
        bento_layout.addWidget(self.files_panel, 1, 3, 1, 1)
        
        # Clean floating digital Clock Widget at top-right corner
        self.clock_w = ClockWidget(self.central_widget)
        
        # Dedicated Holographic Closed Captions Speech Area (Single centered line)
        self.txt_console = QLabel(self.central_widget)
        self.txt_console.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_console.setWordWrap(True)
        
        # Force Close flag and System Tray initialization
        self._force_close = False
        self.tray_icon = None
        self._setup_tray_icon()
        
        # Instantiate the HolographicWidget ONCE
        try:
            self.hologram = HolographicWidget(parent=self)
            self.hologram.hide()
        except Exception as e:
            print(f"[UI] Error init hologram: {e}")
            self.hologram = None
            
        self.update_theme_styles()
        self._drag_pos = None
        self._shutdown_sig.connect(self._handle_shutdown)
        self._holo_sig.connect(self._handle_holo)
        
    def _handle_holo(self, url, html):
        if self.hologram:
            self.hologram.show_content(url=url if url else None, html=html if html else None)

    def update_theme_styles(self):
        self.central_widget.setStyleSheet(f"""
            QWidget#centralWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(28, 21, 6, 0.90), stop:1 rgba(10, 7, 2, 0.90));
                border: 2.2px solid {C_PRI};
                border-radius: 20px;
            }}
        """)
        self.lbl_brand.setStyleSheet(f"color: {C_PRI}; font-weight: bold; background: transparent;")
        
        for btn, icon, cb in self.head_buttons:
            if HAS_QTA:
                btn.setIcon(qta.icon(icon, color=C_PRI_DIM))
            btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid rgba(120,53,15,0.35); border-radius: 14px; }} QPushButton:hover {{ background: rgba(245,158,11,0.1); border-color: {C_PRI}; }}")
            
        self.txt_console.setStyleSheet(f"QLabel {{ color: {C_PRI}; font-weight: bold; font-size: 15px; background: transparent; }}")
        
        self.spotify_w.update_style()
        self.system_w.update_style()
        self.todo_w.update_style()
        self.notes_w.update_style()
        self.files_panel.update_style()
        self.clock_w.update_style()
        self.weather_w.update_style()
        
        if hasattr(self, "orb"):
            self.orb.sync_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        W = self.central_widget.width()
        H = self.central_widget.height()
        
        self.header_container.setGeometry(0, 0, W, 45)
        
        # Position digital Clock floating at top-right
        self.clock_w.setGeometry(W - 260, 50, 240, 70)
        
        # Position background Particle Orb Web capsule
        self.orb.setGeometry(0, 45, W, H - 45)
        
        # Position centered continuous speech line at bottom of HUD
        self.txt_console.setGeometry(30, H - 60, W - 60, 45)
        
        # Bento overlay container Y starts lower and ends exactly flush on top of the subtitles (gap-free!)
        bh = H // 3 + 30   # bottom-third height, lower widgets
        by = H - bh - 60   # positioned flush directly above speech subtitles
        self.bento_container.setGeometry(15, by, W - 30, bh)
        
        self.bento_container.raise_()
        self.txt_console.raise_()
        self.clock_w.raise_()

    def _open_settings(self):
        dialog = DeviceSettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.ui.on_config_saved:
                from memory.config_manager import load_api_keys
                self.ui.on_config_saved(load_api_keys())
                
    def _open_protocols(self):
        dialog = ProtocolDialog(self)
        dialog.exec()
            
    def _open_folder(self):
        try:
            from memory.config_manager import BASE_DIR
            os.startfile(BASE_DIR)
        except Exception:
            pass
            
    def _toggle_mute(self):
        self.ui.muted = not self.ui.muted
        self.orb.set_state("MUTED" if self.ui.muted else "LISTENING")
        if self.ui.muted:
            if self.ui.on_stop_command:
                self.ui.on_stop_command()

    def _force_camera_off(self):
        """Hard stops the camera and resets UI state."""
        if getattr(self, '_gesture_thread', None):
            self._gesture_thread.stop()
            self._gesture_thread = None
        if getattr(self, 'camera_window', None):
            self.camera_window.hide()
            self.camera_window = None
        print("[UI] Camera completely stopped via X button.")

    def _toggle_camera_gestures(self):
        """Toggle camera gesture preview. The GestureTrackingThread persists in the background
        even when the preview window is hidden, so gestures keep working at all times."""
        from PyQt6.QtWidgets import QMessageBox

        # ── If tracking thread is not running yet, start it ─────────────────
        if not hasattr(self, '_gesture_thread') or self._gesture_thread is None:
            try:
                from actions.gesture_engine import GestureTrackingThread
                # Resolve camera source from config
                camera_index = 0
                try:
                    from memory.config_manager import load_api_keys
                    cfg = load_api_keys()
                    camera_ip = cfg.get("camera_ip", "").strip()
                    if camera_ip:
                        if camera_ip.startswith(("http://", "https://")):
                            camera_index = camera_ip
                        elif ":" in camera_ip:
                            camera_index = f"http://{camera_ip}/video"
                        else:
                            camera_index = f"http://{camera_ip}:4747/video"
                        import urllib.request
                        try:
                            urllib.request.urlopen(camera_index, timeout=0.5)
                        except Exception:
                            camera_index = int(cfg.get("camera_device", 0))
                    else:
                        camera_index = int(cfg.get("camera_device", 0))
                except Exception:
                    camera_index = 0

                self._gesture_thread = GestureTrackingThread(
                    camera_index=camera_index,
                    theme_bgr=hex_to_bgr(C_PRI),
                    text_bgr=hex_to_bgr(C_TEXT)
                )
                self._gesture_thread.start()
                print("[UI] Gesture tracking thread started (background).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Fallo al iniciar la cámara gestual:\n{e}")
                return

        # ── Toggle the preview window ────────────────────────────────────────
        if self.camera_window is None:
            self.camera_window = CameraPreviewWindow(shared_thread=self._gesture_thread, on_close_callback=self._force_camera_off, parent=None)
            self.camera_window.attach_thread(self._gesture_thread)
            self.camera_window.show()
            self.camera_window.move(50, 50)
            print("[UI] Camera Preview Window shown.")
        else:
            if self.camera_window.isVisible():
                self.camera_window.hide()
                print("[UI] Camera Preview Window hidden — tracking continues.")
            else:
                self.camera_window.show()
                self.camera_window.raise_()
                print("[UI] Camera Preview Window restored.")

    def stop_gesture_thread(self):
        """Cleanly stop the background gesture tracking thread on JARVIS exit."""
        if hasattr(self, '_gesture_thread') and self._gesture_thread is not None:
            self._gesture_thread.stop()
            self._gesture_thread = None
            print("[UI] Gesture tracking thread stopped.")

    def _setup_tray_icon(self):
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = Path(__file__).parent / "assets" / "jarvis_icono.ico"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            from PyQt6.QtWidgets import QStyle
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            
        tray_menu = QMenu(self)
        
        show_action = tray_menu.addAction("Mostrar JARVIS")
        show_action.triggered.connect(self.show_and_activate)
        
        mute_action = tray_menu.addAction("Silenciar/Escuchar")
        mute_action.triggered.connect(self._toggle_mute)
        
        tray_menu.addSeparator()
        
        exit_action = tray_menu.addAction("Salir")
        exit_action.triggered.connect(self._exit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def show_and_activate(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _exit_application(self):
        self._force_close = True
        if getattr(self, 'camera_window', None):
            self.camera_window.hide()
        QApplication.quit()
        import os
        os._exit(0)

    def _handle_shutdown(self):
        self._force_close = True
        QApplication.quit()
        import os
        os._exit(0)

    def _on_tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger):
            if self.isVisible():
                self.hide()
            else:
                self.show_and_activate()

    def closeEvent(self, event):
        if getattr(self, "_force_close", False):
            # Stop gesture tracking thread on full exit
            self.stop_gesture_thread()
            event.accept()
        else:
            event.ignore()
            self.hide()
            if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
                from PyQt6.QtWidgets import QSystemTrayIcon
                self.tray_icon.showMessage(
                    "JARVIS AI",
                    "Sigo activo en segundo plano. Presiona Insert para hablar o haz doble clic aquí para mostrarme.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


class MockRoot:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp
        
    def mainloop(self):
        sys.exit(self.qapp.exec())
        
    def after(self, ms: int, func):
        QTimer.singleShot(ms, func)


class JarvisUI:
    def __init__(self, face_path=""):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.root = MockRoot(self.app)
        
        self.muted = False
        self.current_file = ""
        
        self.on_text_command = None
        self.on_stop_command = None
        self.on_config_saved = None
        
        self.jarvis_response_buffer = ""
        
        self._win = MainWindow(self, face_path)
        self._win.show()
        
        # Ensure startup shortcut is set up after 2 seconds (so it doesn't block startup)
        QTimer.singleShot(2000, self.ensure_startup_shortcut)
        
    def wait_for_api_key(self):
        pass

    def write_log(self, text: str):
        pass
        
    def set_state(self, state: str):
        self._win.orb.set_state(state)
        if state == "MUTED":
            self.muted = True
        elif state in ("LISTENING", "SPEAKING", "THINKING"):
            if self.muted:
                self.muted = False
                
    def set_audio_level(self, level: float):
        self._win.orb.set_audio(level)
        
    def clear_jarvis_response(self):
        self.jarvis_response_buffer = ""
        self._win.txt_console.setText("")
        
    def stream_jarvis_chunk(self, chunk: str):
        text = chunk.replace("JARVIS:", "").strip()
        if text:
            if self.jarvis_response_buffer:
                self.jarvis_response_buffer += " " + text
            else:
                self.jarvis_response_buffer = text
            self._win.txt_console.setText(self.jarvis_response_buffer)

    def ensure_startup_shortcut(self):
        try:
            import os
            import subprocess
            appdata = os.getenv('APPDATA')
            if not appdata:
                return
            startup_dir = os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            shortcut_path = os.path.join(startup_dir, 'JARVIS AI.lnk')
            
            current_dir = os.path.abspath(os.path.dirname(__file__))
            target_vbs = os.path.join(current_dir, "Iniciar JARVIS Beta.vbs")
            icon_path = os.path.join(current_dir, "assets", "jarvis_icono.ico")
            
            if not os.path.exists(target_vbs):
                return
                
            ps_cmd = (
                f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{shortcut_path}');"
                f"$s.TargetPath='{target_vbs}';"
                f"$s.WorkingDirectory='{current_dir}';"
                f"$s.IconLocation='{icon_path}';"
                f"$s.Description='Lanzador Automatico de JARVIS AI (Admin)';"
                f"$s.Save()"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            print("[STARTUP] Startup shortcut ensured successfully.")
        except Exception as e:
            print(f"[STARTUP] Error ensuring startup shortcut: {e}")

class ProtocolDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Protocolos (Workspaces)")
        self.resize(500, 400)
        self.setStyleSheet("background-color: #0f0a02; color: #fde68a;")
        
        layout = QVBoxLayout(self)
        
        # Lista de protocolos
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("background-color: rgba(35, 28, 10, 0.7); border: 1px solid #f59e0b; border-radius: 5px; padding: 5px;")
        self.list_widget.itemClicked.connect(self._load_selected)
        layout.addWidget(QLabel("Tus Protocolos:"))
        layout.addWidget(self.list_widget)
        
        # Editor
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nombre del protocolo (ej. Ocio)")
        self.txt_name.setStyleSheet("background-color: #1a1405; border: 1px solid #f59e0b; padding: 5px;")
        layout.addWidget(self.txt_name)
        
        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText("Instrucciones para JARVIS (ej. 'Abre Steam y Spotify al 30%')")
        self.txt_desc.setStyleSheet("background-color: #1a1405; border: 1px solid #f59e0b; padding: 5px;")
        layout.addWidget(self.txt_desc)
        
        # Botones
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar Protocolo")
        self.btn_save.setStyleSheet("background-color: #f59e0b; color: black; font-weight: bold; padding: 5px;")
        self.btn_save.clicked.connect(self._save_protocol)
        
        self.btn_del = QPushButton("Eliminar")
        self.btn_del.setStyleSheet("background-color: #78350f; color: white; padding: 5px;")
        self.btn_del.clicked.connect(self._delete_protocol)
        
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_del)
        layout.addLayout(btn_layout)
        
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        try:
            from core.protocols import load_protocols
            data = load_protocols()
            for k in data.keys():
                self.list_widget.addItem(k.title())
        except Exception:
            pass

    def _load_selected(self, item):
        self.txt_name.setText(item.text())
        try:
            from core.protocols import get_protocol
            self.txt_desc.setText(get_protocol(item.text()) or "")
        except:
            pass

    def _save_protocol(self):
        name = self.txt_name.text().strip()
        desc = self.txt_desc.toPlainText().strip()
        if not name or not desc:
            QMessageBox.warning(self, "Error", "El nombre e instrucciones no pueden estar vacíos.")
            return
        try:
            from core.protocols import add_protocol
            add_protocol(name, desc)
            QMessageBox.information(self, "Éxito", f"Protocolo '{name}' guardado.")
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _delete_protocol(self):
        name = self.txt_name.text().strip()
        if name:
            try:
                from core.protocols import delete_protocol
                delete_protocol(name)
                self.txt_name.clear()
                self.txt_desc.clear()
                self._refresh_list()
            except Exception as e:
                pass

class HolographicWidget(QWidget):
    def __init__(self, title="JARVIS Intelligence", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        self.container = QWidget(self)
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 10, 2, 200);
                border: 2px solid rgba(218, 165, 32, 220);
                border-radius: 12px;
            }
            QLabel {
                color: #FFD700;
                font-family: 'Consolas', 'Courier New', monospace;
                border: none;
                background: transparent;
            }
        """)
        
        container_layout = QVBoxLayout(self.container)
        
        self.lbl_title = QLabel(f"✨ {title}")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; border-bottom: 1px solid rgba(218, 165, 32, 100); padding-bottom: 5px;")
        container_layout.addWidget(self.lbl_title)
        
        from PyQt6.QtWidgets import QTextBrowser
        self.text_browser = QTextBrowser()
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: #FFD700;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 14px;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: rgba(218, 165, 32, 0.5);
                border-radius: 4px;
            }
        """)
        self.text_browser.setOpenExternalLinks(True)
        
        container_layout.addWidget(self.text_browser)
        layout.addWidget(self.container)
        
        self.resize(500, 350)
        
        # Posicionar en esquina inferior derecha
        screen_geo = QApplication.primaryScreen().geometry()
        self.move(screen_geo.width() - 530, screen_geo.height() - 400)
        
        self.setWindowOpacity(0.0)
        
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(600)
        
    def show_content(self, url: str = None, html: str = None):
        if html:
            self.text_browser.setHtml(html)
        elif url:
            # Si se manda URL sin HTML, simplemente la ponemos como link
            self.text_browser.setHtml(f"<a href='{url}' style='color: #FFA500;'>Haz clic aquí para abrir el enlace: {url}</a>")
            
        self.show()
        self.animation.stop()
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(1.0)
        self.animation.start()
        
        # Ocultar automáticamente después de 20 segundos
        QTimer.singleShot(20000, self.hide_content)
        
    def hide_content(self):
        self.animation.stop()
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(0.0)
        self.animation.start()
        self.animation.finished.connect(self.hide)
