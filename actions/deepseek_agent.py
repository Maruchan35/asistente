"""deepseek_agent.py — DeepSeek API integration for complex reasoning."""
import os
import json
import requests
from pathlib import Path

def _get_api_key() -> str:
    """Retrieve DeepSeek API key from config."""
    try:
        if getattr(os, "frozen", False):
            base_dir = Path(os.sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parent.parent
        cfg_path = base_dir / "config" / "api_keys.json"
        
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            return cfg.get("deepseek_api_key", "").strip()
    except Exception:
        pass
    return ""

def deepseek_agent(query: str, system_prompt: str = None) -> str:
    """
    Call the official DeepSeek API for complex queries or reasoning.
    Does not require a browser window. Runs entirely in the background.
    """
    api_key = _get_api_key()
    if not api_key:
        return "Error: No se encontró la API Key de DeepSeek en config/api_keys.json."
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    if not system_prompt:
        system_prompt = (
            "Eres un agente analítico delegado por JARVIS. "
            "Tu objetivo es responder de manera exhaustiva, profunda y precisa. "
            "Usa español neutro. Estructura bien tu respuesta."
        )
    
    payload = {
        "model": "deepseek-reasoner",  # Utilizar el modelo de razonamiento profundo
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        "max_tokens": 4000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
        
        # Opcional: Podríamos retornar o loggear el reasoning, pero devolvemos la respuesta final
        if not reply and reasoning:
            return reasoning
            
        return reply.strip()
    except Exception as e:
        return f"Error de conexión con DeepSeek: {e}"
