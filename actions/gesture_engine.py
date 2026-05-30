# -*- coding: utf-8 -*-
"""
gesture_engine.py — High-fidelity webcam hand tracking and mouse gesture controller for JARVIS-IA.
Fully optimized using the modern MediaPipe Tasks HandLandmarker API for bulletproof Windows stability.

Gesture System:
  - Modo Cursor  : Índice + Medio extendidos, Anular + Meñique recogidos → mueve el ratón (EMA)
  - Click Izq.   : 1 snap rápido hacia abajo con índice+medio en modo cursor
  - Click Der.   : 2 snaps rápidos (< 0.6 s) en modo cursor
  - Modo Scroll  : Los 4 dedos extendidos (palma abierta) → scroll/hscroll según movimiento del centroide
"""
import os
import cv2
import time
import urllib.request
import numpy as np
import pyautogui
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

# Configure PyAutoGUI for high performance / low latency
pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = True

# Connection mapping for custom premium hand skeleton drawing
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (9, 10), (10, 11), (11, 12),              # Middle
    (13, 14), (14, 15), (15, 16),             # Ring
    (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
    (5, 9), (9, 13), (13, 17),                # Palm base joints
]


class GestureTrackingThread(QThread):
    """
    Background QThread that captures webcam video frames, runs the modern MediaPipe Tasks
    HandLandmarker model in VIDEO mode, executes smoothed OS mouse movements / clicks /
    scrolls, and emits processed frames to the Qt UI.
    """
    frame_signal = pyqtSignal(QImage, str)   # (processed holographic frame, status label)
    active_signal = pyqtSignal(bool)          # active state changes

    # ──────────────────────────────────────────────────────────────────────────
    def __init__(self, camera_index=0, theme_bgr=(11, 158, 245), text_bgr=(138, 230, 253), parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.theme_bgr    = theme_bgr
        self.text_bgr     = text_bgr
        self._running     = False

        # Model path
        self.model_path = Path("config/hand_landmarker.task")

        # Cursor smoothing (EMA — Exponential Moving Average)
        self.prev_x, self.prev_y = pyautogui.position()
        self.smoothing = 0.25

        # Screen dimensions
        self.screen_width, self.screen_height = pyautogui.size()

        # Mouse Drag & Click States
        self.mouse_pressed = False
        self.last_right_click_time = 0.0
        self.last_pinch_release_time = 0.0
        self.click_sequence_coords = None
        self.pinch_start_time = 0.0

        # Scroll state
        self.prev_palm_x   = None
        self.prev_palm_y   = None
        self.last_scroll_time = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    def stop(self):
        """Safely stops the tracking thread."""
        self._running = False
        # Esperar como máximo 1000ms para evitar que cuelgue la UI principal si el controlador de la cámara se bloquea
        if not self.wait(1000):
            print("[Gesture Engine] El hilo no finalizó en 1s. Forzando terminación...")
            self.terminate()
            self.wait(500)

    # ──────────────────────────────────────────────────────────────────────────
    def _ensure_model_file(self):
        """Ensures the hand_landmarker.task file is downloaded and cached."""
        if not self.model_path.exists():
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            url = (
                "https://storage.googleapis.com/mediapipe-models/"
                "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            )
            print(f"[Gesture Engine] Downloading model from {url}...")
            urllib.request.urlretrieve(url, str(self.model_path.absolute()))
            print("[Gesture Engine] Model download complete.")

    # ──────────────────────────────────────────────────────────────────────────
    def run(self):
        print("[Thread] run() entered.", flush=True)
        self._ensure_model_file()

        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        print("[Thread] mediapipe tasks imported.", flush=True)

        self._running = True

        # ── Open video capture ────────────────────────────────────────────────
        print(f"[Thread] Opening camera {self.camera_index}...", flush=True)
        cap = None
        if isinstance(self.camera_index, int):
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                print(
                    f"[Gesture Engine] Default backend failed, "
                    f"trying DSHOW for camera {self.camera_index}...", flush=True
                )
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(self.camera_index)

        if cap is None or not cap.isOpened():
            print(f"[Gesture Engine] Error: Could not open camera {self.camera_index}", flush=True)
            self.active_signal.emit(False)
            return

        self.active_signal.emit(True)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # ── Build HandLandmarker ──────────────────────────────────────────────
        print("[Thread] Instantiating HandLandmarker...", flush=True)
        base_options = python.BaseOptions(model_asset_path=str(self.model_path.resolve()))
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            running_mode=vision.RunningMode.VIDEO,
        )
        detector = vision.HandLandmarker.create_from_options(options)
        print("[Thread] HandLandmarker successfully initialized.", flush=True)

        # ── Main capture loop ─────────────────────────────────────────────────
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            h, w, c = frame.shape

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            timestamp_ms = int(time.time() * 1000)
            result       = detector.detect_for_video(mp_image, timestamp_ms)

            status_text = "Buscando mano..."

            # HUD border & title
            cv2.rectangle(frame, (10, 10), (w - 10, h - 10), self.theme_bgr, 1)
            cv2.putText(
                frame, "JARVIS GESTURE PILOT", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.theme_bgr, 1, cv2.LINE_AA,
            )

            if result.hand_landmarks:
                for hand_landmarks in result.hand_landmarks:

                    # ── Draw holographic skeleton ─────────────────────────────
                    for conn in HAND_CONNECTIONS:
                        pt1 = hand_landmarks[conn[0]]
                        pt2 = hand_landmarks[conn[1]]
                        cv2.line(
                            frame,
                            (int(pt1.x * w), int(pt1.y * h)),
                            (int(pt2.x * w), int(pt2.y * h)),
                            self.theme_bgr, 1, cv2.LINE_AA,
                        )

                    # Joint nodes
                    for lm_id, lm in enumerate(hand_landmarks):
                        cx, cy = int(lm.x * w), int(lm.y * h)
                        if lm_id in (4, 8, 12, 16, 20):
                            cv2.circle(frame, (cx, cy), 5, self.text_bgr,   -1, cv2.LINE_AA)
                        else:
                            cv2.circle(frame, (cx, cy), 3, self.theme_bgr, -1, cv2.LINE_AA)

                    # ── Landmark references ───────────────────────────────────
                    index_tip  = hand_landmarks[8]
                    middle_tip = hand_landmarks[12]
                    ring_tip   = hand_landmarks[16]
                    pinky_tip  = hand_landmarks[20]

                    # Finger extension flags (tip Y < pip Y  →  extended)
                    index_up  = index_tip.y  < hand_landmarks[6].y
                    middle_up = middle_tip.y < hand_landmarks[10].y
                    ring_up   = ring_tip.y   < hand_landmarks[14].y
                    pinky_up  = pinky_tip.y  < hand_landmarks[18].y

                    todos_up     = index_up and middle_up and ring_up and pinky_up
                    cursor_mode  = index_up and middle_up and (not ring_up) and (not pinky_up)

                    curr_time = time.time()

                    # ── Calculate pinch distance (Thumb tip 4 to index landmarks 8, 7, 6) ────
                    thumb_tip = hand_landmarks[4]
                    d8 = ((thumb_tip.x - hand_landmarks[8].x)**2 + (thumb_tip.y - hand_landmarks[8].y)**2)**0.5
                    d7 = ((thumb_tip.x - hand_landmarks[7].x)**2 + (thumb_tip.y - hand_landmarks[7].y)**2)**0.5
                    d6 = ((thumb_tip.x - hand_landmarks[6].x)**2 + (thumb_tip.y - hand_landmarks[6].y)**2)**0.5
                    dist_thumb_index = min(d8, d7, d6)

                    curr_time = time.time()

                    # Define gesture states based on user specifications
                    # Umbral de contacto flexible (0.042) para mayor comodidad ergonómica lateral
                    is_right_click_gesture = todos_up and dist_thumb_index < 0.042
                    is_scroll_gesture = todos_up and dist_thumb_index >= 0.052
                    is_cursor_or_drag = cursor_mode or self.mouse_pressed

                    # ══════════════════════════════════════════════════════════
                    # MODO CLICK DERECHO — 4 dedos extendidos + pulgar apegado al índice
                    # ══════════════════════════════════════════════════════════
                    if is_right_click_gesture:
                        # Release left click if it was active
                        if self.mouse_pressed:
                            pyautogui.mouseUp(button='left')
                            self.mouse_pressed = False
                            print("[Gesture Engine] Left click released before right click.")

                        # Reset scroll state
                        self.prev_palm_x = None
                        self.prev_palm_y = None

                        # Click right with cooldown
                        if curr_time - self.last_right_click_time > 0.8:
                            pyautogui.click(button='right')
                            self.last_right_click_time = curr_time
                            status_text = "Click Derecho"
                            print("[Gesture Engine] Right click.")
                        else:
                            status_text = "Click Derecho (Cooldown)"

                    # ══════════════════════════════════════════════════════════
                    # MODO SCROLL — 4 dedos extendidos, pulgar libre (no apegado)
                    # ══════════════════════════════════════════════════════════
                    elif is_scroll_gesture:
                        # Release left click if it was active
                        if self.mouse_pressed:
                            pyautogui.mouseUp(button='left')
                            self.mouse_pressed = False
                            print("[Gesture Engine] Left click released before scrolling.")

                        status_text = "Scroll Activo ↕↔"

                        # Centroid across all 21 landmarks
                        palm_x = float(np.mean([lm.x for lm in hand_landmarks]))
                        palm_y = float(np.mean([lm.y for lm in hand_landmarks]))

                        if self.prev_palm_x is not None and self.prev_palm_y is not None:
                            dx = palm_x - self.prev_palm_x
                            dy = palm_y - self.prev_palm_y
                            scroll_threshold = 0.018

                            if curr_time - self.last_scroll_time > 0.06:
                                if abs(dy) >= scroll_threshold or abs(dx) >= scroll_threshold:
                                    if abs(dy) >= abs(dx):
                                        # Vertical scroll — dy > 0 means hand moved down -> scroll down
                                        if dy > 0:
                                            pyautogui.scroll(-5)
                                        else:
                                            pyautogui.scroll(5)
                                    else:
                                        # Horizontal scroll
                                        if dx > 0:
                                            pyautogui.hscroll(5)
                                        else:
                                            pyautogui.hscroll(-5)
                                    self.last_scroll_time = curr_time

                        self.prev_palm_x = palm_x
                        self.prev_palm_y = palm_y

                    # ══════════════════════════════════════════════════════════
                    # MODO CURSOR / ARRASTRE — índice y medio extendidos (o arrastre en curso)
                    # ══════════════════════════════════════════════════════════
                    elif is_cursor_or_drag:
                        # Reset scroll state
                        self.prev_palm_x = None
                        self.prev_palm_y = None

                        # Move cursor based on index finger knuckle (landmark 5) for total stability during pinch
                        ref_pt = hand_landmarks[5]

                        # Map normalized coords [0.25, 0.75] -> screen size
                        mapped_x = np.interp(ref_pt.x, (0.25, 0.75), (0, self.screen_width))
                        mapped_y = np.interp(ref_pt.y, (0.25, 0.75), (0, self.screen_height))

                        # EMA smoothing
                        target_x = self.prev_x + (mapped_x - self.prev_x) * self.smoothing
                        target_y = self.prev_y + (mapped_y - self.prev_y) * self.smoothing
                        target_x = max(0, min(self.screen_width  - 1, target_x))
                        target_y = max(0, min(self.screen_height - 1, target_y))

                        # Pinch (thumb-index) detection for left click and drag
                        is_pinched = dist_thumb_index < 0.042

                        if is_pinched:
                            if not self.mouse_pressed:
                                self.mouse_pressed = True
                                self.pinch_start_time = curr_time
                                
                                # Check if this is a rapid consecutive click in a multi-click sequence (< 0.45s)
                                time_since_release = curr_time - self.last_pinch_release_time
                                if time_since_release < 0.45 and self.click_sequence_coords is not None:
                                    # Use the exact same coordinates as the previous click to ensure Windows registers a perfect double-click!
                                    self.prev_x, self.prev_y = self.click_sequence_coords
                                else:
                                    # Start a new click sequence
                                    self.click_sequence_coords = (int(target_x), int(target_y))
                                    self.prev_x, self.prev_y = target_x, target_y

                                pyautogui.moveTo(int(self.prev_x), int(self.prev_y))
                                pyautogui.mouseDown(button='left')
                                print(f"[Gesture Engine] Left click down at {self.click_sequence_coords} (sequence time since release: {time_since_release:.3f}s)")
                            
                            # Freeze / Hold coordinate system during the first 0.3s of a pinch to prevent micro-movements/shaking!
                            pinch_duration = curr_time - self.pinch_start_time
                            if pinch_duration >= 0.3:
                                # After 0.3s, treat as an intentional click & drag
                                self.prev_x = target_x
                                self.prev_y = target_y
                                pyautogui.moveTo(int(self.prev_x), int(self.prev_y))
                                status_text = "Arrastrando..."
                            else:
                                # Keep cursor frozen during quick tap
                                pyautogui.moveTo(int(self.prev_x), int(self.prev_y))
                                status_text = "Click / Selección (Frozen)"
                        else:
                            if self.mouse_pressed and dist_thumb_index > 0.052:
                                pyautogui.mouseUp(button='left')
                                self.mouse_pressed = False
                                self.last_pinch_release_time = curr_time
                                print("[Gesture Engine] Left click up (drag release).")
                            
                            # In cursor mode (not pinched), move mouse freely
                            self.prev_x = target_x
                            self.prev_y = target_y
                            pyautogui.moveTo(int(self.prev_x), int(self.prev_y))
                            status_text = "Modo Cursor"

                    # ══════════════════════════════════════════════════════════
                    # SIN GESTO RECONOCIDO
                    # ══════════════════════════════════════════════════════════
                    else:
                        self.prev_palm_x = None
                        self.prev_palm_y = None
                        if self.mouse_pressed:
                            pyautogui.mouseUp(button='left')
                            self.mouse_pressed = False
                            print("[Gesture Engine] Gesture lost. Left click released.")
                        status_text = "Mano Detectada"

            else:
                # No hand detected — release mouse drag and reset scroll state
                self.prev_palm_x = None
                self.prev_palm_y = None
                if self.mouse_pressed:
                    pyautogui.mouseUp(button='left')
                    self.mouse_pressed = False
                    print("[Gesture Engine] Hand lost. Left click released.")

            # ── Build and emit QImage ─────────────────────────────────────────
            hud_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            q_img   = QImage(hud_rgb.data, w, h, w * c, QImage.Format.Format_RGB888).copy()
            self.frame_signal.emit(q_img, status_text)

            time.sleep(0.015)

        # ── Cleanup ───────────────────────────────────────────────────────────
        cap.release()
        detector.close()
        self.active_signal.emit(False)
        print("[Gesture Engine] Hand tracking thread stopped safely.")
