"""deepseek_agent.py — DeepSeek API integration for complex reasoning.
Uses urllib (no requests dependency) with streaming disabled for clean responses."""
from __future__ import annotations
import json, urllib.request, urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _get_api_key() -> str:
    try:
        from core.secure_config import read_config
        return read_config().get("deepseek_api_key", "").strip()
    except Exception:
        try:
            cfg_path = BASE_DIR / "config" / "api_keys.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                return cfg.get("deepseek_api_key", "").strip()
        except Exception:
            pass
    return ""

def deepseek_agent(query: str, system_prompt: str | None = None) -> str:
    """Call the official DeepSeek API for complex reasoning queries.
    Uses urllib instead of requests to avoid blocking the main thread."""
    api_key = _get_api_key()
    if not api_key:
        return "Error: No se encontró 'deepseek_api_key' en config/api_keys.json."

    if not system_prompt:
        system_prompt = (
            "Eres un agente analítico delegado por JARVIS. "
            "Responde de manera exhaustiva, profunda y precisa. "
            "Usa español neutro. Estructura bien tu respuesta."
        )

    payload = json.dumps({
        "model": "deepseek-reasoner",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": query},
        ],
        "max_tokens": 4000,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        # 90 s timeout — runs in a ThreadPoolExecutor so it doesn't block the event loop
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())

        choice    = data.get("choices", [{}])[0]
        message   = choice.get("message", {})
        reply     = message.get("content", "")
        reasoning = message.get("reasoning_content", "")

        # DeepSeek Reasoner may put the answer in reasoning_content
        if not reply and reasoning:
            return reasoning.strip()
        return (reply or reasoning or "Sin respuesta del modelo.").strip()

    except urllib.error.HTTPError as e:
        status = e.code
        body   = ""
        try:
            body = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            pass

        # Out of credits (402) or rate limit (429) → fallback to OpenRouter
        if status in (402, 429):
            try:
                from actions.openrouter_agent import openrouter_agent
                return openrouter_agent(query=query, model="deepseek/deepseek-r1-0528")
            except Exception as fb_err:
                return f"DeepSeek sin créditos y OpenRouter también falló: {fb_err}"

        return f"Error DeepSeek (HTTP {status}): {body or e.reason}"

    except urllib.error.URLError as e:
        return f"No se pudo conectar a DeepSeek: {e.reason}"

    except TimeoutError:
        return "DeepSeek tardó demasiado (90s). Intentá con una pregunta más corta."

    except Exception as e:
        return f"Error inesperado en DeepSeek: {e}"
