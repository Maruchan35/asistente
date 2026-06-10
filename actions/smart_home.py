"""smart_home.py — Home Assistant + Philips Hue + generic IoT control.
Connects to a local Home Assistant instance via REST API.
Fallback: Philips Hue bridge direct API."""
from __future__ import annotations
import json, urllib.request, urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _load_keys() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _load_conf() -> dict:
    p = BASE_DIR / "config" / "smart_home_config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_conf(cfg: dict):
    p = BASE_DIR / "config" / "smart_home_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

# ── Home Assistant REST API ───────────────────────────────────────────────────
def _ha_request(method: str, path: str, token: str, base_url: str,
                body: dict | None = None, timeout: int = 8) -> dict | list | str:
    url = f"{base_url.rstrip('/')}/api/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", errors="replace")
            try:
                return json.loads(text)
            except Exception:
                return text
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")[:200]
        return f"HTTP {e.code}: {body_err}"
    except urllib.error.URLError as e:
        return f"No se pudo conectar a Home Assistant ({base_url}): {e.reason}"
    except Exception as e:
        return f"Error: {e}"

# ── Philips Hue direct API ────────────────────────────────────────────────────
def _hue_request(method: str, path: str, bridge_ip: str, username: str,
                 body: dict | None = None, timeout: int = 5) -> dict | str:
    url = f"http://{bridge_ip}/api/{username}/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return f"Error Hue: {e}"

def _hue_on(bridge_ip: str, username: str, light_id: str, on: bool,
             brightness: int | None = None, color_temp: int | None = None) -> str:
    state: dict = {"on": on}
    if brightness is not None:
        state["bri"] = max(1, min(254, int(brightness * 254 / 100)))
    if color_temp is not None:
        state["ct"] = color_temp
    result = _hue_request("PUT", f"lights/{light_id}/state", bridge_ip, username, state)
    if isinstance(result, list) and result:
        return "OK" if "success" in result[0] else str(result)
    return str(result)

# ══════════════════════════════════════════════════════════════════════════════
def smart_home(parameters: dict, player=None) -> str:
    action = parameters.get("action", "status").lower().strip()
    device = parameters.get("device", parameters.get("entity_id", "")).strip()
    value  = parameters.get("value", parameters.get("state", "")).strip()

    def log(msg: str):
        if player:
            player.write_log(f"🏠 Smart Home: {msg}")

    keys = _load_keys()
    cfg  = _load_conf()

    ha_url   = keys.get("ha_url",   cfg.get("ha_url",   "")).strip()
    ha_token = keys.get("ha_token", cfg.get("ha_token", "")).strip()
    hue_ip   = keys.get("hue_bridge_ip",  cfg.get("hue_bridge_ip",  "")).strip()
    hue_user = keys.get("hue_username",   cfg.get("hue_username",   "")).strip()

    has_ha  = bool(ha_url and ha_token)
    has_hue = bool(hue_ip and hue_user)

    # ── SETUP ─────────────────────────────────────────────────────────────────
    if action in ("setup", "configurar", "config"):
        return (
            "Configuración de Smart Home:\n\n"
            "HOME ASSISTANT:\n"
            "  1. Asegurate de tener Home Assistant en tu red local\n"
            "  2. Perfil → Tokens de acceso de larga duración → Crear token\n"
            "  3. Agregá en config/api_keys.json:\n"
            "     'ha_url': 'http://homeassistant.local:8123'\n"
            "     'ha_token': 'tu_token_largo'\n\n"
            "PHILIPS HUE:\n"
            "  1. Abrí http://<ip_del_bridge>/debug/clip.html\n"
            "  2. POST a /api con body {\"devicetype\":\"jarvis\"}\n"
            "  3. Presioná el botón del bridge, enviá el request\n"
            "  4. Copiá el username generado\n"
            "  5. Agregá en config/api_keys.json:\n"
            "     'hue_bridge_ip': '192.168.1.x'\n"
            "     'hue_username': 'tu_username'"
        )

    if not has_ha and not has_hue:
        return (
            "Smart home no configurado.\n"
            "Usá action=setup para ver cómo conectar Home Assistant o Philips Hue.\n"
            "Necesitás configurar al menos una de las dos opciones."
        )

    # ══ HOME ASSISTANT ════════════════════════════════════════════════════════
    if has_ha:

        # ── STATUS ────────────────────────────────────────────────────────────
        if action in ("status", "estado", "list", "listar"):
            domain = parameters.get("domain", "").strip()
            path   = f"states" + (f"/{domain}" if domain else "")
            result = _ha_request("GET", path, ha_token, ha_url)
            if isinstance(result, str):
                return f"Error conectando a Home Assistant: {result}"
            if isinstance(result, list):
                # Filter by domain if specified
                if domain:
                    items = [s for s in result if s.get("entity_id","").startswith(domain)]
                else:
                    items = result[:30]
                lines = [f"Dispositivos Home Assistant ({len(items)}):"]
                for s in items:
                    eid   = s.get("entity_id", "?")
                    state = s.get("state", "?")
                    name  = s.get("attributes", {}).get("friendly_name", eid)
                    lines.append(f"  {name}: {state} [{eid}]")
                log(f"{len(items)} dispositivos listados")
                return "\n".join(lines)
            if isinstance(result, dict):
                return f"Estado: {result.get('state','?')} [{result.get('entity_id','?')}]"
            return str(result)

        # ── ENTITY STATUS ─────────────────────────────────────────────────────
        elif action in ("get", "info"):
            if not device:
                return "Especificá device con el entity_id (ej: light.sala)."
            result = _ha_request("GET", f"states/{device}", ha_token, ha_url)
            if isinstance(result, str):
                return f"Error: {result}"
            if isinstance(result, dict):
                attrs = result.get("attributes", {})
                name  = attrs.get("friendly_name", device)
                state = result.get("state", "?")
                temp  = attrs.get("current_temperature", attrs.get("temperature",""))
                bright= attrs.get("brightness", "")
                color = attrs.get("rgb_color", "")
                info  = [f"{name}: {state}"]
                if temp:  info.append(f"  Temperatura: {temp}°C")
                if bright: info.append(f"  Brillo: {int(bright/254*100)}%")
                if color:  info.append(f"  Color RGB: {color}")
                return "\n".join(info)
            return str(result)

        # ── TURN ON/OFF ───────────────────────────────────────────────────────
        elif action in ("turn_on", "encender", "on"):
            if not device:
                return "Especificá device con el entity_id."
            domain = device.split(".")[0]
            result = _ha_request("POST", f"services/{domain}/turn_on",
                                  ha_token, ha_url, {"entity_id": device})
            msg = f"'{device}' encendido."
            log(msg); return msg

        elif action in ("turn_off", "apagar", "off"):
            if not device:
                return "Especificá device con el entity_id."
            domain = device.split(".")[0]
            result = _ha_request("POST", f"services/{domain}/turn_off",
                                  ha_token, ha_url, {"entity_id": device})
            msg = f"'{device}' apagado."
            log(msg); return msg

        elif action in ("toggle", "alternar"):
            if not device:
                return "Especificá device con el entity_id."
            domain = device.split(".")[0]
            _ha_request("POST", f"services/{domain}/toggle",
                         ha_token, ha_url, {"entity_id": device})
            msg = f"'{device}' alternado."
            log(msg); return msg

        # ── LIGHTS ────────────────────────────────────────────────────────────
        elif action in ("set_brightness", "brillo"):
            if not device: return "Especificá device."
            brightness = int(parameters.get("brightness", parameters.get("value", 50)))
            body = {"entity_id": device,
                    "brightness_pct": max(0, min(100, brightness))}
            _ha_request("POST", "services/light/turn_on", ha_token, ha_url, body)
            msg = f"Brillo de '{device}' al {brightness}%."
            log(msg); return msg

        elif action in ("set_color", "color"):
            if not device: return "Especificá device."
            color_name = parameters.get("color", value).lower()
            COLOR_RGB = {
                "rojo": [255,0,0], "verde": [0,255,0], "azul": [0,0,255],
                "blanco": [255,255,255], "amarillo": [255,255,0],
                "naranja": [255,165,0], "violeta": [148,0,211],
                "rosa": [255,20,147], "cyan": [0,255,255],
                "red": [255,0,0], "green": [0,255,0], "blue": [0,0,255],
                "white": [255,255,255], "yellow": [255,255,0],
            }
            rgb = COLOR_RGB.get(color_name, [255,255,255])
            body = {"entity_id": device, "rgb_color": rgb}
            _ha_request("POST", "services/light/turn_on", ha_token, ha_url, body)
            msg = f"Color de '{device}' cambiado a {color_name}."
            log(msg); return msg

        # ── CLIMATE ──────────────────────────────────────────────────────────
        elif action in ("set_temperature", "temperatura", "temp"):
            if not device: return "Especificá device (ej: climate.living_room)."
            temp = float(parameters.get("temperature", parameters.get("value", 22)))
            body = {"entity_id": device, "temperature": temp}
            _ha_request("POST", "services/climate/set_temperature",
                         ha_token, ha_url, body)
            msg = f"Temperatura de '{device}' → {temp}°C."
            log(msg); return msg

        # ── SCENES ────────────────────────────────────────────────────────────
        elif action in ("scene", "escena", "activate_scene"):
            scene_id = parameters.get("scene", device)
            if not scene_id.startswith("scene."):
                scene_id = f"scene.{scene_id}"
            _ha_request("POST", "services/scene/turn_on",
                         ha_token, ha_url, {"entity_id": scene_id})
            msg = f"Escena '{scene_id}' activada."
            log(msg); return msg

        # ── SCRIPT ────────────────────────────────────────────────────────────
        elif action in ("script", "run_script"):
            script_id = parameters.get("script", device)
            if not script_id.startswith("script."):
                script_id = f"script.{script_id}"
            _ha_request("POST", "services/script/turn_on",
                         ha_token, ha_url, {"entity_id": script_id})
            msg = f"Script '{script_id}' ejecutado."
            log(msg); return msg

        # ── AUTOMATIONS ──────────────────────────────────────────────────────
        elif action in ("automations", "automatizaciones"):
            result = _ha_request("GET", "states", ha_token, ha_url)
            if isinstance(result, list):
                autos = [s for s in result if s["entity_id"].startswith("automation.")]
                lines = [f"Automatizaciones ({len(autos)}):"]
                for a in autos:
                    state = a.get("state", "?")
                    name  = a.get("attributes", {}).get("friendly_name", a["entity_id"])
                    lines.append(f"  {'✅' if state=='on' else '⏸'} {name}")
                return "\n".join(lines)
            return "No se pudieron obtener las automatizaciones."

        # ── CALL SERVICE ─────────────────────────────────────────────────────
        elif action in ("service", "call_service"):
            svc_domain = parameters.get("domain", "").strip()
            svc_name   = parameters.get("service", "").strip()
            if not svc_domain or not svc_name:
                return "Especificá domain y service."
            body = parameters.get("data", {"entity_id": device})
            _ha_request("POST", f"services/{svc_domain}/{svc_name}",
                         ha_token, ha_url, body)
            msg = f"Servicio {svc_domain}.{svc_name} ejecutado."
            log(msg); return msg

        else:
            # Generic: try to call turn_on/turn_off/toggle based on value
            if value in ("on", "encender", "true", "1"):
                domain = device.split(".")[0] if "." in device else "homeassistant"
                _ha_request("POST", f"services/{domain}/turn_on",
                             ha_token, ha_url, {"entity_id": device})
                return f"'{device}' encendido."
            elif value in ("off", "apagar", "false", "0"):
                domain = device.split(".")[0] if "." in device else "homeassistant"
                _ha_request("POST", f"services/{domain}/turn_off",
                             ha_token, ha_url, {"entity_id": device})
                return f"'{device}' apagado."

    # ══ PHILIPS HUE (fallback / standalone) ══════════════════════════════════
    if has_hue:
        # List lights
        if action in ("status", "list", "listar", "lights", "luces"):
            result = _hue_request("GET", "lights", hue_ip, hue_user)
            if isinstance(result, str):
                return f"Error Hue: {result}"
            lines = ["Luces Philips Hue:"]
            for lid, ldata in result.items():
                name  = ldata.get("name", f"Luz {lid}")
                state = ldata.get("state", {})
                on_s  = "ON" if state.get("on") else "OFF"
                bri   = int(state.get("bri", 0) / 254 * 100)
                lines.append(f"  [{lid}] {name}: {on_s} (brillo: {bri}%)")
            return "\n".join(lines)

        elif action in ("turn_on", "encender", "on"):
            light_id = parameters.get("light_id", device or "1")
            bri = parameters.get("brightness")
            result = _hue_on(hue_ip, hue_user, light_id, True,
                              brightness=int(bri) if bri else None)
            msg = f"Luz Hue {light_id} encendida."
            log(msg); return msg

        elif action in ("turn_off", "apagar", "off"):
            light_id = parameters.get("light_id", device or "1")
            result = _hue_on(hue_ip, hue_user, light_id, False)
            msg = f"Luz Hue {light_id} apagada."
            log(msg); return msg

        elif action in ("set_brightness", "brillo"):
            light_id = parameters.get("light_id", device or "1")
            bri = int(parameters.get("brightness", value or 50))
            _hue_on(hue_ip, hue_user, light_id, True, brightness=bri)
            msg = f"Brillo de luz Hue {light_id} → {bri}%."
            log(msg); return msg

    return (f"Acción '{action}' no reconocida o sin backend configurado. "
            "Usá action=setup para ver instrucciones de configuración.")
