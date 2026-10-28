from dataclasses import replace
import json
import math
from pathlib import Path


def load_game_rules(path):
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rules, dict):
        raise ValueError("Les règles par jeu doivent former un objet JSON.")
    for game, options in rules.items():
        if not isinstance(game, str) or not game or not isinstance(options, dict):
            raise ValueError("Règle de jeu invalide.")
        if set(options) - {"max_duration", "levels_only"}:
            raise ValueError(f"Option inconnue dans les règles de {game}.")
        if "max_duration" in options:
            duration = options["max_duration"]
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"Durée maximale invalide pour {game}.")
        if "levels_only" in options and type(options["levels_only"]) is not bool:
            raise ValueError(f"levels_only doit être un booléen pour {game}.")
    return {game.casefold(): options for game, options in rules.items()}


def settings_for_game(settings, game_id, rules):
    options = rules.get(game_id.casefold(), {})
    if options.get("max_duration", settings.max_duration) < settings.min_duration:
        raise ValueError(f"Durée maximale inférieure au minimum pour {game_id}.")
    return replace(settings, **options)
