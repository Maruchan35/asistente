"""tiktok_analyzer.py — TikTok content analyzer via web scraping.
Fetches public video info, user stats, and trending content via TikTok's web API."""
from __future__ import annotations
import json, re, time, urllib.parse, urllib.request, urllib.error, webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.tiktok.com/",
}

def _get(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

def _extract_json_from_script(html: str, key: str = "SIGI_STATE") -> dict | None:
    """Extract embedded JSON from TikTok's __UNIVERSAL_DATA__ script tag."""
    # TikTok embeds data as __UNIVERSAL_DATA__ in <script> tags
    patterns = [
        rf'<script id="{key}" type="application/json">([^<]+)</script>',
        r'<script[^>]*>\s*window\.__UNIVERSAL_DATA__\s*=\s*(\{.+?\})\s*</script>',
        r'"ItemModule"\s*:\s*(\{.+?"stats":\{.+?\}\})',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None

def _ai(prompt: str) -> str:
    try:
        from actions.openrouter_agent import openrouter_agent
        return openrouter_agent(prompt)
    except Exception as e:
        return f"[AI no disponible: {e}]"

def _format_number(n: int | str) -> str:
    try:
        n = int(n)
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)
    except Exception:
        return str(n)

# ══════════════════════════════════════════════════════════════════════════════
def tiktok_analyzer(parameters: dict, player=None) -> str:
    action   = parameters.get("action", "analyze").lower().strip()
    url      = parameters.get("url", "").strip()
    username = parameters.get("username", parameters.get("user", "")).strip().lstrip("@")
    hashtag  = parameters.get("hashtag", parameters.get("tag", "")).strip().lstrip("#")
    query    = parameters.get("query", parameters.get("search", "")).strip()
    count    = int(parameters.get("count", 5))

    def log(msg: str):
        if player:
            player.write_log(f"🎵 TikTok: {msg}")

    # ── ANALYZE VIDEO ─────────────────────────────────────────────────────────
    if action in ("analyze", "video", "analizar_video"):
        if not url:
            return "Especificá url con el link del video de TikTok."
        if "tiktok.com" not in url:
            return "La URL no parece ser de TikTok."

        log(f"Analizando video: {url}")
        html = _get(url)

        if "Error" in html or "HTTP" in html:
            log(f"Error accediendo al video: {html[:100]}")
            # Fallback: open in browser for manual inspection
            webbrowser.open(url)
            return (f"No pude acceder automáticamente al video. "
                    f"Abrí el link en el navegador: {url}")

        # Try to extract video metadata from page
        # TikTok embeds OG meta tags
        title_m    = re.search(r'<title>([^<]+)</title>', html)
        desc_m     = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html)
        views_m    = re.search(r'"playCount"\s*:\s*(\d+)', html)
        likes_m    = re.search(r'"diggCount"\s*:\s*(\d+)', html)
        comments_m = re.search(r'"commentCount"\s*:\s*(\d+)', html)
        shares_m   = re.search(r'"shareCount"\s*:\s*(\d+)', html)
        author_m   = re.search(r'"uniqueId"\s*:\s*"([^"]+)"', html)
        music_m    = re.search(r'"musicName"\s*:\s*"([^"]+)"', html)
        duration_m = re.search(r'"duration"\s*:\s*(\d+)', html)
        tags_m     = re.findall(r'#(\w+)', html[:5000])

        title    = title_m.group(1).strip() if title_m else "Título no disponible"
        desc     = desc_m.group(1).strip()[:200] if desc_m else ""
        views    = _format_number(views_m.group(1)) if views_m else "?"
        likes    = _format_number(likes_m.group(1)) if likes_m else "?"
        comments = _format_number(comments_m.group(1)) if comments_m else "?"
        shares   = _format_number(shares_m.group(1)) if shares_m else "?"
        author   = f"@{author_m.group(1)}" if author_m else "?"
        music    = music_m.group(1) if music_m else "?"
        duration = f"{int(duration_m.group(1))}s" if duration_m else "?"
        tags_str = " ".join(f"#{t}" for t in list(dict.fromkeys(tags_m))[:8]) if tags_m else ""

        result = (f"TikTok Video\n"
                  f"  Título: {title[:100]}\n"
                  f"  Autor: {author}\n"
                  f"  Duración: {duration}\n"
                  f"  Música: {music}\n"
                  f"  📊 Vistas: {views} | Likes: {likes} | Comentarios: {comments} | Shares: {shares}\n"
                  + (f"  Tags: {tags_str}\n" if tags_str else "")
                  + (f"  Descripción: {desc}" if desc else ""))

        # AI content analysis from description
        if desc or tags_str:
            ai_prompt = (f"Analizá este video de TikTok basándote en la metadata:\n"
                         f"Título: {title}\nDescripción: {desc}\nTags: {tags_str}\n"
                         f"Métricas: {views} vistas, {likes} likes\n\n"
                         f"Analizá: ¿sobre qué trata?, ¿por qué funciona o no?, "
                         f"¿qué tipo de audiencia tiene?")
            ai_result = _ai(ai_prompt)
            result += f"\n\n{ai_result}"

        log(f"Video analizado: {views} vistas")
        return result

    # ── USER PROFILE ─────────────────────────────────────────────────────────
    elif action in ("user", "profile", "perfil", "usuario"):
        if not username:
            return "Especificá username con el usuario de TikTok."

        log(f"Analizando perfil: @{username}")
        profile_url = f"https://www.tiktok.com/@{username}"
        html = _get(profile_url)

        if "Error" in html or "HTTP" in html:
            webbrowser.open(profile_url)
            return f"Abrí el perfil en el navegador: {profile_url}"

        # Extract profile stats
        followers_m = re.search(r'"followerCount"\s*:\s*(\d+)', html)
        following_m = re.search(r'"followingCount"\s*:\s*(\d+)', html)
        likes_m     = re.search(r'"heartCount"\s*:\s*(\d+)', html)
        videos_m    = re.search(r'"videoCount"\s*:\s*(\d+)', html)
        bio_m       = re.search(r'"signature"\s*:\s*"([^"]+)"', html)
        nick_m      = re.search(r'"nickname"\s*:\s*"([^"]+)"', html)
        verified_m  = re.search(r'"verified"\s*:\s*(true|false)', html)

        followers = _format_number(followers_m.group(1)) if followers_m else "?"
        following = _format_number(following_m.group(1)) if following_m else "?"
        likes     = _format_number(likes_m.group(1)) if likes_m else "?"
        videos    = videos_m.group(1) if videos_m else "?"
        bio       = bio_m.group(1)[:150] if bio_m else ""
        nickname  = nick_m.group(1) if nick_m else username
        verified  = "✓ Verificado" if (verified_m and verified_m.group(1) == "true") else ""

        result = (f"Perfil TikTok: @{username} {verified}\n"
                  f"  Nombre: {nickname}\n"
                  f"  Seguidores: {followers}\n"
                  f"  Siguiendo: {following}\n"
                  f"  Likes totales: {likes}\n"
                  f"  Videos: {videos}\n"
                  + (f"  Bio: {bio}" if bio else ""))

        if bio or nickname:
            ai_prompt = (f"Analizá el perfil de TikTok de @{username}:\n"
                         f"Seguidores: {followers}, Videos: {videos}, Likes: {likes}\n"
                         f"Bio: {bio}\n"
                         f"¿Qué tipo de creador es? ¿Cuál es su nicho?")
            result += f"\n\n{_ai(ai_prompt)}"

        log(f"Perfil: @{username} — {followers} seguidores")
        return result

    # ── TRENDING ─────────────────────────────────────────────────────────────
    elif action in ("trending", "tendencias"):
        log("Buscando tendencias...")
        # TikTok trending via web
        trend_url = "https://www.tiktok.com/trending"
        webbrowser.open(trend_url)

        # Also get trending hashtags via public API endpoint
        api_url = "https://www.tiktok.com/api/recommend/item_list/?count=20&id=1&type=5&secUid=&maxCursor=0&minCursor=0&sourceType=12&appId=1233"
        html = _get(api_url)

        # Try to extract trending info from TikTok Discover
        discover_url = "https://www.tiktok.com/discover"
        html2 = _get(discover_url)
        hashtags = re.findall(r'#(\w+)', html2[:5000])
        if hashtags:
            unique_tags = list(dict.fromkeys(hashtags))[:10]
            tags_str = " ".join(f"#{t}" for t in unique_tags)
            return (f"Tendencias de TikTok (página abierta en navegador).\n"
                    f"Hashtags detectados: {tags_str}")
        return "Página de tendencias de TikTok abierta en el navegador."

    # ── SEARCH HASHTAG ────────────────────────────────────────────────────────
    elif action in ("hashtag", "tag", "buscar_hashtag"):
        if not hashtag:
            return "Especificá hashtag para analizar."
        log(f"Analizando hashtag: #{hashtag}")
        tag_url = f"https://www.tiktok.com/tag/{hashtag}"
        html = _get(tag_url)

        views_m = re.search(r'"viewCount"\s*:\s*(\d+)', html)
        videos_m = re.search(r'"videoCount"\s*:\s*(\d+)', html)
        desc_m = re.search(r'"desc"\s*:\s*"([^"]+)"', html)

        views  = _format_number(views_m.group(1)) if views_m else "?"
        videos = videos_m.group(1) if videos_m else "?"

        # Open in browser too
        webbrowser.open(tag_url)
        result = (f"Hashtag #{hashtag}:\n"
                  f"  Vistas totales: {views}\n"
                  f"  Videos: {videos}\n"
                  f"  Link: {tag_url}")

        ai_prompt = (f"El hashtag #{hashtag} en TikTok tiene {views} vistas y {videos} videos. "
                     f"¿Qué tipo de contenido se suele publicar con este hashtag? "
                     f"¿Es un hashtag de nicho o masivo?")
        result += f"\n\n{_ai(ai_prompt)}"
        log(f"#{hashtag}: {views} vistas")
        return result

    # ── SEARCH ────────────────────────────────────────────────────────────────
    elif action in ("search", "buscar"):
        if not query:
            return "Especificá query para buscar en TikTok."
        search_url = f"https://www.tiktok.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(search_url)
        log(f"Búsqueda: {query}")
        return f"Resultados de TikTok para '{query}' abiertos en el navegador."

    # ── OPEN ─────────────────────────────────────────────────────────────────
    elif action in ("open", "abrir"):
        target_url = url or (f"https://www.tiktok.com/@{username}" if username else "https://www.tiktok.com")
        webbrowser.open(target_url)
        return f"TikTok abierto: {target_url}"

    return (f"Acción '{action}' no reconocida. "
            "Usa: analyze | user | trending | hashtag | search | open")
