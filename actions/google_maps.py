"""
google_maps.py — Abre Google Maps en el navegador con la búsqueda o ruta indicada.
"""
import webbrowser
import urllib.parse


def google_maps(parameters: dict, player=None) -> str:
    """
    Abre Google Maps en el navegador.

    Acciones:
        search      — Busca un lugar o dirección
        directions  — Abre ruta de origen a destino
        nearby      — Busca negocios/servicios cercanos a una ubicación
    """
    action      = parameters.get("action", "search").lower().strip()
    query       = parameters.get("query", "").strip()
    destination = parameters.get("destination", "").strip()
    origin      = parameters.get("origin", "").strip()
    category    = parameters.get("category", "").strip()   # restaurantes, gasolineras, etc.

    # ── Auto-detectar acción por parámetros ──────────────────────────────────
    if origin and destination:
        action = "directions"
    elif category and (query or destination):
        action = "nearby"

    # ── BUSCAR LUGAR ─────────────────────────────────────────────────────────
    if action in ("search", "buscar"):
        search_term = query or destination or origin
        if not search_term:
            webbrowser.open("https://www.google.com/maps")
            return "Abriendo Google Maps."
        url = "https://www.google.com/maps/search/" + urllib.parse.quote(search_term)
        webbrowser.open(url)
        msg = f"Buscando '{search_term}' en Google Maps."

    # ── RUTA / DIRECCIONES ───────────────────────────────────────────────────
    elif action in ("directions", "ruta", "cómo llegar", "como llegar", "navigate"):
        if not destination:
            destination = query
        if not destination:
            return "Error: Necesito el destino ('destination') para calcular la ruta."
        org_enc  = urllib.parse.quote(origin)      if origin      else ""
        dest_enc = urllib.parse.quote(destination)
        if origin:
            url = f"https://www.google.com/maps/dir/{org_enc}/{dest_enc}"
            msg = f"Abriendo ruta de '{origin}' a '{destination}' en Google Maps."
        else:
            url = f"https://www.google.com/maps/dir//{dest_enc}"
            msg = f"Abriendo ruta hacia '{destination}' (desde tu ubicación actual) en Google Maps."
        webbrowser.open(url)

    # ── NEGOCIOS CERCANOS ────────────────────────────────────────────────────
    elif action in ("nearby", "cerca", "cercano"):
        search_term = (category + " cerca de " + query) if query else category
        if not search_term:
            return "Error: Especifica qué buscar ('category') o dónde ('query')."
        url = "https://www.google.com/maps/search/" + urllib.parse.quote(search_term)
        webbrowser.open(url)
        msg = f"Buscando '{search_term}' en Google Maps."

    # ── STREET VIEW ──────────────────────────────────────────────────────────
    elif action in ("street_view", "street view"):
        search_term = query or destination
        if not search_term:
            return "Error: Falta la dirección para Street View."
        url = "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + urllib.parse.quote(search_term)
        webbrowser.open(url)
        msg = f"Abriendo Street View para '{search_term}'."

    else:
        # Fallback: tratar cualquier otra acción como búsqueda general
        search_term = query or destination or origin or action
        url = "https://www.google.com/maps/search/" + urllib.parse.quote(search_term)
        webbrowser.open(url)
        msg = f"Buscando '{search_term}' en Google Maps."

    if player:
        try: player.write_log(f"🗺️ {msg}")
        except: pass
    return msg
