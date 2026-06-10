"""
game_updater.py — Steam & Epic game management for JARVIS.
Uses Steam VDF files (no SteamCMD required) + subprocess for updates.
"""

import os
import re
import glob
import subprocess
import platform

# ── Steam paths ────────────────────────────────────────────────────────────────
_STEAM_ROOTS = [
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    os.path.expandvars(r"%ProgramFiles(x86)%\Steam"),
    os.path.expandvars(r"%ProgramFiles%\Steam"),
]

def _find_steam_root() -> str | None:
    for p in _STEAM_ROOTS:
        if os.path.isdir(p):
            return p
    return None

def _parse_vdf_str(text: str, key: str) -> str | None:
    """Simple regex VDF parser for string values."""
    m = re.search(rf'"{re.escape(key)}"\s+"([^"]+)"', text)
    return m.group(1) if m else None

def _get_library_folders(steam_root: str) -> list[str]:
    """Return all Steam library paths (including external ones)."""
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    libs = [os.path.join(steam_root, "steamapps")]
    try:
        with open(vdf_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        # New format: "path" entries
        for m in re.finditer(r'"path"\s+"([^"]+)"', content):
            folder = m.group(1).replace("\\\\", "\\")
            steamapps = os.path.join(folder, "steamapps")
            if os.path.isdir(steamapps) and steamapps not in libs:
                libs.append(steamapps)
    except Exception:
        pass
    return libs

def _list_steam_games(steam_root: str) -> list[dict]:
    """Scan appmanifest_*.acf files and return list of installed games."""
    games = []
    libs = _get_library_folders(steam_root)
    for lib in libs:
        for acf in glob.glob(os.path.join(lib, "appmanifest_*.acf")):
            try:
                with open(acf, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                app_id   = _parse_vdf_str(content, "appid")
                name     = _parse_vdf_str(content, "name")
                state    = _parse_vdf_str(content, "StateFlags")
                size_raw = _parse_vdf_str(content, "SizeOnDisk")
                if name:
                    size_gb = f"{int(size_raw) / 1e9:.1f} GB" if size_raw else "?"
                    games.append({
                        "app_id": app_id or "?",
                        "name":   name,
                        "state":  state or "?",
                        "size":   size_gb,
                    })
            except Exception:
                pass
    games.sort(key=lambda g: g["name"].lower())
    return games

def _launch_steam_update(app_id: str, steam_root: str) -> str:
    """Launch SteamCMD to update a game, or open Steam update UI as fallback."""
    steamcmd = os.path.join(steam_root, "steamcmd.exe")
    if os.path.isfile(steamcmd):
        cmd = [steamcmd, "+login", "anonymous",
               "+app_update", app_id, "validate", "+quit"]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return f"SteamCMD lanzado para actualizar AppID {app_id}."
    else:
        # Fallback: open the game's Steam store page (steam:// protocol)
        os.startfile(f"steam://nav/games/details/{app_id}")
        return f"SteamCMD no encontrado. Abriendo panel de Steam para AppID {app_id}."

# ── Epic Games ─────────────────────────────────────────────────────────────────
def _list_epic_games() -> list[dict]:
    """List Epic Games installed via manifest files."""
    manifest_dirs = [
        r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests",
        os.path.expandvars(r"%ProgramData%\Epic\EpicGamesLauncher\Data\Manifests"),
    ]
    games = []
    import json
    for mdir in manifest_dirs:
        if not os.path.isdir(mdir):
            continue
        for f in glob.glob(os.path.join(mdir, "*.item")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                name = data.get("DisplayName") or data.get("AppName")
                if name:
                    games.append({
                        "app_id": data.get("AppName", "?"),
                        "name":   name,
                        "size":   "?",
                    })
            except Exception:
                pass
    games.sort(key=lambda g: g["name"].lower())
    return games

# ── Main entry point ───────────────────────────────────────────────────────────
def game_updater(parameters: dict, player=None, speak=None) -> str:
    """
    Manages Steam and Epic Games installations.
    Actions: list | update | install | open | download_status
    """
    action    = parameters.get("action", "list").lower().strip()
    platform_ = parameters.get("platform", "both").lower().strip()
    game_name = parameters.get("game_name", "").strip()
    app_id    = parameters.get("app_id", "").strip()

    def log(msg):
        if player and hasattr(player, "write_log"):
            player.write_log(f"🎮 {msg}")

    steam_root = _find_steam_root()

    # ── LIST ────────────────────────────────────────────────────────────────────
    if action in ("list", "listar", "installed", "instalados"):
        lines = []

        if platform_ in ("steam", "both") and steam_root:
            steam_games = _list_steam_games(steam_root)
            if game_name:
                steam_games = [g for g in steam_games
                               if game_name.lower() in g["name"].lower()]
            if steam_games:
                lines.append(f"Steam ({len(steam_games)} juegos instalados):")
                for g in steam_games[:20]:   # cap at 20 for readability
                    lines.append(f"  • {g['name']} [{g['size']}]")
                if len(steam_games) > 20:
                    lines.append(f"  … y {len(steam_games) - 20} más.")
            else:
                lines.append("Steam: no se encontraron juegos instalados.")

        elif platform_ in ("steam", "both") and not steam_root:
            lines.append("Steam no encontrado en esta PC.")

        if platform_ in ("epic", "both"):
            epic_games = _list_epic_games()
            if game_name:
                epic_games = [g for g in epic_games
                              if game_name.lower() in g["name"].lower()]
            if epic_games:
                lines.append(f"\nEpic Games ({len(epic_games)} juegos):")
                for g in epic_games[:20]:
                    lines.append(f"  • {g['name']}")
                if len(epic_games) > 20:
                    lines.append(f"  … y {len(epic_games) - 20} más.")
            # no message if Epic not found — optional launcher

        result = "\n".join(lines) if lines else "No se encontraron juegos instalados."
        log(result)
        return result

    # ── UPDATE ──────────────────────────────────────────────────────────────────
    elif action in ("update", "actualizar"):
        if not steam_root:
            return "Steam no está instalado en esta PC."

        if not app_id and game_name:
            # Try to find appid from installed games
            games = _list_steam_games(steam_root)
            matches = [g for g in games if game_name.lower() in g["name"].lower()]
            if not matches:
                return f"No encontré '{game_name}' instalado en Steam."
            if len(matches) > 1:
                names = ", ".join(g["name"] for g in matches[:5])
                return f"Encontré varios juegos: {names}. Sé más específico."
            app_id = matches[0]["app_id"]

        if not app_id:
            # Update all — open Steam > Library > Updates
            os.startfile("steam://open/downloads")
            return "Abriendo Steam > Descargas. Aquí puedes ver actualizaciones pendientes."

        result = _launch_steam_update(app_id, steam_root)
        log(result)
        return result

    # ── INSTALL ─────────────────────────────────────────────────────────────────
    elif action in ("install", "instalar", "download", "descargar"):
        if not steam_root:
            return "Steam no está instalado en esta PC."
        if not app_id:
            if game_name:
                # Open Steam store search
                import urllib.parse
                q = urllib.parse.quote(game_name)
                os.startfile(f"https://store.steampowered.com/search/?term={q}")
                return f"Abriendo Steam Store con búsqueda de '{game_name}'."
            return "Necesito el AppID de Steam o el nombre del juego para instalar."
        os.startfile(f"steam://install/{app_id}")
        return f"Steam abrió el diálogo de instalación para AppID {app_id}."

    # ── DOWNLOAD STATUS ─────────────────────────────────────────────────────────
    elif action in ("download_status", "estado_descarga", "status"):
        if not steam_root:
            return "Steam no está instalado en esta PC."
        os.startfile("steam://open/downloads")
        return "Abriendo Steam > Descargas para ver el estado actual."

    # ── OPEN (redirect) ─────────────────────────────────────────────────────────
    elif action in ("open", "abrir", "launch", "ejecutar"):
        # If user wants to open a specific game
        if not steam_root:
            return "Steam no está instalado en esta PC."
        if app_id:
            os.startfile(f"steam://rungameid/{app_id}")
            return f"Lanzando juego con AppID {app_id} en Steam."
        if game_name:
            games = _list_steam_games(steam_root)
            matches = [g for g in games if game_name.lower() in g["name"].lower()]
            if matches:
                os.startfile(f"steam://rungameid/{matches[0]['app_id']}")
                return f"Lanzando {matches[0]['name']} en Steam."
        os.startfile("steam://open/games")
        return "Abriendo Steam > Biblioteca."

    else:
        return (f"Acción '{action}' no reconocida. "
                "Usa: list, update, install, download_status, open.")
