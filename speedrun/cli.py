import argparse
from dataclasses import replace
import logging
import math
from pathlib import Path
import shutil

from .app import run_batch
from .config import MAX_SEGMENT_DURATION, Settings
from .publication import load_run_metadata
from .render import process_video


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("La valeur doit être un entier positif.")
    return number


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("La valeur doit être positive et finie.")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Télécharger des speedruns vérifiés et produire des vidéos verticales avec crédits."
    )
    parser.add_argument("--max-videos", type=positive_int, default=3, help="Nombre de runs à exporter (défaut : 3).")
    parser.add_argument("--games", type=Path, help="Fichier des URLs de jeux.")
    parser.add_argument("--game-rules", type=Path, help="Règles de durée et de sélection par jeu (JSON).")
    parser.add_argument("--output", type=Path, help="Dossier des exports.")
    parser.add_argument("--min-duration", type=positive_float, default=20, help="Durée officielle minimale en secondes.")
    parser.add_argument("--max-duration", type=positive_float, default=300, help="Durée maximale générale, sauf exceptions par jeu.")
    parser.add_argument("--segment-duration", type=positive_float, default=59, help="Durée maximale de chaque partie (jusqu'à 180 s, défaut : 59 s).")
    parser.add_argument("--top", type=int, choices=(1, 2, 3), default=3, help="Places du podium à examiner.")
    parser.add_argument("--list-only", action="store_true", help="Afficher la sélection sans télécharger ni écrire l'historique.")
    parser.add_argument("--video", type=Path, help="Monter une vidéo locale avec --metadata.")
    parser.add_argument("--metadata", type=Path, help="Fichier metadata.json du run pour une vidéo locale.")
    parser.add_argument("--start", type=float, default=0, help="Début du run dans la vidéo locale, en secondes.")
    parser.add_argument("--end", type=positive_float, help="Fin de la map dans la vidéo locale, en secondes.")
    args = parser.parse_args(argv)
    if args.min_duration > args.max_duration:
        parser.error("--min-duration doit être inférieure ou égale à --max-duration.")
    if args.segment_duration > MAX_SEGMENT_DURATION:
        parser.error(f"--segment-duration ne doit pas dépasser {MAX_SEGMENT_DURATION} secondes.")
    if not math.isfinite(args.start) or args.start < 0:
        parser.error("--start doit être positif ou nul et fini.")
    if bool(args.video) != bool(args.metadata):
        parser.error("--video et --metadata doivent être utilisés ensemble.")
    if args.start and not args.video:
        parser.error("--start nécessite --video.")
    if args.end is not None and (not args.video or args.end <= args.start):
        parser.error("--end nécessite --video et doit être supérieur à --start.")
    if args.list_only and args.video:
        parser.error("--list-only ne s'applique pas au montage local.")
    settings = replace(
        Settings(), min_duration=args.min_duration, max_duration=args.max_duration,
        segment_duration=args.segment_duration, max_videos=args.max_videos, top=args.top
    )
    if args.games:
        settings = replace(settings, game_urls_file=args.games.resolve())
    if args.game_rules:
        settings = replace(settings, game_rules_file=args.game_rules.resolve())
    if args.output:
        settings = replace(settings, output_dir=args.output.resolve())
    logging.basicConfig(level=logging.INFO, format="%(levelname)s : %(message)s")
    try:
        if not args.list_only:
            for binary in (settings.ffmpeg, settings.ffprobe):
                if not shutil.which(binary):
                    raise FileNotFoundError(f"Exécutable introuvable : {binary}. Consulter README.md.")
        if args.video:
            run = load_run_metadata(args.metadata)
            output = process_video(args.video.resolve(), run, settings, start_time=args.start, end_time=args.end)
            logging.info("Export terminé : %s", output)
        else:
            runs = run_batch(settings, list_only=args.list_only)
            logging.info("%s run(s) %s.", len(runs), "sélectionné(s)" if args.list_only else "exporté(s)")
        return 0
    except (OSError, ValueError, RuntimeError, TypeError) as error:
        logging.error("%s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
