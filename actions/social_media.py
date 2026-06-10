"""social_media.py — Social media automation for Twitter/X, Instagram, TikTok, LinkedIn.
Twitter via Tweepy API.
Instagram via Instagrapi (if installed) or browser automation.
TikTok / LinkedIn via browser automation (webbrowser + pyautogui).
"""
from __future__ import annotations
import json, os, subprocess, time, webbrowser
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent
KEYS_FILE = BASE_DIR / "config" / "api_keys.json"

def _load_keys() -> dict:
    try: return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except: return {}

def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return str(e)

# ══════════════════════════════════════════════════════════════════════════════
# ── TWITTER / X ───────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
def _twitter(action: str, params: dict, keys: dict) -> str:
    bearer   = keys.get("twitter_bearer_token", "").strip()
    api_key  = keys.get("twitter_api_key", keys.get("twitter_consumer_key","")).strip()
    api_sec  = keys.get("twitter_api_secret", keys.get("twitter_consumer_secret","")).strip()
    acc_tok  = keys.get("twitter_access_token", "").strip()
    acc_sec  = keys.get("twitter_access_secret", "").strip()

    text     = params.get("text", "")
    query    = params.get("query", "")
    tweet_id = params.get("tweet_id", "")
    count    = int(params.get("count", 5))

    # ── Setup info ────────────────────────────────────────────────────────────
    if action == "setup":
        return ("Para Twitter necesitás:\n"
                "1. Ir a developer.twitter.com y crear una app\n"
                "2. Agregar en config/api_keys.json:\n"
                "   - twitter_bearer_token\n"
                "   - twitter_api_key + twitter_api_secret\n"
                "   - twitter_access_token + twitter_access_secret")

    # ── Needs tweepy ──────────────────────────────────────────────────────────
    try:
        import tweepy
    except ImportError:
        return ("Tweepy no instalado. Ejecutá: pip install tweepy\n"
                "Luego configurá tus credenciales de Twitter en config/api_keys.json")

    if not api_key:
        return ("Twitter no configurado. Usá action=setup para ver cómo configurarlo.\n"
                "Alternativamente, podés abrir Twitter manualmente: twitter.com")

    # Build auth
    try:
        auth = tweepy.OAuth1UserHandler(api_key, api_sec, acc_tok, acc_sec)
        api  = tweepy.API(auth, wait_on_rate_limit=True)
    except Exception as e:
        return f"Error de autenticación Twitter: {e}"

    # ── TWEET ─────────────────────────────────────────────────────────────────
    if action in ("tweet", "publicar", "post"):
        if not text:
            return "Necesito el texto del tweet."
        if len(text) > 280:
            return f"El tweet tiene {len(text)} caracteres. El límite es 280."
        try:
            status = api.update_status(text)
            return f"Tweet publicado (ID: {status.id}): '{text[:80]}'"
        except tweepy.errors.Forbidden as e:
            return f"Error publicando tweet: {e}"

    # ── DELETE TWEET ──────────────────────────────────────────────────────────
    elif action in ("delete_tweet", "borrar_tweet"):
        if not tweet_id:
            return "Necesito el tweet_id para eliminar."
        try:
            api.destroy_status(id=tweet_id)
            return f"Tweet {tweet_id} eliminado."
        except Exception as e:
            return f"Error: {e}"

    # ── LIKE ─────────────────────────────────────────────────────────────────
    elif action in ("like", "dar_like"):
        if not tweet_id:
            return "Necesito el tweet_id para dar like."
        try:
            api.create_favorite(tweet_id)
            return f"Like dado al tweet {tweet_id}."
        except Exception as e:
            return f"Error: {e}"

    # ── RETWEET ───────────────────────────────────────────────────────────────
    elif action in ("retweet", "retweetear"):
        if not tweet_id:
            return "Necesito el tweet_id para retweetear."
        try:
            api.retweet(tweet_id)
            return f"Tweet {tweet_id} retwiteado."
        except Exception as e:
            return f"Error: {e}"

    # ── TIMELINE ─────────────────────────────────────────────────────────────
    elif action in ("timeline", "feed"):
        try:
            tweets = api.home_timeline(count=count)
            lines = [f"Timeline de Twitter ({len(tweets)} tweets):"]
            for t in tweets:
                lines.append(f"  @{t.user.screen_name}: {t.text[:100]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # ── SEARCH ────────────────────────────────────────────────────────────────
    elif action in ("search", "buscar", "search_tweets"):
        if not query:
            return "Necesito un término de búsqueda."
        try:
            tweets = api.search_tweets(q=query, count=count, lang="es")
            lines = [f"Resultados para '{query}':"]
            for t in tweets:
                lines.append(f"  @{t.user.screen_name}: {t.text[:100]}")
            return "\n".join(lines) if len(lines) > 1 else f"No se encontraron tweets sobre '{query}'."
        except Exception as e:
            return f"Error: {e}"

    # ── MY TWEETS ────────────────────────────────────────────────────────────
    elif action in ("my_tweets", "mis_tweets"):
        try:
            me = api.verify_credentials()
            tweets = api.user_timeline(user_id=me.id, count=count)
            lines = [f"Tus últimos {len(tweets)} tweets:"]
            for t in tweets:
                lines.append(f"  [{t.id}] {t.text[:100]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # ── PROFILE ──────────────────────────────────────────────────────────────
    elif action in ("profile", "perfil"):
        try:
            me = api.verify_credentials()
            return (f"Twitter: @{me.screen_name}\n"
                    f"Nombre: {me.name}\n"
                    f"Seguidores: {me.followers_count}\n"
                    f"Siguiendo: {me.friends_count}\n"
                    f"Tweets: {me.statuses_count}")
        except Exception as e:
            return f"Error: {e}"

    return f"Acción Twitter '{action}' no reconocida."

# ══════════════════════════════════════════════════════════════════════════════
# ── INSTAGRAM ─────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
def _instagram(action: str, params: dict, keys: dict) -> str:
    ig_user = keys.get("instagram_username", "").strip()
    ig_pass = keys.get("instagram_password", "").strip()
    caption = params.get("caption", params.get("text", ""))
    image_p = params.get("image_path", "")
    receiver= params.get("receiver", params.get("username", ""))
    text    = params.get("text", "")
    count   = int(params.get("count", 5))

    if action == "setup":
        return ("Para Instagram necesitás:\n"
                "1. Agregar en config/api_keys.json:\n"
                "   - instagram_username (tu usuario)\n"
                "   - instagram_password (tu contraseña)\n"
                "2. pip install instagrapi\n"
                "Nota: Instagram bloquea bots agresivos. Usar con moderación.")

    try:
        from instagrapi import Client as InstaClient
    except ImportError:
        # Fallback: browser
        if action in ("post", "upload_photo", "upload"):
            webbrowser.open("https://www.instagram.com/create/style/")
            return "Instagrapi no instalado. Abrí Instagram en el navegador para subir la foto.\npip install instagrapi para automatización completa."
        webbrowser.open("https://www.instagram.com")
        return "Instagrapi no instalado (pip install instagrapi). Abrí Instagram en el navegador."

    if not ig_user:
        return ("Instagram no configurado. Usá action=setup para ver instrucciones.\n"
                "O abrí Instagram en: instagram.com")

    # ── Login (cached) ────────────────────────────────────────────────────────
    session_file = BASE_DIR / "config" / "instagram_session.json"
    cl = InstaClient()
    cl.delay_range = [1, 3]  # Avoid rate limiting

    try:
        if session_file.exists():
            cl.load_settings(str(session_file))
            cl.login(ig_user, ig_pass)
        else:
            cl.login(ig_user, ig_pass)
            cl.dump_settings(str(session_file))
    except Exception as e:
        return f"Error de login en Instagram: {e}"

    # ── POST PHOTO ────────────────────────────────────────────────────────────
    if action in ("post", "upload_photo", "upload"):
        if not image_p or not Path(image_p).exists():
            return f"Imagen no encontrada: '{image_p}'. Especificá image_path con la ruta de la imagen."
        try:
            media = cl.photo_upload(image_p, caption=caption or "")
            return f"Foto publicada en Instagram. Media ID: {media.pk}"
        except Exception as e:
            return f"Error publicando foto: {e}"

    # ── STORY ────────────────────────────────────────────────────────────────
    elif action in ("story", "historia"):
        if not image_p or not Path(image_p).exists():
            return f"Imagen no encontrada: '{image_p}'."
        try:
            media = cl.photo_upload_to_story(image_p)
            return f"Historia publicada en Instagram."
        except Exception as e:
            return f"Error publicando historia: {e}"

    # ── SEND DM ───────────────────────────────────────────────────────────────
    elif action in ("send_dm", "dm", "mensaje", "direct"):
        if not receiver: return "Necesito el receiver (usuario de Instagram)."
        if not text:     return "Necesito el texto del mensaje."
        try:
            user_id = cl.user_id_from_username(receiver)
            cl.direct_send(text, [user_id])
            return f"Mensaje enviado a @{receiver} en Instagram."
        except Exception as e:
            return f"Error enviando DM: {e}"

    # ── FEED ─────────────────────────────────────────────────────────────────
    elif action in ("feed", "timeline"):
        try:
            items = cl.get_timeline_feed().get("feed_items", [])[:count]
            lines = [f"Feed de Instagram ({len(items)} posts):"]
            for item in items:
                media = item.get("media_or_ad", {})
                user  = media.get("user", {}).get("username", "?")
                cap   = media.get("caption", {})
                cap_text = cap.get("text","")[:80] if isinstance(cap, dict) else ""
                lines.append(f"  @{user}: {cap_text}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error leyendo feed: {e}"

    # ── LIKE ─────────────────────────────────────────────────────────────────
    elif action == "like":
        media_id = params.get("media_id", "")
        if not media_id: return "Necesito el media_id para dar like."
        try:
            cl.media_like(media_id)
            return f"Like dado al post {media_id}."
        except Exception as e:
            return f"Error: {e}"

    # ── PROFILE ──────────────────────────────────────────────────────────────
    elif action in ("profile", "perfil"):
        try:
            user = cl.user_info_by_username(receiver or ig_user)
            return (f"Instagram: @{user.username}\n"
                    f"Nombre: {user.full_name}\n"
                    f"Seguidores: {user.follower_count}\n"
                    f"Siguiendo: {user.following_count}\n"
                    f"Posts: {user.media_count}")
        except Exception as e:
            return f"Error: {e}"

    return f"Acción Instagram '{action}' no reconocida."

# ══════════════════════════════════════════════════════════════════════════════
# ── TIKTOK ────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
def _tiktok(action: str, params: dict, keys: dict) -> str:
    video_path = params.get("video_path", "")
    caption    = params.get("caption", params.get("text", ""))
    username   = params.get("username", "")

    if action == "setup":
        return ("TikTok usa automatización de navegador.\n"
                "1. Abrí TikTok en Chrome/Edge y logueate\n"
                "2. JARVIS controlará el navegador vía pyautogui\n"
                "No se necesitan API keys para TikTok.")

    # ── UPLOAD ────────────────────────────────────────────────────────────────
    if action in ("upload", "publicar", "subir"):
        if not video_path or not Path(video_path).exists():
            webbrowser.open("https://www.tiktok.com/upload")
            return f"Video no encontrado. Abrí TikTok Upload en el navegador para subirlo manualmente."
        # Open TikTok upload page
        webbrowser.open("https://www.tiktok.com/upload")
        time.sleep(3)
        try:
            import pyautogui
            # Wait for page to load, then use file dialog
            time.sleep(2)
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.5)
            # This is a best-effort automation
            return (f"TikTok Upload abierto en el navegador.\n"
                    f"Video: {video_path}\n"
                    f"Caption sugerido: {caption}\n"
                    "La automatización completa de TikTok requiere Selenium con sesión activa.")
        except Exception:
            return f"Abrí TikTok en el navegador para subir: {video_path}"

    # ── PROFILE ──────────────────────────────────────────────────────────────
    elif action in ("profile", "perfil"):
        profile_url = f"https://www.tiktok.com/@{username}" if username else "https://www.tiktok.com/@me"
        webbrowser.open(profile_url)
        return f"Perfil de TikTok abierto en el navegador."

    # ── TRENDING ─────────────────────────────────────────────────────────────
    elif action in ("trending", "tendencias"):
        webbrowser.open("https://www.tiktok.com/trending")
        return "Tendencias de TikTok abiertas en el navegador."

    # Default: open TikTok
    webbrowser.open("https://www.tiktok.com")
    return "TikTok abierto en el navegador."

# ══════════════════════════════════════════════════════════════════════════════
# ── LINKEDIN ──────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
def _linkedin(action: str, params: dict, keys: dict) -> str:
    text     = params.get("text", params.get("content", ""))
    username = params.get("username", "")
    receiver = params.get("receiver", "")

    li_email = keys.get("linkedin_email", "").strip()
    li_pass  = keys.get("linkedin_password", "").strip()

    if action == "setup":
        return ("LinkedIn usa automatización de navegador.\n"
                "Opcional: agregar linkedin_email y linkedin_password en api_keys.json\n"
                "para automatización avanzada con Selenium.")

    # ── POST / SHARE ──────────────────────────────────────────────────────────
    if action in ("post", "publicar", "share"):
        if text:
            # Try to use clipboard for quick posting
            try:
                import pyperclip
                pyperclip.copy(text)
                webbrowser.open("https://www.linkedin.com/feed/")
                time.sleep(2)
                return (f"LinkedIn abierto. El texto fue copiado al portapapeles.\n"
                        f"Pegalo en el campo de publicación (Ctrl+V):\n'{text[:100]}'")
            except Exception:
                pass
        webbrowser.open("https://www.linkedin.com/feed/")
        return "LinkedIn abierto en el navegador para publicar."

    # ── PROFILE ──────────────────────────────────────────────────────────────
    elif action in ("profile", "perfil"):
        if username:
            webbrowser.open(f"https://www.linkedin.com/in/{username}/")
            return f"Perfil de LinkedIn de '{username}' abierto."
        webbrowser.open("https://www.linkedin.com/in/me/")
        return "Tu perfil de LinkedIn abierto en el navegador."

    # ── FEED ─────────────────────────────────────────────────────────────────
    elif action in ("feed", "inicio"):
        webbrowser.open("https://www.linkedin.com/feed/")
        return "Feed de LinkedIn abierto en el navegador."

    # ── MESSAGES ─────────────────────────────────────────────────────────────
    elif action in ("send_message", "mensaje", "dm"):
        if receiver:
            webbrowser.open(f"https://www.linkedin.com/messaging/compose/?recipients={receiver}")
        else:
            webbrowser.open("https://www.linkedin.com/messaging/")
        return f"Mensajes de LinkedIn abiertos{f' para {receiver}' if receiver else ''}."

    # Default
    webbrowser.open("https://www.linkedin.com")
    return "LinkedIn abierto en el navegador."

# ══════════════════════════════════════════════════════════════════════════════
def social_media(parameters: dict, player=None) -> str:
    platform = parameters.get("platform", "").lower().strip()
    action   = parameters.get("action", "").lower().strip()

    def log(msg):
        if player: player.write_log(f"📱 {msg}")

    if not platform:
        return ("Especificá la plataforma: twitter, instagram, tiktok o linkedin.\n"
                "Ej: platform=twitter, action=tweet, text='Hola mundo'")

    keys = _load_keys()

    if "twitter" in platform or platform == "x":
        log(f"Twitter: {action}")
        result = _twitter(action, parameters, keys)

    elif "instagram" in platform or platform == "ig":
        log(f"Instagram: {action}")
        result = _instagram(action, parameters, keys)

    elif "tiktok" in platform:
        log(f"TikTok: {action}")
        result = _tiktok(action, parameters, keys)

    elif "linkedin" in platform:
        log(f"LinkedIn: {action}")
        result = _linkedin(action, parameters, keys)

    elif platform == "setup":
        result = ("Configuración de redes sociales:\n\n"
                  "TWITTER: twitter_api_key, twitter_api_secret, twitter_access_token, twitter_access_secret\n"
                  "INSTAGRAM: instagram_username, instagram_password (+ pip install instagrapi)\n"
                  "TIKTOK: Solo automatización de navegador, no requiere config\n"
                  "LINKEDIN: Solo automatización de navegador (opcional: linkedin_email, linkedin_password)\n\n"
                  "Todos los valores van en config/api_keys.json")

    else:
        return (f"Plataforma '{platform}' no reconocida. "
                f"Disponibles: twitter, instagram, tiktok, linkedin")

    log(result[:100])
    return result
