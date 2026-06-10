"""
core/proactive_engine.py — Motor de sugerencias proactivas.

Analiza los hábitos del usuario (`user_profile.habits` + `memory/sessions/*.jsonl`)
para detectar patrones de uso por hora/día de la semana, y dispara sugerencias
cuando el contexto actual coincide con un patrón conocido.

Ejemplo: si en 5+ lunes a las 9am abriste el calendario y Spotify, hoy lunes 9am
sugerirá "señor, ¿abro su rutina habitual del lunes?".

Sin LLM — todo se basa en estadísticas locales. Cero costo, cero latencia.

Uso:
    from core.proactive_engine import (
        ProactiveEngine, get_suggestion_for_now,
    )
    suggestion = get_suggestion_for_now()
    if suggestion:
        speak(suggestion.message)
"""
from __future__ import annotations
import json
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_SESSIONS = _BASE / "memory" / "sessions"
_PROFILE  = _BASE / "config" / "user_profile.json"

# Mínimo de ocurrencias para considerar un patrón válido
_MIN_OCCURRENCES = 3

# Ventana horaria (en horas) — agrupa horas similares
_HOUR_BUCKET = 1     # 1h: detecta patrones por hora exacta

# Si la última sugerencia fue hace < N segundos, no repetir
_COOLDOWN_S = 1800   # 30 min entre sugerencias proactivas


@dataclass
class Pattern:
    """Patrón detectado de uso."""
    weekday:   int                   # 0=lunes ... 6=domingo
    hour:      int                   # 0-23
    tool:      str                   # nombre de herramienta
    count:     int = 0               # ocurrencias
    last_seen: float = 0.0           # ts última vez

    def matches_now(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        return (now.weekday() == self.weekday
                and abs(now.hour - self.hour) <= _HOUR_BUCKET)


@dataclass
class Suggestion:
    message:  str
    tools:    list[str] = field(default_factory=list)
    weekday:  int = -1
    hour:     int = -1
    score:    int = 0     # confianza (= count del patrón)


class ProactiveEngine:
    """Motor que analiza historial y produce sugerencias."""

    def __init__(self):
        self._patterns: list[Pattern] = []
        self._last_suggested_ts: float = 0.0
        self._last_pattern_key: str = ""
        self._lock = threading.Lock()
        self._rebuild()

    # ── Análisis ─────────────────────────────────────────────────────────────
    def _rebuild(self) -> None:
        """Re-escanear el historial y construir patrones."""
        counter: Counter[tuple[int, int, str]] = Counter()   # (wd, hr, tool) → count
        last_seen: dict[tuple[int, int, str], float] = {}

        try:
            for f in sorted(_SESSIONS.glob("*.jsonl")):
                try:
                    iso = f.stem
                    d = date.fromisoformat(iso)
                    wd = d.weekday()
                except Exception:
                    continue
                try:
                    with open(f, encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line: continue
                            try:
                                entry = json.loads(line)
                            except Exception:
                                continue
                            ts = entry.get("ts", 0)
                            if not ts: continue
                            hr = datetime.fromtimestamp(ts).hour
                            for tool in (entry.get("tools") or []):
                                k = (wd, hr, tool)
                                counter[k] += 1
                                last_seen[k] = max(last_seen.get(k, 0), ts)
                except Exception:
                    continue
        except Exception:
            pass

        patterns = []
        for (wd, hr, tool), cnt in counter.items():
            if cnt >= _MIN_OCCURRENCES:
                patterns.append(Pattern(
                    weekday=wd, hour=hr, tool=tool,
                    count=cnt, last_seen=last_seen.get((wd, hr, tool), 0),
                ))
        patterns.sort(key=lambda p: -p.count)

        with self._lock:
            self._patterns = patterns

    def get_suggestion_for_now(self, now: datetime | None = None) -> Suggestion | None:
        """Devuelve la mejor sugerencia para el contexto actual, o None."""
        now = now or datetime.now()
        now_ts = now.timestamp()

        # Cooldown global
        with self._lock:
            if (now_ts - self._last_suggested_ts) < _COOLDOWN_S:
                return None

        # Cargar perfil con habits (frecuencia general)
        try:
            profile = json.loads(_PROFILE.read_text(encoding="utf-8"))
            habits = profile.get("habits", {})
        except Exception:
            habits = {}

        # Buscar patrones que matchean hoy/ahora
        matched = []
        with self._lock:
            for p in self._patterns:
                if p.matches_now(now):
                    matched.append(p)

        if not matched:
            return None

        # Agrupar por (wd,hr) para no repetir herramienta-por-herramienta
        wd_hr_key = f"{now.weekday()}-{now.hour}"
        with self._lock:
            if self._last_pattern_key == wd_hr_key:
                return None  # ya sugerimos algo para esta franja

        # Construir mensaje
        tools = [p.tool for p in matched]
        unique_tools = list(dict.fromkeys(tools))   # preservar orden, sin duplicados
        unique_tools = unique_tools[:4]

        weekday_es = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        day_str = weekday_es[now.weekday()]
        hour_str = f"{now.hour:02d}:00"

        tools_str = ", ".join(unique_tools)
        msg = (
            f"Señor, observo que los {day_str} a esta hora suele usar: {tools_str}. "
            f"¿Procedo con su rutina habitual?"
        )

        score = sum(p.count for p in matched)
        with self._lock:
            self._last_suggested_ts = now_ts
            self._last_pattern_key = wd_hr_key

        return Suggestion(
            message=msg, tools=unique_tools,
            weekday=now.weekday(), hour=now.hour, score=score,
        )

    def list_patterns(self, top_n: int = 20) -> list[Pattern]:
        with self._lock:
            return list(self._patterns[:top_n])

    def refresh(self) -> None:
        """Forzar reanálisis."""
        self._rebuild()


# ── Singleton + API conveniente ───────────────────────────────────────────────
_engine: ProactiveEngine | None = None
_engine_lock = threading.Lock()


def _get_engine() -> ProactiveEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ProactiveEngine()
        return _engine


def get_suggestion_for_now() -> Suggestion | None:
    """Conveniente: ¿hay algo que sugerir ahora mismo?"""
    return _get_engine().get_suggestion_for_now()


def list_patterns(top_n: int = 20) -> list[dict]:
    """Lista patrones detectados para diagnóstico."""
    weekday_es = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    return [
        {
            "day":   weekday_es[p.weekday],
            "hour":  f"{p.hour:02d}:00",
            "tool":  p.tool,
            "count": p.count,
        }
        for p in _get_engine().list_patterns(top_n=top_n)
    ]


def refresh() -> None:
    """Re-escanear historial."""
    _get_engine().refresh()


# ── Loop opcional para disparar sugerencias automáticamente ──────────────────

_runner_thread: threading.Thread | None = None
_runner_stop = threading.Event()


def start_loop(on_suggestion, interval_s: int = 600) -> None:
    """
    Loop en background que cada `interval_s` segundos pregunta si hay sugerencia.
    `on_suggestion(suggestion)` se llama con el objeto Suggestion cuando hay match.
    """
    global _runner_thread
    if _runner_thread and _runner_thread.is_alive():
        return

    _runner_stop.clear()

    def _loop():
        while not _runner_stop.is_set():
            try:
                # Respetar focus mode
                try:
                    from core.focus_mode import is_active as _focus_active
                    if _focus_active():
                        _runner_stop.wait(interval_s)
                        continue
                except Exception:
                    pass

                s = get_suggestion_for_now()
                if s and s.score >= _MIN_OCCURRENCES:
                    try:
                        on_suggestion(s)
                    except Exception:
                        pass
            except Exception:
                pass
            _runner_stop.wait(interval_s)

    _runner_thread = threading.Thread(target=_loop, daemon=True, name="ProactiveEngine")
    _runner_thread.start()


def stop_loop() -> None:
    _runner_stop.set()
