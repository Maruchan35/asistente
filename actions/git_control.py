"""git_control.py — Real git command executor for JARVIS.
All operations run via subprocess in the configured repo directory."""
from __future__ import annotations
import json, os, re, subprocess
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent
CONF_FILE = BASE_DIR / "config" / "git_config.json"

# ── Config helpers ────────────────────────────────────────────────────────────
def _load_conf() -> dict:
    try:
        return json.loads(CONF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_conf(cfg: dict) -> None:
    CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONF_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def _resolve_dir(parameters: dict) -> str | None:
    """Return the working directory for git: param > config > cwd."""
    d = (parameters.get("path") or parameters.get("directory") or "").strip()
    if d and os.path.isdir(d):
        return d
    cfg = _load_conf()
    default = cfg.get("default_repo", "").strip()
    if default and os.path.isdir(default):
        return default
    return None

# ── Git runner ────────────────────────────────────────────────────────────────
def _git(args: list[str], cwd: str | None = None,
         timeout: int = 60, env: dict | None = None) -> tuple[bool, str]:
    """Run git with given args. Returns (success, output)."""
    git_exe = "git"
    try:
        r = subprocess.run(
            [git_exe] + args,
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env=env or os.environ.copy(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except FileNotFoundError:
        return False, "Git no está instalado o no está en el PATH. Instalá git desde https://git-scm.com"
    except subprocess.TimeoutExpired:
        return False, f"Timeout después de {timeout}s."
    except Exception as e:
        return False, f"Error ejecutando git: {e}"

def _sanitize_branch(name: str) -> str:
    """Remove characters invalid in branch names."""
    return re.sub(r"[^\w\-./]", "", name)[:80]

def _sanitize_message(msg: str) -> str:
    """Escape double quotes for commit messages."""
    return msg.replace('"', '\\"')[:500]

# ══════════════════════════════════════════════════════════════════════════════
def git_control(parameters: dict, player=None) -> str:
    action  = parameters.get("action", "status").lower().strip()
    cwd     = _resolve_dir(parameters)

    def log(msg: str):
        if player:
            player.write_log(f"🌿 git: {msg}")

    def no_repo():
        return ("No hay repositorio git configurado. "
                "Usá action=set_repo con path='/ruta/a/tu/proyecto' para configurarlo, "
                "o action=init para inicializar uno nuevo aquí.")

    # ── SET REPO ──────────────────────────────────────────────────────────────
    if action == "set_repo":
        path = (parameters.get("path") or parameters.get("directory") or "").strip()
        if not path:
            return "Especificá path con la ruta del repositorio."
        if not os.path.isdir(path):
            return f"La ruta '{path}' no existe."
        cfg = _load_conf()
        cfg["default_repo"] = path
        _save_conf(cfg)
        log(f"Repo configurado: {path}")
        return f"Repositorio git configurado: {path}"

    # ── INIT ─────────────────────────────────────────────────────────────────
    if action == "init":
        path = (parameters.get("path") or cwd or os.getcwd()).strip()
        ok, out = _git(["init"], cwd=path)
        if ok:
            cfg = _load_conf()
            cfg["default_repo"] = path
            _save_conf(cfg)
        msg = f"Repositorio inicializado en {path}." if ok else f"Error: {out}"
        log(msg); return msg

    if not cwd:
        return no_repo()

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "estado"):
        ok, out = _git(["status", "--short", "--branch"], cwd=cwd)
        if not ok:
            log(f"Error: {out[:200]}")
            return f"Error obteniendo estado: {out[:300]}"
        if not out.strip():
            out = "Repositorio limpio, sin cambios pendientes."
        log("status OK")
        return f"Estado del repositorio:\n{out}"

    # ── LOG ───────────────────────────────────────────────────────────────────
    elif action in ("log", "historial"):
        count = int(parameters.get("count", 10))
        ok, out = _git(
            ["log", f"--max-count={count}",
             "--pretty=format:%h  %an  %ar  %s"],
            cwd=cwd
        )
        if not ok:
            return f"Error: {out[:300]}"
        log(f"Últimos {count} commits mostrados")
        return f"Historial de commits:\n{out}" if out else "No hay commits todavía."

    # ── ADD ───────────────────────────────────────────────────────────────────
    elif action in ("add", "stage"):
        files = parameters.get("files", ".").strip()
        # Sanitize: no shell metacharacters
        if any(c in files for c in ["&", "|", ";", "`", "$", ">"]):
            return "Caracteres inválidos en el nombre de archivo."
        ok, out = _git(["add", files], cwd=cwd)
        msg = f"Archivos en staging: {files}." if ok else f"Error: {out[:300]}"
        log(msg); return msg

    # ── COMMIT ────────────────────────────────────────────────────────────────
    elif action in ("commit", "confirmar"):
        message = parameters.get("message", parameters.get("msg", "")).strip()
        if not message:
            return "Especificá un message para el commit."
        message = _sanitize_message(message)
        add_all = parameters.get("add_all", False)
        if add_all:
            _git(["add", "-A"], cwd=cwd)
        ok, out = _git(["commit", "-m", message], cwd=cwd)
        msg = f"Commit creado: '{message}'." if ok else f"Error: {out[:300]}"
        log(msg); return msg

    # ── PUSH ─────────────────────────────────────────────────────────────────
    elif action in ("push", "subir"):
        remote  = parameters.get("remote", "origin")
        branch  = _sanitize_branch(parameters.get("branch", ""))
        args    = ["push", remote]
        if branch:
            args += [branch]
        ok, out = _git(args, cwd=cwd, timeout=120)
        msg = f"Push a {remote}{' ' + branch if branch else ''} exitoso." if ok else f"Error push: {out[:400]}"
        log(msg); return msg

    # ── PULL ─────────────────────────────────────────────────────────────────
    elif action in ("pull", "bajar", "actualizar"):
        remote = parameters.get("remote", "origin")
        branch = _sanitize_branch(parameters.get("branch", ""))
        args   = ["pull", remote]
        if branch:
            args += [branch]
        ok, out = _git(args, cwd=cwd, timeout=120)
        msg = f"Pull completado." if ok else f"Error pull: {out[:400]}"
        log(msg); return msg

    # ── BRANCH ────────────────────────────────────────────────────────────────
    elif action in ("branch", "rama"):
        sub = parameters.get("subaction", "list").lower()
        name = _sanitize_branch(parameters.get("name", ""))
        if sub == "list":
            ok, out = _git(["branch", "-a"], cwd=cwd)
            return f"Ramas:\n{out}" if ok else f"Error: {out}"
        elif sub in ("create", "nueva"):
            if not name: return "Especificá name para la nueva rama."
            ok, out = _git(["checkout", "-b", name], cwd=cwd)
            return f"Rama '{name}' creada y activa." if ok else f"Error: {out}"
        elif sub in ("switch", "cambiar"):
            if not name: return "Especificá name para cambiar de rama."
            ok, out = _git(["checkout", name], cwd=cwd)
            return f"Cambiado a rama '{name}'." if ok else f"Error: {out}"
        elif sub in ("delete", "borrar"):
            if not name: return "Especificá name para borrar la rama."
            ok, out = _git(["branch", "-d", name], cwd=cwd)
            return f"Rama '{name}' eliminada." if ok else f"Error: {out}"
        return "Subacción de branch no reconocida. Usa: list | create | switch | delete"

    # ── CHECKOUT ─────────────────────────────────────────────────────────────
    elif action == "checkout":
        target = _sanitize_branch(parameters.get("target", parameters.get("branch", "main")))
        ok, out = _git(["checkout", target], cwd=cwd)
        return f"Checkout a '{target}'." if ok else f"Error: {out}"

    # ── MERGE ────────────────────────────────────────────────────────────────
    elif action == "merge":
        branch = _sanitize_branch(parameters.get("branch", ""))
        if not branch: return "Especificá la rama a mergear."
        ok, out = _git(["merge", branch], cwd=cwd)
        return f"Merge de '{branch}' completado." if ok else f"Conflicto/error: {out[:400]}"

    # ── DIFF ─────────────────────────────────────────────────────────────────
    elif action == "diff":
        file_p = parameters.get("file", "").strip()
        args   = ["diff", "--stat"]
        if file_p and not any(c in file_p for c in ["&","|",";","`","$"]):
            args.append(file_p)
        ok, out = _git(args, cwd=cwd)
        return f"Diferencias:\n{out[:2000]}" if (ok and out) else "Sin diferencias."

    # ── STASH ────────────────────────────────────────────────────────────────
    elif action == "stash":
        sub = parameters.get("subaction", "save").lower()
        if sub in ("save", "guardar"):
            msg_s = parameters.get("message", "JARVIS stash")
            ok, out = _git(["stash", "push", "-m", _sanitize_message(msg_s)], cwd=cwd)
            return f"Cambios guardados en stash." if ok else f"Error: {out}"
        elif sub in ("pop", "restaurar"):
            ok, out = _git(["stash", "pop"], cwd=cwd)
            return "Stash restaurado." if ok else f"Error: {out}"
        elif sub == "list":
            ok, out = _git(["stash", "list"], cwd=cwd)
            return f"Stash:\n{out}" if (ok and out) else "No hay stash."

    # ── CLONE ────────────────────────────────────────────────────────────────
    elif action == "clone":
        url  = parameters.get("url", "").strip()
        dest = parameters.get("destination", "").strip()
        if not url: return "Especificá la url del repositorio a clonar."
        # Validate URL
        if not re.match(r"^https?://|^git@", url):
            return "URL de repositorio inválida."
        args = ["clone", url]
        if dest:
            args.append(dest)
        ok, out = _git(args, cwd=cwd or os.path.expanduser("~"), timeout=300)
        return f"Repositorio clonado en {dest or ''}." if ok else f"Error clonando: {out[:400]}"

    # ── RESET ────────────────────────────────────────────────────────────────
    elif action == "reset":
        mode  = parameters.get("mode", "soft")  # soft | mixed | hard
        target= parameters.get("target", "HEAD~1")
        if mode not in ("soft", "mixed", "hard"):
            return "Modo de reset inválido. Usa: soft | mixed | hard"
        if mode == "hard":
            return ("⚠ Reset --hard puede perder trabajo. "
                    "Para confirmar, usá action=reset_confirm con mode=hard.")
        ok, out = _git(["reset", f"--{mode}", target], cwd=cwd)
        return f"Reset {mode} a {target}." if ok else f"Error: {out}"

    elif action == "reset_confirm":
        mode   = parameters.get("mode", "mixed")
        target = parameters.get("target", "HEAD~1")
        ok, out = _git(["reset", f"--{mode}", target], cwd=cwd)
        return f"Reset --{mode} a {target} aplicado." if ok else f"Error: {out}"

    # ── TAG ──────────────────────────────────────────────────────────────────
    elif action == "tag":
        sub  = parameters.get("subaction", "list")
        name = _sanitize_branch(parameters.get("name", ""))
        if sub == "list":
            ok, out = _git(["tag", "--sort=-creatordate"], cwd=cwd)
            return f"Tags:\n{out}" if (ok and out) else "No hay tags."
        elif sub in ("create", "nueva"):
            if not name: return "Especificá name para el tag."
            ok, out = _git(["tag", name], cwd=cwd)
            return f"Tag '{name}' creado." if ok else f"Error: {out}"
        elif sub in ("push_tags", "subir"):
            ok, out = _git(["push", "--tags"], cwd=cwd, timeout=60)
            return "Tags subidos." if ok else f"Error: {out}"

    # ── RAW COMMAND ───────────────────────────────────────────────────────────
    elif action == "raw":
        cmd = parameters.get("command", "").strip()
        if not cmd: return "Especificá command para el comando raw."
        # Safety: block destructive patterns
        BLOCKED = ["push --force", "push -f", "filter-branch",
                   "reset --hard", "clean -f", "rm -r"]
        if any(b in cmd for b in BLOCKED):
            return f"Comando bloqueado por seguridad. Usá las acciones específicas."
        parts = cmd.split()
        ok, out = _git(parts, cwd=cwd, timeout=60)
        return out[:2000] if out else ("Comando ejecutado sin salida." if ok else "Error sin detalle.")

    return (f"Acción git '{action}' no reconocida. "
            "Usa: status | log | add | commit | push | pull | branch | checkout | "
            "merge | diff | stash | clone | reset | tag | raw | set_repo | init")
