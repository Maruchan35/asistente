"""spotify_control.py - Smart Spotify controller using Spotipy API and fallback."""
import time
import os

def spotify_control(parameters: dict, player=None) -> str:
    """Control Spotify playback, search, and queueing using Spotipy (if authenticated) or OS fallbacks."""
    action = parameters.get("action", "").lower().strip()
    query = parameters.get("query", parameters.get("song", parameters.get("artist", "")))
    
    if not action:
        # Default to play if there's a query
        if query:
            action = "play"
        else:
            return "Action parameter is required."

    msg = ""
    # Try using Spotipy first if credentials exist
    try:
        from memory.config_manager import load_api_keys
        cfg = load_api_keys()
        token = cfg.get("spotify_token_info", {}).get("access_token")
        
        if token:
            import spotipy
            sp = spotipy.Spotify(auth=token)
            
            if action in ("play", "reproduce"):
                if query:
                    results = sp.search(q=query, limit=1, type='track')
                    if results['tracks']['items']:
                        track = results['tracks']['items'][0]
                        track_uri = track['uri']
                        track_name = track['name']
                        artist_name = track['artists'][0]['name']
                        
                        devices = sp.devices()
                        if devices and devices['devices']:
                            # Try to play on active device
                            sp.start_playback(uris=[track_uri])
                            msg = f"Reproduciendo '{track_name}' de {artist_name} vía API."
                        else:
                            # If no active devices, launch Spotify with the URI
                            os.startfile(track_uri)
                            msg = f"Abriendo '{track_name}' de {artist_name} en Spotify local."
                    else:
                        msg = f"No encontré resultados para '{query}' en Spotify."
                else:
                    sp.start_playback()
                    msg = "Reproducción reanudada."
                    
            elif action == "pause":
                sp.pause_playback()
                msg = "Música en pausa."
            elif action in ("next", "skip"):
                sp.next_track()
                msg = "Siguiente canción."
            elif action in ("prev", "previous", "back"):
                sp.previous_track()
                msg = "Canción anterior."
            elif action in ("search", "buscar"):
                # Search and display results, then play the first one
                if query:
                    results = sp.search(q=query, limit=5, type='track,artist,album')
                    tracks = results.get('tracks', {}).get('items', [])
                    if tracks:
                        names = [f"{t['name']} — {t['artists'][0]['name']}" for t in tracks[:3]]
                        # Auto-play the first result
                        sp.start_playback(uris=[tracks[0]['uri']])
                        msg = f"Encontré: {', '.join(names)}. Reproduciendo el primero."
                    else:
                        msg = f"Sin resultados para '{query}'."
                else:
                    msg = "Necesito qué buscar en Spotify."

            elif action in ("devices", "dispositivos"):
                devices_list = sp.devices()
                devs = devices_list.get('devices', [])
                if devs:
                    names = [f"{d['name']} ({'activo' if d['is_active'] else 'inactivo'})"
                             for d in devs]
                    msg = "Dispositivos Spotify: " + ", ".join(names) + "."
                else:
                    msg = "No hay dispositivos Spotify activos. Abre la app primero."

            elif action == "volume":
                # Spotify API doesn't allow volume set without Premium + active device
                # Fall through to pyautogui fallback
                msg = ""  # will be handled below

            if msg:
                if player:
                    player.write_log(f"🎵 Spotify: {msg}")
                return msg
    except Exception as e:
        print(f"[Spotify API Error] {e}")
        pass # Fallback to local pyautogui/os commands

    # --- FALLBACK: Local OS Control ---
    try:
        import pyautogui
        
        if action in ("play", "reproduce"):
            if query:
                import urllib.parse
                safe_query = urllib.parse.quote(query)
                os.startfile(f"spotify:search:{safe_query}")
                msg = f"Buscando '{query}' en Spotify..."
                # No podemos presionar Enter de forma confiable porque Spotify tarda en cargar.
                # Dejaremos que el usuario le de clic, o usaremos un pequeño truco:
                time.sleep(2.5)
                # Tab twice and enter sometimes works to play the first result
                pyautogui.press('tab', presses=2, interval=0.1)
                pyautogui.press('enter')
            else:
                pyautogui.press("playpause")
                msg = "Media playback toggled."
                
        elif action == "pause":
            pyautogui.press("playpause")
            msg = "Media playback toggled."
            
        elif action in ("next", "skip"):
            pyautogui.press("nexttrack")
            msg = "Skipped to next track."
            
        elif action in ("prev", "previous", "back"):
            pyautogui.press("prevtrack")
            msg = "Returned to previous track."
            
        elif action in ("search", "buscar"):
            if query:
                import urllib.parse
                safe_query = urllib.parse.quote(query)
                os.startfile(f"spotify:search:{safe_query}")
                msg = f"Buscando '{query}' en Spotify."
            else:
                msg = "Necesito qué buscar en Spotify."

        elif action in ("devices", "dispositivos"):
            msg = "No hay conexión API activa. Abre Spotify manualmente para ver dispositivos."

        elif action == "volume":
            value = str(parameters.get("value", "")).lower()
            if "up" in value:
                pyautogui.press("volumeup", presses=5)
                msg = "Volume increased."
            elif "down" in value:
                pyautogui.press("volumedown", presses=5)
                msg = "Volume decreased."
            else:
                msg = f"Volume adjust requires relative direction: {value}"
        else:
            msg = f"Action '{action}' not recognized, sir."
            
        if player:
            player.write_log(f"🎵 Spotify (Local): {msg}")
        return msg
        
    except Exception as e:
        return f"Error executing media control action: {e}"
