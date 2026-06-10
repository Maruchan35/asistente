"""wake_word.py — Wake word detection for JARVIS.
Listens in background for "JARVIS" (or custom phrase) using:
  1. Vosk (offline, free) — preferred
  2. SpeechRecognition + Google (online fallback)
Calls a callback when wake word is detected."""
from __future__ import annotations
import json, os, queue, threading, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Config ────────────────────────────────────────────────────────────────────
def _load_cfg() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

_WAKE_WORDS_DEFAULT = ["jarvis", "oye jarvis", "hey jarvis", "hola jarvis"]


def get_configured_wake_words() -> list[str]:
    """Lee wake words desde config/api_keys.json. Soporta string CSV o lista."""
    cfg = _load_cfg()
    custom = cfg.get("wake_words")
    if not custom:
        return list(_WAKE_WORDS_DEFAULT)
    if isinstance(custom, str):
        # CSV o palabra única
        words = [w.strip().lower() for w in custom.split(",") if w.strip()]
    elif isinstance(custom, list):
        words = [str(w).strip().lower() for w in custom if str(w).strip()]
    else:
        return list(_WAKE_WORDS_DEFAULT)
    # Siempre incluir "jarvis" como fallback (a menos que el usuario lo excluya explícitamente)
    if "jarvis" not in words and not cfg.get("wake_words_strict", False):
        words.append("jarvis")
    return words or list(_WAKE_WORDS_DEFAULT)

class WakeWordDetector:
    """Background wake word detector.

    Usage:
        detector = WakeWordDetector(on_wake=lambda: print("Wake!"))
        detector.start()
        # ... later ...
        detector.stop()
    """

    def __init__(self,
                 on_wake: callable,
                 wake_words: list[str] | None = None,
                 sensitivity: float = 0.5):
        self.on_wake     = on_wake
        self.wake_words  = [w.lower() for w in (wake_words or _WAKE_WORDS_DEFAULT)]
        self.sensitivity = sensitivity
        self._running    = False
        self._thread: threading.Thread | None = None
        self._mode: str  = "none"

    # ── Vosk (offline) ────────────────────────────────────────────────────────
    def _try_vosk(self) -> bool:
        """Return True if Vosk is available and model is downloaded."""
        try:
            import vosk
            model_paths = [
                BASE_DIR / "models" / "vosk-model-small-es-0.42",
                BASE_DIR / "models" / "vosk-model-es",
                BASE_DIR / "models" / "vosk-model-small-en-us-0.15",
                BASE_DIR / "models" / "vosk-model-en-us",
                Path.home() / "vosk-model-small-es-0.42",
            ]
            for mp in model_paths:
                if mp.exists():
                    self._vosk_model_path = str(mp)
                    return True
            return False
        except ImportError:
            return False

    def _run_vosk(self):
        """Wake word loop using Vosk offline recognition."""
        import vosk
        import sounddevice as sd

        model = vosk.Model(self._vosk_model_path)
        q     = queue.Queue()
        samplerate = 16000

        def callback(indata, frames, time_info, status):
            if status:
                pass  # Ignore audio status messages silently
            q.put(bytes(indata))

        rec = vosk.KaldiRecognizer(model, samplerate)
        rec.SetWords(False)

        with sd.RawInputStream(samplerate=samplerate, blocksize=4000,
                                dtype="int16", channels=1, callback=callback):
            while self._running:
                try:
                    data = q.get(timeout=1.0)
                except queue.Empty:
                    continue
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower().strip()
                    if text and any(w in text for w in self.wake_words):
                        try:
                            self.on_wake()
                        except Exception as e:
                            print(f"[WakeWord] Error en callback: {e}")
                else:
                    partial = json.loads(rec.PartialResult())
                    text = partial.get("partial", "").lower()
                    if text and any(w in text for w in self.wake_words):
                        rec.Reset()
                        try:
                            self.on_wake()
                        except Exception as e:
                            print(f"[WakeWord] Error en callback: {e}")

    # ── SpeechRecognition fallback ─────────────────────────────────────────
    def _run_speech_recognition(self):
        """Wake word loop using SpeechRecognition (online, slower)."""
        try:
            import speech_recognition as sr
        except ImportError:
            print("[WakeWord] SpeechRecognition no instalado: pip install SpeechRecognition")
            return

        r   = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True

        with sr.Microphone(sample_rate=16000) as source:
            r.adjust_for_ambient_noise(source, duration=1)
            print("[WakeWord] SpeechRecognition activo — escuchando wake word…")

            while self._running:
                try:
                    audio = r.listen(source, timeout=5, phrase_time_limit=4)
                    try:
                        # Try offline Sphinx first
                        text = r.recognize_sphinx(audio).lower()
                    except Exception:
                        try:
                            text = r.recognize_google(audio, language="es-MX").lower()
                        except sr.UnknownValueError:
                            continue
                        except sr.RequestError as e:
                            print(f"[WakeWord] Google SR error: {e}")
                            time.sleep(2)
                            continue

                    if any(w in text for w in self.wake_words):
                        print(f"[WakeWord] Wake word detectada: '{text}'")
                        try:
                            self.on_wake()
                        except Exception as e:
                            print(f"[WakeWord] Error en callback: {e}")
                        time.sleep(1.5)  # debounce

                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    print(f"[WakeWord] Error de audio: {e}")
                    time.sleep(1)

    # ── Porcupine (Picovoice) ─────────────────────────────────────────────
    def _try_porcupine(self) -> bool:
        try:
            import pvporcupine
            return True
        except ImportError:
            return False

    def _run_porcupine(self):
        """Wake word using Porcupine ('jarvis' keyword available for free)."""
        import pvporcupine
        import struct

        cfg = _load_cfg()
        pv_key = cfg.get("picovoice_api_key", "").strip()

        try:
            porcupine = pvporcupine.create(
                access_key=pv_key,
                keywords=["jarvis"],
            )
        except Exception as e:
            print(f"[WakeWord] Porcupine init error: {e}")
            return

        try:
            import sounddevice as sd
            frame_len = porcupine.frame_length
            q = queue.Queue()

            def cb(indata, frames, t, status):
                q.put(bytes(indata))

            with sd.RawInputStream(samplerate=porcupine.sample_rate,
                                    blocksize=frame_len,
                                    dtype="int16", channels=1, callback=cb):
                print("[WakeWord] Porcupine activo — escuchando 'Jarvis'…")
                while self._running:
                    try:
                        pcm = q.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    pcm_unpacked = struct.unpack_from(f"{frame_len}h", pcm)
                    keyword_idx = porcupine.process(pcm_unpacked)
                    if keyword_idx >= 0:
                        print("[WakeWord] 'Jarvis' detectado via Porcupine")
                        try:
                            self.on_wake()
                        except Exception as e:
                            print(f"[WakeWord] Error en callback: {e}")
                        time.sleep(1.0)
        finally:
            porcupine.delete()

    # ── Public API ─────────────────────────────────────────────────────────
    def start(self) -> str:
        """Start the detector in a background thread. Returns selected mode."""
        if self._running:
            return self._mode

        self._running = True

        if self._try_porcupine():
            self._mode  = "porcupine"
            target = self._run_porcupine
        elif self._try_vosk():
            self._mode  = "vosk"
            target = self._run_vosk
        else:
            self._mode  = "speech_recognition"
            target = self._run_speech_recognition

        self._thread = threading.Thread(target=target, daemon=True, name="WakeWordDetector")
        self._thread.start()
        print(f"[WakeWord] Detector iniciado — modo: {self._mode}")
        print(f"[WakeWord] Wake words: {', '.join(self.wake_words)}")
        return self._mode

    def stop(self):
        """Stop the detector."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        print("[WakeWord] Detector detenido.")

    @property
    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def install_vosk():
        """Print instructions to install Vosk model."""
        return (
            "Para wake word offline con Vosk:\n"
            "1. pip install vosk sounddevice\n"
            "2. Descargar modelo: https://alphacephei.com/vosk/models\n"
            "   Recomendado: vosk-model-small-es-0.42 (español, 39 MB)\n"
            "3. Extraer en: jarvis/models/vosk-model-small-es-0.42/\n\n"
            "Para wake word con Porcupine (más preciso):\n"
            "1. pip install pvporcupine sounddevice\n"
            "2. Registrarse en https://picovoice.ai (plan gratuito disponible)\n"
            "3. Agregar 'picovoice_api_key' en config/api_keys.json"
        )


# ── Singleton global ──────────────────────────────────────────────────────────
_detector: WakeWordDetector | None = None

def get_detector() -> WakeWordDetector | None:
    return _detector

def start_wake_word(on_wake: callable,
                    wake_words: list[str] | None = None) -> str:
    """Start the global wake word detector. Returns mode string."""
    global _detector
    if _detector and _detector.is_running:
        _detector.stop()
    # Si no se pasaron palabras explícitas, usar las del config (o defaults)
    if wake_words is None:
        wake_words = get_configured_wake_words()
    _detector = WakeWordDetector(on_wake=on_wake, wake_words=wake_words)
    return _detector.start()

def stop_wake_word():
    global _detector
    if _detector:
        _detector.stop()
        _detector = None
