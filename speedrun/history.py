import json
import os
import tempfile
from pathlib import Path

from .models import Run
from .utils import get_video_id_from_url


def load_history(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        history = json.load(file)
    if not isinstance(history, dict):
        raise ValueError(f"Historique invalide : {path}")
    for categories in history.values():
        if not isinstance(categories, dict):
            raise ValueError(f"Catégories invalides dans l'historique : {path}")
        for videos in categories.values():
            if not isinstance(videos, list) or any(
                video is not None and not isinstance(video, str) for video in videos
            ):
                raise ValueError(f"Identifiants vidéo invalides dans l'historique : {path}")
    return history


def is_used(history: dict, run: Run) -> bool:
    video_id = get_video_id_from_url(run.video_url)
    return bool(video_id) and video_id in history.get(run.game_id, {}).get(run.category_id, [])


def record_run(path: Path, run: Run) -> None:
    video_id = get_video_id_from_url(run.video_url)
    if not video_id:
        raise ValueError("Impossible d'enregistrer une vidéo sans identifiant pris en charge.")
    history = load_history(path)
    if is_used(history, run):
        return
    history.setdefault(run.game_id, {}).setdefault(run.category_id, []).append(video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as file:
            temporary_path = Path(file.name)
            json.dump(history, file, ensure_ascii=False, indent=4)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
