import math
import re
from urllib.parse import parse_qs, urlparse


def get_video_id_from_url(video_url):
    if not isinstance(video_url, str):
        return None
    try:
        parsed = urlparse(video_url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip('/').split('/')
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if parts == ["watch"]:
            return parse_qs(parsed.query).get('v', [None])[0]
        if len(parts) == 2 and parts[0] in ("shorts", "embed", "live"):
            return parts[1] or None
    elif host in ("youtu.be", "www.youtu.be") and len(parts) == 1:
        return parts[0] or None
    elif host in ("twitch.tv", "www.twitch.tv", "m.twitch.tv"):
        if len(parts) == 2 and parts[0] == "videos" and parts[1].isdigit():
            return "v" + parts[1]
        if len(parts) == 3 and parts[1] == "clip":
            return parts[2] or None
    elif host == "clips.twitch.tv" and len(parts) == 1:
        return parts[0] or None
    return None


def extract_game_id_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("speedrun.com", "www.speedrun.com"):
        raise ValueError(f"URL de jeu invalide : {url}")
    parts = [part for part in parsed.path.split('/') if part]
    if parts and re.fullmatch(r'[a-z]{2}-[A-Z]{2}', parts[0]):
        parts.pop(0)
    if len(parts) != 1:
        raise ValueError(f"L'URL doit désigner un jeu : {url}")
    return parts[0]


def safe_filename(filename):
    cleaned = re.sub(r'[\x00-\x1f\\/*?:"<>|]', '', filename).rstrip(' .')
    cleaned = cleaned[:100].rstrip(' .') or 'video'
    if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', cleaned):
        cleaned = '_' + cleaned
    return cleaned


def format_duration(seconds):
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("La durée doit être positive et finie.")
    milliseconds = round(seconds * 1000)
    minutes, remainder = divmod(milliseconds, 60000)
    whole_seconds, fraction = divmod(remainder, 1000)
    hours, minutes = divmod(minutes, 60)
    prefix = f"{hours}:{minutes:02d}" if hours else str(minutes)
    return f"{prefix}:{whole_seconds:02d}.{fraction:03d}"
