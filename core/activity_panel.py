"""
core/activity_panel.py — Mini panel lateral con la actividad de JARVIS.

Ventana flotante, sin marco, esquina inferior-derecha (o donde se coloque),
mostrando:
  • Herramienta activa actualmente
  • Plan multi-paso del AgentRunner si está corriendo
  • Lista de tareas en curso (TaskQueue)
  • Botón "Cancelar" en cada tarea

Diseño minimalista, estilo holograma dorado (a juego con el resto del UI).
"""
from __future__ import annotations
import time

try:
    from PyQt6.QtCore    import Qt, QTimer, QPoint
    from PyQt6.QtGui     import QFont, QColor, QPalette
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QScrollArea, QFrame, QApplication
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False

try:
    from core.task_queue import list_tasks, cancel as cancel_task
except Exception:
    list_tasks = lambda: []
    cancel_task = lambda tid: False


_GOLD       = "#D4AF37"
_GOLD_DIM   = "#8a7220"
_BG         = "rgba(8, 8, 12, 230)"
_BG_HOVER   = "rgba(20, 20, 28, 245)"
_TEXT       = "#F2E6BD"
_DIM_TEXT   = "#7e7350"


if HAS_QT:
    class ActivityPanel(QWidget):
        """Panel flotante con estado en vivo."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setMinimumWidth(280)
            self.setMaximumWidth(360)

            self._current_tool = ""
            self._current_plan = []
            self._build_ui()
            self._dragging = False
            self._drag_offset = QPoint()

            # Refresh tasks every 750ms
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.refresh)
            self._timer.start(750)

        def _build_ui(self):
            self.setStyleSheet(f"""
                QWidget {{
                    background: {_BG};
                    color: {_TEXT};
                    font-family: 'Consolas','Courier New',monospace;
                    font-size: 11px;
                    border: 1px solid {_GOLD_DIM};
                    border-radius: 8px;
                }}
                QLabel#title {{
                    color: {_GOLD};
                    font-weight: bold;
                    font-size: 12px;
                    padding: 4px 8px;
                    border: none;
                }}
                QLabel#tool {{
                    color: {_GOLD};
                    padding: 2px 8px;
                    border: none;
                }}
                QLabel.task-title {{
                    color: {_TEXT};
                    border: none;
                }}
                QLabel.task-dim {{
                    color: {_DIM_TEXT};
                    border: none;
                    font-size: 10px;
                }}
                QPushButton {{
                    background: transparent;
                    color: {_GOLD};
                    border: 1px solid {_GOLD_DIM};
                    border-radius: 3px;
                    padding: 2px 6px;
                }}
                QPushButton:hover {{
                    background: {_BG_HOVER};
                }}
                QScrollArea, QFrame {{
                    border: none;
                    background: transparent;
                }}
            """)

            root = QVBoxLayout(self)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(4)

            # Header (drag-area + close)
            head = QHBoxLayout()
            title = QLabel("◈ JARVIS Activity")
            title.setObjectName("title")
            head.addWidget(title)
            head.addStretch()
            close = QPushButton("×")
            close.setFixedSize(20, 20)
            close.clicked.connect(self.hide)
            head.addWidget(close)
            root.addLayout(head)

            # Tool actual
            self.tool_label = QLabel("⌁ idle")
            self.tool_label.setObjectName("tool")
            root.addWidget(self.tool_label)

            # Plan / pasos
            self.plan_frame = QFrame()
            self.plan_layout = QVBoxLayout(self.plan_frame)
            self.plan_layout.setContentsMargins(8, 2, 8, 2)
            self.plan_layout.setSpacing(2)
            root.addWidget(self.plan_frame)

            # Lista de tareas
            self.tasks_frame = QFrame()
            self.tasks_layout = QVBoxLayout(self.tasks_frame)
            self.tasks_layout.setContentsMargins(4, 4, 4, 4)
            self.tasks_layout.setSpacing(3)
            root.addWidget(self.tasks_frame)

            root.addStretch()

        # ── API pública ───────────────────────────────────────────────────────
        def set_current_tool(self, tool_name: str):
            self._current_tool = tool_name
            self.tool_label.setText(f"⌁ {tool_name}" if tool_name else "⌁ idle")

        def set_plan(self, steps: list[str], current_idx: int = -1):
            self._current_plan = steps
            self._render_plan(current_idx)

        def _render_plan(self, current_idx: int = -1):
            # Limpiar
            while self.plan_layout.count():
                item = self.plan_layout.takeAt(0)
                w = item.widget()
                if w: w.deleteLater()
            for i, step in enumerate(self._current_plan):
                prefix = "▶" if i == current_idx else ("✓" if i < current_idx else "○")
                lbl = QLabel(f"  {prefix} {step[:50]}")
                lbl.setProperty("class", "task-dim")
                lbl.setStyleSheet(
                    f"color: {_GOLD if i == current_idx else _DIM_TEXT}; border: none;"
                )
                self.plan_layout.addWidget(lbl)

        # ── Refresco automático de tareas ─────────────────────────────────────
        def refresh(self):
            try:
                # Limpiar lista actual
                while self.tasks_layout.count():
                    item = self.tasks_layout.takeAt(0)
                    w = item.widget()
                    if w: w.deleteLater()

                tasks = list_tasks(limit=8)
                running = [t for t in tasks if t.status == "running"]

                if not running:
                    # Mostrar las últimas terminadas
                    recent = [t for t in tasks if t.status in ("done","failed","cancelled")][:3]
                    if recent:
                        lbl = QLabel("— recientes —")
                        lbl.setStyleSheet(f"color:{_DIM_TEXT}; border:none; font-size:9px;")
                        self.tasks_layout.addWidget(lbl)
                        for t in recent:
                            self._add_task_row(t, with_cancel=False)
                    return

                lbl = QLabel(f"— {len(running)} en curso —")
                lbl.setStyleSheet(f"color:{_GOLD}; border:none; font-size:10px;")
                self.tasks_layout.addWidget(lbl)
                for t in running:
                    self._add_task_row(t, with_cancel=True)
            except Exception:
                pass

        def _add_task_row(self, task, with_cancel: bool = True):
            row = QFrame()
            h = QHBoxLayout(row)
            h.setContentsMargins(2, 2, 2, 2)
            h.setSpacing(4)

            icon = {"running":"▶","done":"✓","failed":"✗","cancelled":"⊘","pending":"…"}.get(task.status, "·")
            color = {
                "running":   _GOLD,
                "done":      "#7ed87e",
                "failed":    "#e07070",
                "cancelled": _DIM_TEXT,
                "pending":   _DIM_TEXT,
            }.get(task.status, _TEXT)

            txt = QLabel(f"{icon} {task.title[:32]}")
            txt.setStyleSheet(f"color:{color}; border:none;")
            h.addWidget(txt)
            h.addStretch()

            dur = QLabel(f"{int(task.duration_s())}s")
            dur.setStyleSheet(f"color:{_DIM_TEXT}; border:none; font-size:9px;")
            h.addWidget(dur)

            if with_cancel:
                btn = QPushButton("×")
                btn.setFixedSize(18, 18)
                btn.clicked.connect(lambda _, tid=task.id: cancel_task(tid))
                h.addWidget(btn)

            self.tasks_layout.addWidget(row)

        # ── Drag para mover ───────────────────────────────────────────────────
        def mousePressEvent(self, ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._dragging    = True
                self._drag_offset = ev.globalPosition().toPoint() - self.pos()

        def mouseMoveEvent(self, ev):
            if self._dragging:
                self.move(ev.globalPosition().toPoint() - self._drag_offset)

        def mouseReleaseEvent(self, ev):
            self._dragging = False


    def position_panel(panel: ActivityPanel):
        """Posicionar en esquina inferior-derecha de la pantalla principal."""
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + screen.width()  - panel.width()  - 20
            y = screen.y() + screen.height() - panel.height() - 80
            panel.move(x, y)
        except Exception:
            pass

else:
    # PyQt6 no disponible: stub vacío
    class ActivityPanel:
        def __init__(self, *a, **k): pass
        def set_current_tool(self, *a): pass
        def set_plan(self, *a): pass
        def refresh(self): pass
        def show(self): pass
        def hide(self): pass

    def position_panel(panel): pass
