"""
core/emotion_detector.py — Detecta tono emocional del usuario por keywords y prosodia textual.

No es ML — son heurísticas baratas que funcionan sorprendentemente bien:
  • Mayúsculas excesivas → enfadado/enfático
  • Múltiples signos de exclamación → emocionado o frustrado (según keywords)
  • Palabras key: "no funciona", "puta", "joder", "está mal" → frustrado
  • "gracias", "perfecto", "genial", "bien hecho" → contento
  • "estoy cansado", "agotado", "harto" → cansado
  • "urgente", "rápido", "ya" → apurado

Devuelve un EmotionalState que el system_instruction puede usar para adaptar tono.
"""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class EmotionalState:
    """Estado emocional detectado."""
    label:     str     # neutral | frustrado | contento | cansado | apurado | enfático
    intensity: float   # 0.0 - 1.0
    cues:      list[str]   # señales detectadas

    def to_prompt_hint(self) -> str:
        """Genera hint para inyectar al contexto del LLM."""
        if self.label == "neutral" or self.intensity < 0.3:
            return ""
        hints = {
            "frustrado": (
                "El usuario parece frustrado. Sé directo, breve, sin humor. "
                "Reconoce el problema, ejecuta la solución, evita preámbulos."
            ),
            "contento": (
                "El usuario está de buen humor. Puedes ser un poco más jocoso "
                "con tu sarcasmo habitual."
            ),
            "cansado": (
                "El usuario está cansado. Respuestas MUY breves. Sin sarcasmo. "
                "Ofrece hacer cosas por él en lugar de preguntar."
            ),
            "apurado": (
                "El usuario tiene prisa. Una sola frase de confirmación, sin humor. "
                "Ejecuta inmediatamente sin verificar dos veces."
            ),
            "enfático": (
                "El usuario está siendo enfático. Atiende exactamente lo que pidió, "
                "sin interpretaciones creativas ni ampliar el scope."
            ),
        }
        return f"[ESTADO DEL USUARIO: {self.label.upper()}] {hints.get(self.label, '')}"


# Vocabularios
_FRUSTRATED = [
    r"\bno funciona\b", r"\bno sirve\b", r"\bse rompi[oó]\b", r"\bcrash(?:e[oó])?\b",
    r"\bputa\b", r"\bmierda\b", r"\bjoder\b", r"\bcoño\b", r"\bcarajo\b", r"\bverga\b",
    r"\bestá mal\b", r"\bno entendiste\b", r"\bya te dije\b", r"\bharto\b",
    r"\bhart[oa] de\b", r"\bno aguanto\b", r"\botra vez (?:lo )?mismo\b",
    r"\bque chinga(?:dera|os)\b", r"\bestoy enojad[oa]\b",
]
_HAPPY = [
    r"\bperfecto\b", r"\bgenial\b", r"\bexcelente\b", r"\bbien hecho\b",
    r"\bmuy bien\b", r"\bgracias\b", r"\bte quiero\b", r"\beres (?:el|la) mejor\b",
    r"\bsalvaste\b", r"\bme encanta\b", r"\bbrutal\b", r"\bchévere\b", r"\bcrack\b",
    r"\bingenioso\b", r"\bjaj+a\b",
]
_TIRED = [
    r"\bcansado\b", r"\bagotado\b", r"\bsin energ[ií]a\b", r"\bmuerto\b",
    r"\bsue[ñn]o\b", r"\btengo sue[ñn]o\b", r"\bmadrugada\b",
    r"\bno tengo ganas\b", r"\baplastad[oa]\b",
]
_HURRIED = [
    r"\burgente\b", r"\br[áa]pido\b", r"\bya\b", r"\bahora mismo\b",
    r"\bdate prisa\b", r"\bapurat[ea]\b", r"\bestoy llegando tarde\b",
    r"\bme van a echar\b", r"\bya casi\b",
]


def _matches(patterns: list[str], text: str) -> list[str]:
    out = []
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            out.append(p)
    return out


def detect(user_text: str) -> EmotionalState:
    """Detecta estado emocional del texto del usuario."""
    if not user_text or len(user_text) < 3:
        return EmotionalState(label="neutral", intensity=0.0, cues=[])

    text = user_text.strip()

    # Señales de prosodia
    cues = []
    intensity_bonus = 0.0

    # 1. Mayúsculas excesivas (al menos 5 letras y >50% del texto en mayúscula)
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 5:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.5:
            cues.append("mayúsculas_excesivas")
            intensity_bonus += 0.3

    # 2. Múltiples signos de exclamación
    exclam_count = text.count("!")
    if exclam_count >= 2:
        cues.append(f"exclamaciones_{exclam_count}")
        intensity_bonus += min(0.3, exclam_count * 0.1)

    # 3. Múltiples signos de pregunta consecutivos
    if "??" in text or "¿¿" in text:
        cues.append("multiples_preguntas")
        intensity_bonus += 0.2

    # Conteo por categoría
    matched_frustrated = _matches(_FRUSTRATED, text)
    matched_happy      = _matches(_HAPPY, text)
    matched_tired      = _matches(_TIRED, text)
    matched_hurried    = _matches(_HURRIED, text)

    scores = {
        "frustrado": len(matched_frustrated) * 0.4,
        "contento":  len(matched_happy)      * 0.35,
        "cansado":   len(matched_tired)      * 0.5,
        "apurado":   len(matched_hurried)    * 0.4,
    }

    # Mayúsculas + exclamaciones sin keyword específico → enfático
    if intensity_bonus > 0.3 and max(scores.values()) == 0:
        return EmotionalState(
            label="enfático",
            intensity=min(1.0, intensity_bonus),
            cues=cues,
        )

    # Boost por prosodia (refuerza la etiqueta dominante si es frustración)
    if matched_frustrated:
        scores["frustrado"] += intensity_bonus

    label = max(scores, key=scores.get)
    intensity = scores[label]

    if intensity < 0.25:
        return EmotionalState(label="neutral", intensity=intensity, cues=cues)

    all_cues = cues + (
        matched_frustrated + matched_happy + matched_tired + matched_hurried
    )
    return EmotionalState(
        label=label, intensity=min(1.0, intensity), cues=all_cues[:6],
    )


# ── Cache simple del último estado (para que main.py inyecte hint sin recalcular) ──

_last_state: EmotionalState | None = None


def update_from_user_text(user_text: str) -> EmotionalState:
    """Detectar y cachear. Llamar tras cada turno del usuario."""
    global _last_state
    state = detect(user_text)
    _last_state = state
    return state


def get_last_state() -> EmotionalState | None:
    return _last_state


def current_prompt_hint() -> str:
    """Hint listo para inyectar al context. '' si no hay nada útil."""
    if _last_state is None:
        return ""
    return _last_state.to_prompt_hint()
