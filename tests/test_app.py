from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from speedrun.app import rank_runs, read_game_ids, run_batch
from speedrun.config import Settings
from speedrun.history import load_history
from speedrun.models import Run


class BatchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        games = root / "games.txt"
        games.write_text("https://speedrun.com/game/\nhttps://speedrun.com/game\n", encoding="utf-8")
        self.settings = replace(Settings(), game_urls_file=games, history_file=root / "history.json", max_videos=2)
        self.run = Run("one", "game", "category", "Game", "Any%", "Joueur", "fr", "2026-10-28",
                       "https://youtu.be/one", "https://speedrun.com/runs/one", "https://speedrun.com/users/player", 30)
        self.client_patch = patch("speedrun.app.SpeedrunClient")
        self.client = self.client_patch.start().return_value.__enter__.return_value
        self.addCleanup(self.client_patch.stop)
        self.client.find_runs.return_value = [self.run]
        self.download_patch = patch("speedrun.app.download_video", return_value=root / "source.mp4")
        self.download = self.download_patch.start()
        self.addCleanup(self.download_patch.stop)
        self.probe_patch = patch("speedrun.app.probe_video", return_value={"duration": 38})
        self.probe = self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)
        self.render_patch = patch("speedrun.app.process_video", return_value=root / "output")
        self.render = self.render_patch.start()
        self.addCleanup(self.render_patch.stop)

    def test_new_record_in_known_category_preserves_history(self):
        self.settings.history_file.write_text('{"game": {"category": [null, "old"]}}', encoding="utf-8")
        self.assertEqual(run_batch(self.settings), [self.run])
        self.assertEqual(load_history(self.settings.history_file), {"game": {"category": [None, "old", "one"]}})
        self.client.find_runs.assert_called_once_with("game", self.settings)

    def test_multiple_successes_are_saved(self):
        second = replace(self.run, run_id="two", video_url="https://youtu.be/two")
        self.client.find_runs.return_value = [self.run, second]
        self.assertEqual(len(run_batch(self.settings)), 2)
        self.assertEqual(load_history(self.settings.history_file)["game"]["category"], ["one", "two"])

    def test_same_source_in_several_categories_is_processed_once(self):
        self.client.find_runs.return_value = [self.run, replace(self.run, category_id="other")]
        self.assertEqual(run_batch(self.settings), [self.run])
        self.download.assert_called_once()

    def test_same_source_in_other_category_is_skipped_on_next_batch(self):
        self.settings = replace(self.settings, max_videos=1)
        self.client.find_runs.return_value = [self.run, replace(self.run, run_id="two", category_id="other")]
        self.assertEqual(run_batch(self.settings), [self.run])
        self.assertEqual(run_batch(self.settings), [])
        self.download.assert_called_once()

    def test_history_from_other_games_also_prevents_source_duplicates(self):
        self.settings.history_file.write_text('{"another-game": {"another-category": [null, "one"]}}', encoding="utf-8")
        self.assertEqual(run_batch(self.settings), [])
        self.download.assert_not_called()

    def test_used_video_and_empty_list_finish(self):
        self.settings.history_file.write_text('{"game": {"category": ["one"]}}', encoding="utf-8")
        self.assertEqual(run_batch(self.settings), [])
        self.download.assert_not_called()
        self.settings.game_urls_file.write_text("", encoding="utf-8")
        self.client.find_runs.reset_mock()
        self.assertEqual(run_batch(self.settings), [])
        self.client.find_runs.assert_not_called()

    def test_failed_download_probe_or_render_never_changes_history(self):
        for target, exception in ((self.download, RuntimeError("download")), (self.probe, ValueError("probe")), (self.render, RuntimeError("render"))):
            with self.subTest(exception=exception):
                target.side_effect = exception
                with self.assertRaisesRegex(RuntimeError, "Aucun run exporté"):
                    run_batch(self.settings)
                self.assertFalse(self.settings.history_file.exists())
                target.side_effect = None

    def test_wrong_source_length_is_not_rendered(self):
        for duration in (0, 27, 151, float('nan')):
            with self.subTest(duration=duration):
                self.probe.return_value = {"duration": duration}
                with self.assertRaisesRegex(RuntimeError, "Aucun run exporté"):
                    run_batch(self.settings)
        self.render.assert_not_called()
        self.assertFalse(self.settings.history_file.exists())

    def test_all_failures_are_reported_but_no_candidates_is_normal(self):
        self.client.find_runs.return_value = [self.run, replace(self.run, run_id="two", video_url="https://youtu.be/two")]
        self.download.side_effect = RuntimeError("download")
        with self.assertRaisesRegex(RuntimeError, "2 échec"):
            run_batch(self.settings)
        self.client.find_runs.return_value = []
        self.assertEqual(run_batch(self.settings), [])

    def test_successful_candidate_survives_an_earlier_failure(self):
        second = replace(self.run, run_id="two", video_url="https://youtu.be/two")
        self.client.find_runs.return_value = [self.run, second]
        self.download.side_effect = [RuntimeError("download"), self.settings.download_dir / "source.mp4"]
        self.assertEqual(run_batch(self.settings), [second])
        self.assertEqual(load_history(self.settings.history_file)["game"]["category"], ["two"])

    def test_list_only_has_no_download_or_history_side_effect(self):
        self.assertEqual(run_batch(self.settings, list_only=True), [self.run])
        self.download.assert_not_called()
        self.render.assert_not_called()
        self.assertFalse(self.settings.history_file.exists())

    def test_game_failure_does_not_abort_other_games(self):
        self.settings.game_urls_file.write_text("https://speedrun.com/one\nhttps://speedrun.com/two\n", encoding="utf-8")
        self.client.find_runs.side_effect = [RuntimeError("unavailable"), [self.run]]
        self.assertEqual(run_batch(self.settings), [self.run])

    def test_prioritizes_records_short_runs_and_recent_dates(self):
        long_record = replace(self.run, run_id="long", duration=100, date="2026-10-28")
        old_record = replace(self.run, run_id="old", date="2020-01-01")
        second_place = replace(self.run, run_id="silver", rank=2)
        self.assertEqual(rank_runs([second_place, long_record, old_record, self.run], self.settings),
                         [self.run, old_record, long_record, second_place])

    def test_utf8_bom_comments_and_duplicate_games(self):
        self.settings.game_urls_file.write_text("\ufeff# Jeux\nhttps://speedrun.com/game\nhttps://speedrun.com/fr-FR/game/\n", encoding="utf-8")
        self.assertEqual(read_game_ids(self.settings.game_urls_file), ["game"])

    def test_game_exception_reaches_discovery_download_and_render(self):
        rules = self.settings.history_file.parent / "rules.json"
        rules.write_text('{"celeste": {"max_duration": 3600, "levels_only": true}}', encoding="utf-8")
        self.settings = replace(self.settings, game_rules_file=rules)
        self.settings.game_urls_file.write_text("https://speedrun.com/celeste\n", encoding="utf-8")
        self.run = replace(self.run, game_id="celeste", duration=1800)
        self.client.find_runs.return_value = [self.run]
        self.probe.return_value = {"duration": 1820}
        self.assertEqual(run_batch(self.settings), [self.run])
        discovery_settings = self.client.find_runs.call_args.args[1]
        self.assertTrue(discovery_settings.levels_only)
        self.assertEqual(discovery_settings.max_duration, 3600)
        self.assertEqual(self.download.call_args.args[1], discovery_settings)
        self.assertEqual(self.render.call_args.args[2].segment_duration, 59)
