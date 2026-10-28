from functools import partial
import math
from pathlib import Path
import shutil

import yt_dlp

from .config import Settings
from .utils import get_video_id_from_url


def _reject_video(info: dict, *, incomplete: bool = False, max_duration: float | None = None) -> str | None:
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        return "Les directs et les vidéos à venir ne sont pas pris en charge."
    if info.get("_type") in ("playlist", "multi_video"):
        return "Une seule vidéo est attendue."
    duration = info.get("duration")
    if duration is None and incomplete:
        return None
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        return "La durée de la vidéo doit être positive et finie."
    if max_duration is not None and duration > max_duration:
        return f"La vidéo source dépasse la limite de {max_duration:g} secondes."
    return None


def download_video(video_url: str, settings: Settings) -> Path:
    if not get_video_id_from_url(video_url):
        raise ValueError("Seules les vidéos YouTube et Twitch identifiables sont prises en charge.")
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    max_duration = settings.max_duration + 120
    options = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/best",
        "merge_output_format": "mkv",
        "outtmpl": str(settings.download_dir / "%(extractor_key)s-%(id)s.%(ext)s"),
        "noplaylist": True,
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "socket_timeout": 30,
        "match_filter": partial(_reject_video, max_duration=max_duration),
    }
    ffmpeg = shutil.which(settings.ffmpeg)
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    node = shutil.which("node")
    if node:
        options["js_runtimes"] = {"deno": {}, "node": {"path": node}}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(video_url, download=True)
            if not isinstance(info, dict):
                raise ValueError("Aucune vidéo disponible après le téléchargement.")
            rejection = _reject_video(info, max_duration=max_duration)
            if rejection:
                raise ValueError(rejection)
            paths = [
                item.get("filepath")
                for item in info.get("requested_downloads") or []
                if isinstance(item, dict)
            ]
            paths.extend((info.get("filepath"), downloader.prepare_filename(info)))
            for filename in paths:
                if filename:
                    path = Path(filename)
                    if path.is_file() and path.stat().st_size > 0:
                        return path.resolve()
    except yt_dlp.utils.DownloadError as error:
        raise RuntimeError(f"Téléchargement impossible : {error}") from error
    raise FileNotFoundError("Le fichier vidéo téléchargé ou fusionné est introuvable.")
