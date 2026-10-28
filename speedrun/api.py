import logging
import math
import time
from urllib.parse import parse_qs, quote, urlparse

import requests

from .config import Settings
from .models import Run
from .utils import get_video_id_from_url


API_BASE_URL = "https://www.speedrun.com/api/v1"
logger = logging.getLogger(__name__)


class SpeedrunClient:
    def __init__(self):
        self.session = requests.Session()
        self._players = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.session.close()

    def get(self, endpoint: str, params: dict | None = None) -> dict | None:
        if not isinstance(endpoint, str) or endpoint.startswith('/') or '://' in endpoint or any(
            part in ('.', '..') for part in endpoint.split('/')
        ):
            raise ValueError("L'endpoint API doit être un chemin relatif.")
        for attempt in range(3):
            try:
                with self.session.get(f"{API_BASE_URL}/{endpoint}", params=params, timeout=30) as response:
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get('data'), (dict, list)):
                    logger.warning("Réponse API invalide : %s", endpoint)
                    return None
                return payload
            except requests.RequestException as error:
                if isinstance(error, (requests.Timeout, requests.ConnectionError)) and attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                logger.warning("Échec API %s : %s", endpoint, error)
                return None
            except ValueError:
                logger.warning("Réponse JSON invalide : %s", endpoint)
                return None
        return None

    def find_runs(self, game_id: str, settings: Settings) -> list[Run]:
        game_endpoint = f"games/{quote(game_id, safe='')}"
        response = self.get(game_endpoint, params={'embed': 'categories,levels,variables'})
        game = response.get('data') if response else None
        if not isinstance(game, dict):
            return []
        names = game.get('names')
        game_name = names.get('international') if isinstance(names, dict) else None
        if not isinstance(game_name, str) or not game_name:
            logger.warning("Nom du jeu absent : %s", game_id)
            return []
        if isinstance(game.get('id'), str) and game['id']:
            game_endpoint = f"games/{quote(game['id'], safe='')}"

        resources = {}
        for resource in ('categories', 'levels'):
            embedded = game.get(resource)
            entries = embedded.get('data') if isinstance(embedded, dict) else None
            if not isinstance(entries, list):
                response = self.get(f"{game_endpoint}/{resource}")
                entries = response.get('data') if response else None
            resources[resource] = {
                entry['id']: entry['name']
                for entry in entries or []
                if isinstance(entry, dict) and isinstance(entry.get('id'), str)
                and isinstance(entry.get('name'), str)
            } if isinstance(entries, list) else {}
        embedded = game.get('variables')
        variables = embedded.get('data') if isinstance(embedded, dict) else None
        resources['variables'] = {
            variable['id']: variable for variable in variables
            if isinstance(variable, dict) and isinstance(variable.get('id'), str)
            and variable.get('is-subcategory') is True
        } if isinstance(variables, list) else {}

        runs = []
        seen = set()
        offset = 0
        while True:
            response = self.get(f"{game_endpoint}/records", params={
                'top': settings.top, 'embed': 'players', 'skip-empty': 'true', 'max': 200, 'offset': offset
            })
            boards = response.get('data') if response else None
            if not isinstance(boards, list) or not boards:
                break
            for board in boards:
                for run in self._board_runs(board, game_id, game_name, resources, settings):
                    if run.run_id not in seen:
                        seen.add(run.run_id)
                        runs.append(run)
            pagination = response.get('pagination')
            links = pagination.get('links') if isinstance(pagination, dict) else None
            next_page = next((link.get('uri') for link in links if isinstance(link, dict)
                              and link.get('rel') == 'next'), None) if isinstance(links, list) else None
            if not next_page:
                break
            try:
                parsed = urlparse(next_page)
                next_offset = int(parse_qs(parsed.query)['offset'][0])
                if parsed.scheme != 'https' or parsed.netloc != 'www.speedrun.com' or (
                    parsed.path != f"/api/v1/{game_endpoint}/records" or next_offset <= offset
                ):
                    raise ValueError("Pagination invalide")
            except (KeyError, TypeError, ValueError):
                logger.warning("Pagination API invalide : %s", game_id)
                break
            offset = next_offset
        return runs

    def _board_runs(self, board, game_id, game_name, resources, settings):
        if not isinstance(board, dict):
            return []
        category_id = board.get('category')
        level_id = board.get('level')
        if settings.levels_only and level_id is None:
            return []
        if not isinstance(category_id, str) or category_id not in resources['categories']:
            logger.warning("Classement sans catégorie connue : %s", game_id)
            return []
        category_name = resources['categories'][category_id]
        if level_id is not None:
            if not isinstance(level_id, str) or level_id not in resources['levels']:
                logger.warning("Classement sans niveau connu : %s", game_id)
                return []
            category_name = f"{resources['levels'][level_id]} - {category_name}"
        embedded = board.get('players')
        players = embedded.get('data') if isinstance(embedded, dict) else None
        for player in players if isinstance(players, list) else []:
            if isinstance(player, dict) and isinstance(player.get('id'), str):
                self._players[player['id']] = player

        entries = board.get('runs')
        runs = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or type(entry.get('place')) is not int:
                continue
            rank = entry['place']
            data = entry.get('run')
            if not 1 <= rank <= settings.top or not isinstance(data, dict):
                continue
            run_id = data.get('id')
            status = data.get('status')
            times = data.get('times')
            duration = times.get('primary_t') if isinstance(times, dict) else None
            if not isinstance(run_id, str) or not run_id or not isinstance(status, dict) or status.get('status') != 'verified':
                continue
            if type(duration) not in (int, float) or not math.isfinite(duration) or not settings.min_duration <= duration <= settings.max_duration:
                continue
            videos = data.get('videos')
            links = videos.get('links') if isinstance(videos, dict) else None
            video_url = next((link.get('uri') for link in links if isinstance(link, dict)
                              and get_video_id_from_url(link.get('uri'))), None) if isinstance(links, list) else None
            if not video_url:
                continue
            board_values = board.get('values')
            values = dict(board_values) if isinstance(board_values, dict) else {}
            if isinstance(data.get('values'), dict):
                values.update(data['values'])
            labels = []
            for variable_id, value_id in values.items():
                variable = resources['variables'].get(variable_id)
                if not variable or not isinstance(value_id, str):
                    continue
                options = variable.get('values')
                choices = options.get('values') if isinstance(options, dict) else None
                choice = choices.get(value_id) if isinstance(choices, dict) else None
                label = choice.get('label') if isinstance(choice, dict) else None
                name = variable.get('name')
                if isinstance(label, str) and label:
                    labels.append(f"{name}: {label}" if isinstance(name, str) and name else label)
            player_name, country, profiles = self._player_details(data.get('players'))
            run_link = data.get('weblink')
            date = data.get('date')
            runs.append(Run(
                run_id=run_id, game_id=game_id, category_id=category_id,
                game_name=game_name, category_name=' - '.join([category_name, *labels]),
                player_name=player_name, country=country,
                date=date if isinstance(date, str) and date else 'Unknown',
                video_url=video_url,
                run_link=run_link if isinstance(run_link, str) else '',
                player_profile_link=profiles, duration=float(duration), rank=rank
            ))
        return runs

    def _player_details(self, players):
        names = []
        countries = []
        profiles = []
        for player in players if isinstance(players, list) else []:
            if not isinstance(player, dict):
                continue
            player_id = player.get('id')
            if isinstance(player_id, str):
                if player_id not in self._players:
                    response = self.get(f"users/{quote(player_id, safe='')}")
                    user = response.get('data') if response else None
                    self._players[player_id] = user if isinstance(user, dict) else {}
                player = self._players[player_id]
            player_names = player.get('names')
            name = player_names.get('international') if isinstance(player_names, dict) else player.get('name')
            names.append(name if isinstance(name, str) and name else 'Joueur inconnu')
            location = player.get('location')
            country = location.get('country') if isinstance(location, dict) else None
            code = country.get('code') if isinstance(country, dict) else None
            countries.append(code if isinstance(code, str) and code else 'Unknown')
            profile = player.get('weblink')
            if isinstance(profile, str) and profile and profile not in profiles:
                profiles.append(profile)
        return (
            ' & '.join(names) or 'Joueur inconnu',
            countries[0] if countries and len(set(countries)) == 1 else 'Unknown',
            '\n'.join(profiles)
        )
