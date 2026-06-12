# -*- coding: utf-8 -*-
"""
tests/test_config_readers.py — Ningún módulo puede leer las API keys cifradas
sin pasar por core/secure_config.

La clase de bug que previene: al cifrar api_keys.json (valores enc::), todo
módulo que haga json.loads() directo recibe el blob cifrado en vez de la
clave real → las APIs lo rechazan → "Fallo de visión multiservicio" etc.

Regla: si un .py menciona api_keys.json Y usa alguno de los campos cifrados
(_ENCRYPTED_FIELDS de secure_config), DEBE importar secure_config/read_config.

Excepciones legítimas:
  - core/secure_config.py (es el cifrador)
  - install.py (solo ESCRIBE el template con placeholders)
  - main.py settings UI (escribe el config — leer lo hace via _get_api_key parchado)

Uso:  .venv/Scripts/python.exe tests/test_config_readers.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ENCRYPTED_FIELDS = (
    "gemini_api_key", "openrouter_api_key", "deepseek_api_key",
    "groq_api_key", "telegram_bot_token",
)

# Archivos que pueden tocar las claves sin descifrar (escriben, no consumen)
ALLOWED = {
    "core/secure_config.py",
    "install.py",
    "tests/test_config_readers.py",
}


def main() -> int:
    broken: list[str] = []
    scanned = 0

    for py in list(ROOT.glob("actions/*.py")) + list(ROOT.glob("core/*.py")) \
              + list(ROOT.glob("memory/*.py")) + [ROOT / "main.py"]:
        rel = str(py.relative_to(ROOT)).replace("\\", "/")
        if rel in ALLOWED:
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "api_keys.json" not in src:
            continue
        scanned += 1
        uses_enc_fields = any(f in src for f in ENCRYPTED_FIELDS)
        if not uses_enc_fields:
            continue   # lee otros campos (timezone, mic) — no necesita descifrar
        if "secure_config" in src or "read_config" in src:
            continue   # parchado ✓
        broken.append(rel)

    if broken:
        print(f"[FAIL] {len(broken)} mód