"""
core/secure_config.py — Cifrado transparente de las API keys.

config/api_keys.json está en texto plano: cualquiera con acceso al PC ve
todas las claves. Este módulo cifra los VALORES sensibles (las que contienen
"key", "token", "secret") con Fernet, usando una clave derivada de la máquina
(hostname + usuario + MAC) — así el archivo cifrado no sirve en otro equipo.

Diseño NO invasivo:
  • read_config() devuelve el config con los valores descifrados — el resto
    del código sigue leyendo api_keys.json como siempre vía esta función
  • encrypt_file() cifra in-place los valores sensibles (los demás campos
    como timezone, mic_device quedan legibles)
  • Compatibilidad: si un valor no está cifrado (texto plano), se devuelve tal cual
  • Si cryptography no está instalado, todo funciona sin cifrado (degradado)

Los valores cifrados se marcan con prefijo "enc::" para distinguirlos.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import uuid
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_CFG  = _BASE / "config" / "api_keys.json"

_ENC_PREFIX = "enc::"

# Allowlist EXACTO de claves que se cifran. Solo estas porque sus lectores
# están parcheados para descifrar (read_config). Otras keys (spotify oauth,
# etc.) quedan en texto plano para no romper módulos no parcheados.
_ENCRYPTED_FIELDS = {
    "gemini_api_key", "openrouter_api_key", "deepseek_api_key",
    "groq_api_key", "telegram_bot_token",
}
# Para status/detección genérica
_SENSITIVE_HINTS = ("key", "token", "secret", "password", "credential")


_KEYFILE = _BASE / "config" / ".jarvis_key"


def _machine_key() -> bytes:
    """Clave Fernet ESTABLE almacenada en un keyfile local (gitignored).

    ANTES usaba uuid.getnode() (el MAC), que es INESTABLE: devuelve un MAC
    distinto en cada arranque si hay varias interfaces de red (WiFi, VPN,
    adaptadores virtuales). Eso causó dos caídas — la clave se cifraba con un
    MAC y al reiniciar no descifraba porque getnode() devolvía otro → "API key
    not valid". Ahora la clave de cifrado se genera UNA vez y se guarda en
    config/.jarvis_key, estable entre reinicios y fuera de git."""
    try:
        if _KEYFILE.exists():
            data = _KEYFILE.read_bytes().strip()
            if len(data) >= 44:   # una clave Fernet válida tiene 44 bytes b64
                return data
        # Generar una nueva clave estable y persistirla
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key()
        _KEYFILE.parent.mkdir(parents=True, exist_ok=True)
        _KEYFILE.write_bytes(new_key)
        return new_key
    except Exception:
        # Último recurso: clave derivada SOLO de usuario+hostname (sin MAC).
        # Estable aunque menos única; mejor que romper.
        seed = f"{os.environ.get('COMPUTERNAME','')}|{os.environ.get('USERNAME','')}|jarvis-stable-v2"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def _is_sensitive(field: str) -> bool:
    f = field.lower()
    return any(h in f for h in _SENSITIVE_HINTS)


def _fernet():
    try:
        from cryptography.fernet import Fernet
        return Fernet(_machine_key())
    except Exception:
        return None


def encrypt_value(plain: str) -> str:
    f = _fernet()
    if f is None or not plain or plain.startswith(_ENC_PREFIX):
        return plain
    try:
        token = f.encrypt(plain.encode("utf-8")).decode("ascii")
        return _ENC_PREFIX + token
    except Exception:
        return plain


def decrypt_value(value: str) -> str:
    if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value
    f = _fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        # Clave de otra máquina o corrupto — devolver el cifrado (no romper)
        return value


def read_config() -> dict:
    """Cargar api_keys.json con los valores sensibles DESCIFRADOS."""
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for k, v in data.items():
        if isinstance(v, str) and v.startswith(_ENC_PREFIX):
            out[k] = decrypt_value(v)
        else:
            out[k] = v
    return out


def encrypt_file() -> dict:
    """Cifrar in-place los valores sensibles de api_keys.json.
    Idempotente: los ya cifrados se omiten. Devuelve resumen."""
    if _fernet() is None:
        return {"ok": False, "reason": "cryptography no instalado — sin cifrado."}
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "reason": f"no se pudo leer api_keys.json: {e}"}

    encrypted = 0
    for k, v in list(data.items()):
        if (k in _ENCRYPTED_FIELDS and isinstance(v, str) and v.strip()
                and not v.startswith(_ENC_PREFIX)
                and not v.upper().startswith("YOUR_")):   # no cifrar placeholders
            data[k] = encrypt_value(v)
            encrypted += 1

    if encrypted:
        # Backup antes de sobrescribir
        try:
            bak = _CFG.with_suffix(".json.plain.bak")
            if not bak.exists():
                bak.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        try:
            from core.safe_json import safe_write
            safe_write(_CFG, data)
        except Exception:
            _CFG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"ok": True, "encrypted": encrypted}


def status() -> dict:
    """¿Cuántos valores sensibles están cifrados vs en texto plano?"""
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {"encrypted": 0, "plaintext": 0}
    enc = pt = 0
    for k, v in data.items():
        if k in _ENCRYPTED_FIELDS and isinstance(v, str) and v.strip() and not v.upper().startswith("YOUR_"):
            if v.startswith(_ENC_PREFIX):
                enc += 1
            else:
                pt += 1
    return {"encrypted": enc, "plaintext": pt, "crypto_available": _fernet() is not None}
