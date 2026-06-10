"""flight_finder.py — Flight search via Google Flights browser automation + Aviationstack API.
Opens Google Flights with prefilled params and optionally fetches live data via API."""
from __future__ import annotations
import json, re, urllib.parse, urllib.request, webbrowser
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _load_keys() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _get(url: str, timeout: int = 10) -> dict | str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return f"Error: {e}"

def _parse_date(s: str) -> str:
    """Convert natural date to YYYY-MM-DD."""
    s = s.strip().lower()
    now = datetime.now()
    if s in ("hoy", "today"):
        return now.strftime("%Y-%m-%d")
    if s in ("mañana", "tomorrow"):
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    # Try ISO
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    # DD/MM or DD/MM/YYYY
    m = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", s)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        return f"{year:04d}-{month:02d}-{day:02d}"
    return now.strftime("%Y-%m-%d")

def _airport_code(place: str) -> str:
    """Try to extract/map IATA code."""
    CODES = {
        "mexico city": "MEX", "cdmx": "MEX", "ciudad de mexico": "MEX",
        "guadalajara": "GDL", "monterrey": "MTY", "cancun": "CUN",
        "buenos aires": "EZE", "bogota": "BOG", "lima": "LIM",
        "santiago": "SCL", "madrid": "MAD", "barcelona": "BCN",
        "miami": "MIA", "new york": "JFK", "nueva york": "JFK",
        "los angeles": "LAX", "chicago": "ORD", "houston": "IAH",
        "london": "LHR", "londre": "LHR", "paris": "CDG",
        "amsterdam": "AMS", "frankfurt": "FRA", "rome": "FCO",
        "tokyo": "NRT", "dubai": "DXB", "toronto": "YYZ",
        "sao paulo": "GRU", "rio": "GIG",
    }
    p = place.strip().lower()
    # If already IATA code
    if re.match(r"^[A-Z]{3}$", place.strip()):
        return place.strip().upper()
    for key, code in CODES.items():
        if key in p:
            return code
    return place.strip().upper()[:3]

# ══════════════════════════════════════════════════════════════════════════════
def flight_finder(parameters: dict, player=None) -> str:
    action    = parameters.get("action", "search").lower().strip()
    origin    = parameters.get("origin", parameters.get("from", parameters.get("desde", ""))).strip()
    dest      = parameters.get("destination", parameters.get("to", parameters.get("hasta", ""))).strip()
    dep_date  = parameters.get("departure_date", parameters.get("date", parameters.get("fecha", ""))).strip()
    ret_date  = parameters.get("return_date", parameters.get("retorno", "")).strip()
    passengers= int(parameters.get("passengers", parameters.get("pasajeros", 1)))
    cabin     = parameters.get("cabin", "economy").lower()  # economy | business | first
    flexible  = parameters.get("flexible", False)

    def log(msg: str):
        if player:
            player.write_log(f"✈ Vuelos: {msg}")

    # ── SETUP ────────────────────────────────────────────────────────────────
    if action == "setup":
        return ("Para búsqueda de vuelos con datos en tiempo real:\n"
                "1. Registrate en https://aviationstack.com (gratis hasta 500 req/mes)\n"
                "2. Agregá 'aviationstack_api_key' en config/api_keys.json\n"
                "Sin API key, JARVIS abre Google Flights con los parámetros pre-cargados.")

    if not origin:
        return "Especificá origin con el aeropuerto/ciudad de origen."
    if not dest:
        return "Especificá destination con el aeropuerto/ciudad de destino."

    origin_code = _airport_code(origin)
    dest_code   = _airport_code(dest)
    dep_date_fmt = _parse_date(dep_date) if dep_date else (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    log(f"{origin_code} → {dest_code} ({dep_date_fmt})")

    # ── API SEARCH (Aviationstack) ─────────────────────────────────────────
    keys = _load_keys()
    avi_key = keys.get("aviationstack_api_key", "").strip()

    api_result = ""
    if avi_key:
        # Aviationstack schedules endpoint
        url = (f"http://api.aviationstack.com/v1/flights"
               f"?access_key={avi_key}"
               f"&dep_iata={origin_code}"
               f"&arr_iata={dest_code}"
               f"&limit=5")
        data = _get(url)
        if isinstance(data, dict) and "data" in data:
            flights = data["data"]
            if flights:
                lines = [f"Vuelos {origin_code} → {dest_code}:"]
                for fl in flights[:5]:
                    airline = fl.get("airline", {}).get("name", "?")
                    flight_n = fl.get("flight", {}).get("iata", "?")
                    dep_t    = fl.get("departure", {}).get("scheduled", "?")[:16]
                    arr_t    = fl.get("arrival", {}).get("scheduled", "?")[:16]
                    status   = fl.get("flight_status", "?")
                    lines.append(f"  {airline} {flight_n}: {dep_t} → {arr_t} ({status})")
                api_result = "\n".join(lines)
                log(f"{len(flights)} vuelos encontrados via API")
            else:
                api_result = f"No se encontraron vuelos programados {origin_code}→{dest_code} hoy."
        elif isinstance(data, dict) and "error" in data:
            log(f"API error: {data['error'].get('message','?')}")

    # ── GOOGLE FLIGHTS URL (always) ───────────────────────────────────────
    cabin_map = {"economy": "1", "premium_economy": "2", "business": "3", "first": "4"}
    cabin_code = cabin_map.get(cabin, "1")

    # Google Flights deep link format
    # /flights/search#flt=ORIGIN.DEST.YYYY-MM-DD;c:cabin;e:1;sd:1;t:f
    dep_no_dash = dep_date_fmt.replace("-", "")
    one_way = not bool(ret_date)

    gf_params = f"{origin_code}.{dest_code}.{dep_date_fmt}"
    if ret_date:
        ret_date_fmt = _parse_date(ret_date)
        gf_params   += f"*{dest_code}.{origin_code}.{ret_date_fmt}"

    google_flights_url = (
        f"https://www.google.com/travel/flights/search"
        f"?q=vuelos+{urllib.parse.quote(origin)}+a+{urllib.parse.quote(dest)}"
        f"+{dep_date_fmt}&hl=es"
    )

    # Kayak as alternative
    trip_type = "oneway" if one_way else "roundtrip"
    kayak_url = (
        f"https://www.kayak.com/flights/{origin_code}-{dest_code}"
        f"/{dep_date_fmt}"
        + (f"/{_parse_date(ret_date)}" if ret_date else "")
        + f"/{passengers}adults/{cabin}/{'flexible' if flexible else ''}"
    )

    # Open Google Flights in browser
    if action in ("search", "buscar", "find"):
        webbrowser.open(google_flights_url)

    # Build summary
    trip_str = "Ida y vuelta" if ret_date else "Solo ida"
    result_parts = [
        f"✈ Búsqueda de vuelos:",
        f"  {origin_code} → {dest_code}",
        f"  Salida: {dep_date_fmt}" + (f" | Regreso: {_parse_date(ret_date)}" if ret_date else ""),
        f"  Tipo: {trip_str} | Cabina: {cabin.capitalize()} | Pasajeros: {passengers}",
    ]

    if api_result:
        result_parts.append(f"\n{api_result}")
    else:
        result_parts.append("\n📌 Google Flights abierto en el navegador con tu búsqueda.")
        result_parts.append(f"  También podés buscar en Kayak: {kayak_url}")

    if not avi_key:
        result_parts.append("\n💡 Para precios en tiempo real, configurá una API key de Aviationstack.")

    log(f"{origin_code}→{dest_code} búsqueda completada")
    return "\n".join(result_parts)
