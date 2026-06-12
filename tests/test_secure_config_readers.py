# -*- coding: utf-8 -*-
"""
tests/test_secure_config_readers.py — Previene el bug del cifrado que rompió la visión.

Cuando secure_config cifró las API keys, varios módulos seguían leyendo
api_keys.json crudo y recibían 'enc::...' en vez de la clave → fallo de visión,
WhatsApp, etc.

Este test escanea TODOS los .py del proyecto y exige: si un módulo lee
api_keys.json Y usa alguna de las claves cifradas, DEBE pasar por
secure_config.read_config() (o tener un fallback que lo haga).

Uso: .venv/Scripts/python.exe tests/test_secure_config_readers.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Claves que secure_config cifra (deben leerse descifradas)
ENCRYPTED_KEYS = (
    "gemini_api_key", "openrouter_api_key", "deepseek_api_key",
    "groq_api_key", "telegram_bot_token",
)

# Módulos exentos: el propio secure_config y scripts de instalación/test
EXEMPT = {
    "core/secure_config.py",
    "install.py",                     # escribe el config, no consume las keys en runtime
    "tests/test_secure_config_readers.py",
}


def main() -> int:
    offenders = []
    for py in ROOT.rglob("*.py"):
        rel = str(py.relative_to(ROOT)).replace("\\", "/")
        if rel in EXEMPT or "/.venv/" in f"/{rel}" or rel.startswith(".venv"):
            continue
        if "__pycache__" in rel or rel.startswith("backups/"):
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        reads_json = "api_keys.json" in src
        uses_key   = any(k in src for k in ENCRYPTED_KEYS)
        if reads_json and uses_key:
            # Debe referenciar secure_config / read_config
            if "secure_config" not in src and "read_config" not in src:
                offenders.append(rel)

    if offenders:
        print(f"[FAIL] {len(offenders)} módulo(s) leen api_keys.json y usan claves "
              "cifradas SIN pasar por secure_config.read_config():")
        for o in sorted(offenders):
            print(f"         - {o}")
        print("       → recibirán 'enc::...' en vez de la clave real y fallarán.")
        return 1

    print("[PASS] Todos los lectores de claves cifradas usan secure_config — "
          "no hay riesgo de recibir valores 'enc::' sin descifrar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
