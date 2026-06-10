"""weather_report.py — Rich weather: current conditions + 3-day forecast + alerts."""
from __future__ import annotations
import json, urllib.request, urllib.parse

def _get(url: str, timeout: int = 6) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

def weather_action(parameters: dict, player=None) -> str:
    city  = (parameters.get("city") or parameters.get("location") or "").strip()
    mode  = parameters.get("mode", "current").lower()   # current | forecast | alerts
    units = parameters.get("units", "metric").lower()   # metric | imperial

    if not city:
        # Try to detect from IP
        try:
            ip_data = json.loads(_get("https://ipinfo.io/json", timeout=4))
            city = ip_data.get("city", "Mexico City")
        except Exception:
            city = "Mexico City"

    try:
        encoded = urllib.parse.quote(city)
        unit_sym = "°C" if units == "metric" else "°F"

        # ── Current conditions (always fetched) ───────────────────────────────
        # wttr.in JSON API — very reliable, no key needed
        url_json = f"https://wttr.in/{encoded}?format=j1"
        raw = json.loads(_get(url_json))

        cur = raw["current_condition"][0]
        desc_list = [d["value"] for d in cur.get("weatherDesc", [{"value":""}])]
        desc = desc_list[0] if desc_list else "?"

        temp_c   = int(cur.get("temp_C", 0))
        feels_c  = int(cur.get("FeelsLikeC", 0))
        humidity = cur.get("humidity", "?")
        wind_kmh = cur.get("windspeedKmph", "?")
        uv       = cur.get("uvIndex", "?")
        vis      = cur.get("visibility", "?")

        if units == "imperial":
            temp   = int(cur.get("temp_F", temp_c * 9/5 + 32))
            feels  = int(cur.get("FeelsLikeF", feels_c * 9/5 + 32))
        else:
            temp, feels = temp_c, feels_c

        current_str = (
            f"{city}: {desc}, {temp}{unit_sym} (sensación {feels}{unit_sym})\n"
            f"Humedad: {humidity}%  •  Viento: {wind_kmh} km/h  •  UV: {uv}  •  Visibilidad: {vis} km"
        )

        if mode == "current":
            if player: player.write_log(f"🌤 {current_str[:80]}")
            return current_str

        # ── 3-day forecast ────────────────────────────────────────────────────
        if mode in ("forecast", "pronostico", "pronóstico"):
            days_raw = raw.get("weather", [])[:3]
            lines = [current_str, "\nPronóstico:"]
            day_names = ["Hoy", "Mañana", "Pasado"]
            for i, day in enumerate(days_raw):
                date = day.get("date", "")
                max_c = int(day.get("maxtempC", 0))
                min_c = int(day.get("mintempC", 0))
                if units == "imperial":
                    max_t = int(day.get("maxtempF", max_c*9/5+32))
                    min_t = int(day.get("mintempF", min_c*9/5+32))
                else:
                    max_t, min_t = max_c, min_c
                hourly = day.get("hourly", [])
                rain_chances = [int(h.get("chanceofrain", 0)) for h in hourly]
                max_rain = max(rain_chances) if rain_chances else 0
                descs = [d["value"] for h in hourly for d in h.get("weatherDesc", [{"value":""}])]
                day_desc = descs[len(descs)//2] if descs else "?"
                label = day_names[i] if i < len(day_names) else date
                lines.append(
                    f"  {label}: {day_desc}, {min_t}–{max_t}{unit_sym}, "
                    f"lluvia: {max_rain}%"
                )
            result = "\n".join(lines)
            if player: player.write_log(f"🌤 Pronóstico solicitado: {city}")
            return result

        # ── Alerts ────────────────────────────────────────────────────────────
        if mode in ("alerts", "alertas"):
            # wttr.in doesn't have alerts — check uv and wind
            alerts = []
            if int(str(uv) or "0") >= 8:
                alerts.append(f"⚠ UV muy alto ({uv}). Usar protector solar.")
            if int(str(wind_kmh) or "0") >= 50:
                alerts.append(f"⚠ Viento fuerte ({wind_kmh} km/h). Precaución al manejar.")
            if temp_c >= 38:
                alerts.append(f"⚠ Calor extremo ({temp_c}°C). Mantenerse hidratado.")
            if temp_c <= 0:
                alerts.append(f"⚠ Temperatura bajo cero ({temp_c}°C). Riesgo de hielo.")
            result = current_str + "\n" + ("\n".join(alerts) if alerts else "Sin alertas activas.")
            if player: player.write_log(f"🌤 Alertas solicitadas: {city}")
            return result

        return current_str

    except Exception as e:
        msg = f"No pude obtener el clima para '{city}': {e}"
        if player: player.write_log(f"⚠ {msg}")
        return msg
