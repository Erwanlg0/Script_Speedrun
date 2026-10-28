from datetime import date
import logging
from pathlib import Path
import random

from .api import SpeedrunClient
from .download import download_video
from .history import load_history, record_run
from .policy import load_game_rules, settings_for_game
from .render import probe_video, process_video
from .utils import extract_game_id_from_url, format_duration, get_video_id_from_url


logger = logging.getLogger(__name__)


def read_game_ids(path):
    game_ids = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            game_id = extract_game_id_from_url(line)
            if game_id not in game_ids:
                game_ids.append(game_id)
    return game_ids


def rank_runs(runs, settings):
    def priority(run):
        try:
            day = date.fromisoformat(run.date).toordinal()
        except ValueError:
            day = 0
        return run.rank, run.duration > settings.segment_duration, -day, run.duration

    return sorted(runs, key=priority)


def run_batch(settings, list_only=False):
    history = load_history(settings.history_file)
    rules = load_game_rules(settings.game_rules_file)
    game_ids = read_game_ids(settings.game_urls_file)
    random.shuffle(game_ids)
    selected = []
    seen_videos = {
        video_id for categories in history.values() for videos in categories.values()
        for video_id in videos if video_id is not None
    }
    failures = 0
    with SpeedrunClient() as client:
        for game_id in game_ids:
            try:
                game_settings = settings_for_game(settings, game_id, rules)
                candidates = rank_runs(client.find_runs(game_id, game_settings), game_settings)
            except (ValueError, RuntimeError) as error:
                logger.warning("Jeu %s ignoré : %s", game_id, error)
                continue
            for run in candidates:
                video_id = get_video_id_from_url(run.video_url)
                if video_id in seen_videos:
                    continue
                seen_videos.add(video_id)
                logger.info(
                    "#%s · %s · %s · %s · %s",
                    run.rank, run.game_name, run.category_name, run.player_name,
                    format_duration(run.duration)
                )
                if list_only:
                    print(f"{run.run_link}\n{run.video_url}")
                    selected.append(run)
                else:
                    try:
                        source = download_video(run.video_url, game_settings)
                        source_info = probe_video(source, game_settings)
                        if not run.duration - 2 <= source_info["duration"] <= run.duration + 120:
                            failures += 1
                            logger.warning(
                                "Vidéo %s ignorée : durée source %.1fs incompatible avec le run %.1fs.",
                                run.run_id, source_info["duration"], run.duration
                            )
                            continue
                        output = process_video(source, run, game_settings)
                        record_run(settings.history_file, run)
                        selected.append(run)
                        logger.info("Export terminé : %s", output)
                    except (OSError, ValueError, RuntimeError) as error:
                        failures += 1
                        logger.warning("Run %s ignoré : %s", run.run_id, error)
                if len(selected) >= settings.max_videos:
                    return selected
    if not selected and failures:
        raise RuntimeError(f"Aucun run exporté : {failures} échec(s) de téléchargement ou de traitement.")
    return selected
