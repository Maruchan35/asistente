"""
core/sandbox.py — Validación de comandos/operaciones peligrosas.

Capa de seguridad que envuelve operaciones destructivas (terminal_agent,
file moves, file deletes) y devuelve una "intención clasificada" con nivel
de riesgo y lista exacta de archivos/comandos afectados, para que la UI
muestre un diálogo de confirmación antes de ejecutar.

LECCIÓN APRENDIDA: una orden de "organizar archivos" puede vaciar el
Escritorio entero. NUNCA ejecutar destructivo sin enumerar exactamente qué.

Uso:
    from core.sandbox import classify_command, classify_paths
    report = classify_command("rm -rf C:/Users/marux/Desktop/*")
    # → SandboxReport(risk='CRITICAL', reason='Destructive recursive deletion of Desktop')

    if report.risk in ("HIGH", "CRITICAL"):
        # mostrar confirm dialog en UI con report.affected
        ...
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Carpetas críticas del usuario que requieren confirmación obligatoria
_HOME = Path(os.path.expanduser("~"))
_PROTECTED_FOLDERS = {
    str(_HOME / sub).lower() for sub in
    ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive"]
}
_PROTECTED_FOLDERS.add(str(_HOME).lower())

# Patrones de comandos altamente peligrosos (regex sobre línea completa)
_CRITICAL_CMDS = [
    (r"\brm\s+(-[rRf]+\s+)+.*\*", "Borrado recursivo con wildcard"),
    (r"\brm\s+-rf\s+/", "Borrado recursivo desde raíz"),
    (r"\bdel\s+/[sqf]+\s+", "Borrado masivo en Windows con flags"),
    (r"\bRemove-Item\s+.*-Recurse.*-Force", "Borrado recursivo forzado"),
    (r"\bformat\s+[a-zA-Z]:", "Formateo de partición"),
    (r"\bdiskpart\b", "Manipulación de discos"),
    (r"\bsudo\s+rm\b", "Borrado con privilegios"),
    (r":(){:|:&};:", "Fork bomb"),
    (r"shutdown\s+/[fr]", "Apagado forzado"),
    (r"\b(?:reg|reg.exe)\s+delete\s+HKEY", "Borrado de registro"),
]

_HIGH_CMDS = [
    (r"\bmv\s+.*~?/Desktop", "Mover Escritorio"),
    (r"\bMove-Item\s+.*Desktop", "Mover Escritorio (PowerShell)"),
    (r"\bcurl\s+.*\|\s*(?:bash|sh|powershell)", "Ejecución remota sin verificar"),
    (r"\bInvoke-Expression\s+.*Invoke-WebRequest", "Ejecución remota PowerShell"),
    (r"\btaskkill\s+/[fF]\s+/IM\s+(?:explorer|winlogon|csrss|smss|lsass)", "Matar proceso crítico"),
    (r"\bnetsh\s+wlan\s+", "Manipulación de WiFi"),
    (r"\bchmod\s+777\b", "Permisos abiertos"),
    (r"\bdrop\s+(?:database|table)", "Borrado de base de datos"),
]

_MEDIUM_CMDS = [
    (r"\bpip\s+install\b",      "Instalación de paquete Python"),
    (r"\bnpm\s+install\b",      "Instalación de paquete Node"),
    (r"\bwinget\s+install\b",   "Instalación de software"),
    (r"\bgit\s+(?:reset|clean)\s+", "Operación git destructiva"),
    (r"\bgit\s+push\s+--force",     "Force push a git"),
]


@dataclass
class SandboxReport:
    risk:      str           # SAFE / MEDIUM / HIGH / CRITICAL
    reason:    str = ""
    matched:   str = ""      # patrón que se detonó
    affected:  list[str] = field(default_factory=list)  # archivos/recursos afectados
    suggestion: str = ""     # texto sugerido para mostrar al usuario

    def needs_confirmation(self) -> bool:
        return self.risk in ("HIGH", "CRITICAL")

    def to_dict(self) -> dict:
        return {
            "risk":     self.risk,
            "reason":   self.reason,
            "matched":  self.matched,
            "affected": self.affected,
            "suggestion": self.suggestion,
        }


def classify_command(cmd: str) -> SandboxReport:
    """Clasificar un comando shell por nivel de riesgo."""
    if not cmd:
        return SandboxReport(risk="SAFE")
    text = cmd.strip()

    for pat, reason in _CRITICAL_CMDS:
        if re.search(pat, text, re.IGNORECASE):
            return SandboxReport(
                risk="CRITICAL", reason=reason, matched=pat,
                suggestion=f"Confirme señor: '{reason}' — comando: {text[:100]}",
            )
    for pat, reason in _HIGH_CMDS:
        if re.search(pat, text, re.IGNORECASE):
            return SandboxReport(
                risk="HIGH", reason=reason, matched=pat,
                suggestion=f"Operación de alto riesgo: {reason}. ¿Procedo, señor?",
            )
    for pat, reason in _MEDIUM_CMDS:
        if re.search(pat, text, re.IGNORECASE):
            return SandboxReport(
                risk="MEDIUM", reason=reason, matched=pat,
                suggestion=f"Acción que modifica el sistema: {reason}.",
            )
    return SandboxReport(risk="SAFE")


def classify_paths(operation: str, paths: list[str]) -> SandboxReport:
    """
    Clasificar una operación de archivos. `operation` ∈ {"delete","move","overwrite"}.
    Devuelve riesgo según si los paths tocan carpetas protegidas.
    """
    op = operation.lower()
    expanded = []
    protected_hits = []
    for p in paths:
        try:
            full = str(Path(os.path.expanduser(p)).resolve()).lower()
        except Exception:
            full = p.lower()
        expanded.append(full)
        # ¿toca alguna carpeta protegida?
        for prot in _PROTECTED_FOLDERS:
            if full == prot or full.startswith(prot + os.sep) or full.startswith(prot + "/"):
                protected_hits.append(full)
                break

    if not paths:
        return SandboxReport(risk="SAFE")

    risk = "SAFE"
    reason = ""

    if op == "delete":
        risk = "HIGH" if protected_hits else "MEDIUM"
        reason = f"Eliminar {len(paths)} archivo(s)"
        if protected_hits:
            risk = "CRITICAL"
            reason = f"Eliminar archivos en carpeta protegida ({len(protected_hits)})"
    elif op == "move":
        risk = "HIGH" if protected_hits else "MEDIUM"
        reason = f"Mover {len(paths)} archivo(s)"
    elif op == "overwrite":
        risk = "MEDIUM"
        reason = f"Sobrescribir {len(paths)} archivo(s)"
        if protected_hits:
            risk = "HIGH"

    return SandboxReport(
        risk=risk,
        reason=reason,
        affected=expanded[:20],
        suggestion=f"{reason}. ¿Confirma señor?" if risk in ("HIGH","CRITICAL") else reason,
    )


# Lista de archivos que JARVIS no debe tocar bajo ninguna circunstancia
_UNTOUCHABLE_FILES = {
    "actions/terminal_agent.py",
    "actions/self_edit.py",
    "core/sandbox.py",
}


def is_untouchable(file_path: str) -> bool:
    """Verifica si un archivo está en la lista de intocables."""
    p = file_path.replace("\\", "/").lower()
    for u in _UNTOUCHABLE_FILES:
        if p.endswith(u.lower()):
            return True
    return False
