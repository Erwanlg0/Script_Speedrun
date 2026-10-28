from copy import deepcopy
import unittest
from unittest.mock import MagicMock, patch

import requests

from speedrun.api import API_BASE_URL, SpeedrunClient
from speedrun.config import Settings


def response(payload, status=200):
    result = MagicMock(spec=requests.Response)
    result.__enter__.return_value = result
    result.status_code = status
    result.json.return_value = deepcopy(payload)
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return result


def run_data(run_id='run-one', **overrides):
    data = {
        'id': run_id, 'status': {'status': 'verified'}, 'times': {'primary_t': 30},
        'players': [{'rel': 'user', 'id': 'player'}], 'date': '2026-10-01',
        'videos': {'links': [{'uri': 'https://youtu.be/video'}]},
        'weblink': f'https://www.speedrun.com/run/{run_id}'
    }
    data.update(overrides)
    return data


def board(entries=None, level=None):
    return {
        'category': 'category', 'level': level,
        'runs': entries if entries is not None else [{'place': 1, 'run': run_data()}],
        'players': {'data': [{
            'id': 'player', 'names': {'international': 'Runner'},
            'weblink': 'https://www.speedrun.com/users/real-profile',
            'location': {'country': {'code': 'FR'}}
        }]}
    }


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock(spec=requests.Session)
        self.enterContext(patch('speedrun.api.requests.Session', return_value=self.session))
        self.client = self.enterContext(SpeedrunClient())
        self.sleep = self.enterContext(patch('speedrun.api.time.sleep'))

    def test_session_is_closed_by_context_manager(self):
        with SpeedrunClient() as client:
            self.assertIs(client.session, self.session)
        self.session.close.assert_called_once()

    def test_get_uses_timeout_and_relative_endpoint(self):
        self.session.get.return_value = response({'data': []})
        self.assertEqual(self.client.get('games/example', {'embed': 'levels'}), {'data': []})
        self.session.get.assert_called_once_with(
            API_BASE_URL + '/games/example', params={'embed': 'levels'}, timeout=30
        )
        for endpoint in ('https://example.com/', '/games', '../games'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                self.client.get(endpoint)

    def test_transient_statuses_are_retried_at_most_three_times(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status), self.assertLogs('speedrun.api', level='WARNING'):
                self.session.get.reset_mock()
                self.session.get.side_effect = [response({'data': []}, status) for _ in range(3)]
                self.assertIsNone(self.client.get('games/example'))
                self.assertEqual(self.session.get.call_count, 3)

    def test_connection_failure_can_recover(self):
        self.session.get.side_effect = [requests.Timeout('timeout'), response({'data': []})]
        self.assertEqual(self.client.get('games/example'), {'data': []})
        self.assertEqual(self.session.get.call_count, 2)
        self.sleep.assert_called_once_with(0.5)

    def test_persistent_connection_failure_stops_after_three_attempts(self):
        self.session.get.side_effect = requests.ConnectionError('connection refused')
        with self.assertLogs('speedrun.api', level='WARNING'):
            self.assertIsNone(self.client.get('games/example'))
        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_transient_http_failure_can_recover(self):
        self.session.get.side_effect = [response({'data': []}, 503), response({'data': []})]
        self.assertEqual(self.client.get('games/example'), {'data': []})
        self.assertEqual(self.session.get.call_count, 2)

    def test_permanent_http_failure_is_not_retried(self):
        self.session.get.return_value = response({'data': []}, 404)
        with self.assertLogs('speedrun.api', level='WARNING'):
            self.assertIsNone(self.client.get('games/example'))
        self.session.get.assert_called_once()

    def test_invalid_json_and_payloads_fail_without_retry(self):
        for payload in (None, [], {}, {'data': None}, {'data': 'unexpected'}):
            with self.subTest(payload=payload), self.assertLogs('speedrun.api', level='WARNING'):
                self.session.get.reset_mock()
                self.session.get.return_value = response(payload)
                self.assertIsNone(self.client.get('games/example'))
                self.session.get.assert_called_once()
        self.session.get.return_value = response({'data': []})
        self.session.get.return_value.json.side_effect = ValueError('invalid JSON')
        with self.assertLogs('speedrun.api', level='WARNING'):
            self.assertIsNone(self.client.get('games/example'))


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock(spec=requests.Session)
        self.enterContext(patch('speedrun.api.requests.Session', return_value=self.session))
        self.client = self.enterContext(SpeedrunClient())
        self.settings = Settings()
        self.calls = []
        self.routes = {
            'games/example': {'data': {
                'id': 'gameid', 'names': {'international': 'Example Game'},
                'categories': {'data': [{'id': 'category', 'name': 'Any%'}]},
                'levels': {'data': [{'id': 'level-one', 'name': 'First level'},
                                    {'id': 'level-two', 'name': 'Second level'}]}
            }},
            'games/gameid/records': {'data': [board()]}
        }
        self.session.get.side_effect = self.request

    def request(self, url, params, timeout):
        endpoint = url.removeprefix(API_BASE_URL + '/')
        self.calls.append((endpoint, params))
        payload = self.routes.get((endpoint, params.get('offset'))) if params else None
        if payload is None:
            payload = self.routes[endpoint]
        return response(payload)

    def test_podium_metadata_uses_embedded_profiles(self):
        entries = [{'place': rank, 'run': run_data(f'run-{rank}')} for rank in (1, 2, 3)]
        self.routes['games/gameid/records']['data'] = [board(entries)]
        runs = self.client.find_runs('example', self.settings)
        self.assertEqual([run.rank for run in runs], [1, 2, 3])
        self.assertEqual(runs[0].game_id, 'example')
        self.assertEqual(runs[0].game_name, 'Example Game')
        self.assertEqual(runs[0].player_name, 'Runner')
        self.assertEqual(runs[0].country, 'FR')
        self.assertEqual(runs[0].player_profile_link, 'https://www.speedrun.com/users/real-profile')
        self.assertEqual(runs[0].date, '2026-10-01')
        self.assertEqual(runs[0].duration, 30.0)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][1]['top'], 3)

    def test_unverified_outside_duration_and_unsupported_videos_are_filtered(self):
        invalid = [
            run_data(status={'status': 'new'}), run_data(status=None),
            run_data(times={'primary_t': 19.9}), run_data(times={'primary_t': 300.1}),
            run_data(times={'primary_t': float('nan')}), run_data(times={'primary_t': True}),
            run_data(times={'primary_t': '30'}), run_data(times=None),
            run_data(videos=None), run_data(videos={'links': []}),
            run_data(videos={'links': [None]}),
            run_data(videos={'links': [{'uri': 'https://example.com/video'}]}),
            run_data(id=None)
        ]
        entries = [{'place': 1, 'run': data} for data in invalid]
        entries.extend([None, {'place': '1', 'run': run_data()}, {'place': 4, 'run': run_data()}])
        entries.extend({'place': 1, 'run': run_data(f'limit-{duration}', times={'primary_t': duration})}
                       for duration in (20, 300))
        self.routes['games/gameid/records']['data'] = [board(entries)]
        runs = self.client.find_runs('example', self.settings)
        self.assertEqual([run.duration for run in runs], [20, 300])

    def test_duration_settings_are_respected(self):
        self.settings = Settings(min_duration=31, max_duration=40)
        self.assertEqual(self.client.find_runs('example', self.settings), [])

    def test_all_levels_are_returned_and_duplicate_runs_are_removed(self):
        self.routes['games/gameid/records']['data'] = [
            board(level='level-one'),
            board([{'place': 2, 'run': run_data('second')}], level='level-two'),
            board(level='level-one')
        ]
        runs = self.client.find_runs('example', self.settings)
        self.assertEqual([run.run_id for run in runs], ['run-one', 'second'])
        self.assertEqual([run.category_name for run in runs], ['First level - Any%', 'Second level - Any%'])

    def test_levels_only_excludes_full_game_runs(self):
        self.routes['games/gameid/records']['data'] = [
            board(),
            board([{'place': 1, 'run': run_data('map-one')}], level='level-one'),
            board([{'place': 2, 'run': run_data('map-two')}], level='level-two')
        ]
        self.settings = Settings(levels_only=True)
        runs = self.client.find_runs('example', self.settings)
        self.assertEqual([run.run_id for run in runs], ['map-one', 'map-two'])
        self.assertEqual([run.category_name for run in runs], ['First level - Any%', 'Second level - Any%'])

    def test_subcategory_labels_distinguish_individual_stages(self):
        game = self.routes['games/example']['data']
        game['levels']['data'][0]['name'] = 'World 1'
        game['variables'] = {'data': [{
            'id': 'stage', 'name': 'Level', 'is-subcategory': True,
            'values': {'values': {'one-six': {'label': '1-6'}, 'one-one': {'label': '1-1'}}}
        }, {
            'id': 'extra', 'name': 'Input device', 'is-subcategory': False,
            'values': {'values': {'controller': {'label': 'Controller'}}}
        }]}
        entries = [
            {'place': 1, 'run': run_data(values={'stage': 'one-six', 'extra': 'controller'})},
            {'place': 2, 'run': run_data('second', values={})}
        ]
        data = board(entries, level='level-one')
        data['values'] = {'stage': 'one-one'}
        self.routes['games/gameid/records']['data'] = [data]
        runs = self.client.find_runs('example', self.settings)
        self.assertEqual([run.category_name for run in runs], [
            'World 1 - Any% - Level: 1-6', 'World 1 - Any% - Level: 1-1'
        ])
        self.assertEqual(len(self.calls), 2)
        self.assertIn('variables', self.calls[0][1]['embed'])

    def test_missing_or_malformed_variables_keep_base_category(self):
        self.routes['games/gameid/records']['data'] = [board([
            {'place': 1, 'run': run_data(values={'stage': 'unknown'})}
        ])]
        for variables in (None, {}, {'data': None}, {'data': [None, {'id': [], 'is-subcategory': True}]},
                          {'data': [{'id': 'stage', 'is-subcategory': True, 'values': {'values': []}}]}):
            with self.subTest(variables=variables):
                self.calls.clear()
                self.routes['games/example']['data']['variables'] = variables
                runs = self.client.find_runs('example', self.settings)
                self.assertEqual(runs[0].category_name, 'Any%')
                self.assertEqual(len(self.calls), 2)

    def test_guest_and_cooperative_players(self):
        data = run_data(players=[{'rel': 'user', 'id': 'player'}, {'rel': 'guest', 'name': 'Invité'}])
        self.routes['games/gameid/records']['data'] = [board([{'place': 1, 'run': data}])]
        run = self.client.find_runs('example', self.settings)[0]
        self.assertEqual(run.player_name, 'Runner & Invité')
        self.assertEqual(run.country, 'Unknown')
        self.assertEqual(run.player_profile_link, 'https://www.speedrun.com/users/real-profile')

    def test_missing_player_embed_fetches_each_user_once(self):
        entries = [{'place': rank, 'run': run_data(f'run-{rank}')} for rank in (1, 2)]
        data = board(entries)
        del data['players']
        self.routes['games/gameid/records']['data'] = [data]
        self.routes['users/player'] = {'data': {'names': {'international': 'Real Runner'}, 'location': None}}
        runs = self.client.find_runs('example', self.settings)
        self.assertEqual([run.player_name for run in runs], ['Real Runner', 'Real Runner'])
        self.assertEqual(sum(endpoint == 'users/player' for endpoint, _ in self.calls), 1)

    def test_missing_game_embeds_fall_back_to_collections(self):
        game = self.routes['games/example']['data']
        self.routes['games/gameid/categories'] = game.pop('categories')
        self.routes['games/gameid/levels'] = game.pop('levels')
        self.assertEqual(len(self.client.find_runs('example', self.settings)), 1)

    def test_supported_video_can_follow_an_unsupported_link(self):
        data = run_data(videos={'links': [{'uri': 'https://example.com/video'},
                                        {'uri': 'https://www.twitch.tv/videos/123'}]})
        self.routes['games/gameid/records']['data'] = [board([{'place': 1, 'run': data}])]
        self.assertEqual(self.client.find_runs('example', self.settings)[0].video_url,
                         'https://www.twitch.tv/videos/123')

    def test_pagination_visits_subsequent_levels(self):
        self.routes['games/gameid/records']['pagination'] = {'links': [{
            'rel': 'next', 'uri': API_BASE_URL + '/games/gameid/records?offset=200&max=200'
        }]}
        self.routes[('games/gameid/records', 200)] = {'data': [
            board([{'place': 1, 'run': run_data('next-page')}], level='level-two')
        ]}
        self.assertEqual([run.run_id for run in self.client.find_runs('example', self.settings)],
                         ['run-one', 'next-page'])

    def test_invalid_pagination_cannot_repeat_or_visit_another_host(self):
        for uri in (API_BASE_URL + '/games/gameid/records?offset=0',
                    'https://example.com/api/v1/games/gameid/records?offset=200', None):
            self.routes['games/gameid/records']['pagination'] = {'links': [{'rel': 'next', 'uri': uri}]}
            with self.subTest(uri=uri):
                if uri:
                    with self.assertLogs('speedrun.api', level='WARNING'):
                        self.assertEqual(len(self.client.find_runs('example', self.settings)), 1)
                else:
                    self.assertEqual(len(self.client.find_runs('example', self.settings)), 1)

    def test_empty_or_malformed_collections_are_safe(self):
        for payload in ({'data': []}, {'data': [None, {}, {'category': []}]}, {'data': {}}):
            self.routes['games/gameid/records'] = payload
            with self.subTest(payload=payload):
                self.assertEqual(self.client.find_runs('example', self.settings), [])

    def test_missing_game_name_prevents_board_requests(self):
        self.routes['games/example'] = {'data': {'names': None}}
        with self.assertLogs('speedrun.api', level='WARNING'):
            self.assertEqual(self.client.find_runs('example', self.settings), [])
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
