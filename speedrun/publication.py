from dataclasses import asdict
import json
import math
from pathlib import Path

from .models import Run
from .utils import format_duration


def write_publication_files(run, folder, segments, render_spec):
    folder = Path(folder)
    metadata = {
        "run": asdict(run), "segments": [Path(path).name for path in segments], "render": render_spec
    }
    (folder / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    description = (
        f"{run.game_name} — {run.category_name}\n"
        f"{run.player_name} | {format_duration(run.duration)} | #{run.rank}\n"
        f"Date du run : {run.date}\n\n"
        f"Run et classement : {run.run_link}\n"
        f"Vidéo originale : {run.video_url}\n"
        f"Profil du joueur : {run.player_profile_link or 'Joueur invité'}\n\n"
        "#speedrun #gaming #shorts\n"
    )
    (folder / "description.txt").write_text(description, encoding="utf-8")


def load_run_metadata(path):
    metadata = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or not isinstance(metadata.get("run"), dict):
        raise ValueError("Le fichier metadata.json doit contenir un objet 'run'.")
    run = Run(**metadata["run"])
    for field in (
        "run_id", "game_id", "category_id", "game_name", "category_name", "player_name",
        "country", "date", "video_url", "run_link", "player_profile_link"
    ):
        if not isinstance(getattr(run, field), str):
            raise ValueError(f"Métadonnée invalide : {field}")
    if not run.run_id or type(run.rank) is not int or run.rank < 1:
        raise ValueError("Identifiant ou classement du run invalide.")
    if type(run.duration) not in (int, float) or not math.isfinite(run.duration) or run.duration <= 0:
        raise ValueError("Durée officielle du run invalide.")
    return run
