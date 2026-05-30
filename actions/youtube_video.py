"""youtube_video.py — Clean YouTube video launching action."""
import webbrowser
import urllib.parse

def youtube_video(parameters: dict, response=None, player=None) -> str:
    """Search for and play a YouTube video in the default browser."""
    query = parameters.get("query", "").strip()
    if not query:
        return "Please specify what you would like to play on YouTube, sir."
        
    try:
        import urllib.request
        import re
        encoded_query = urllib.parse.quote(query)
        # Buscar en YouTube
        html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + encoded_query)
        video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
        
        if video_ids:
            url = f"https://www.youtube.com/watch?v={video_ids[0]}"
        else:
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        webbrowser.open(url)
        msg = f"Reproduciendo '{query}' en YouTube."
        if player:
            player.write_log(f"📺 {msg}")
        return msg
    except Exception as e:
        return f"Failed to play YouTube video: {e}"
