from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from speedrun.config import Settings
from speedrun.policy import load_game_rules, settings_for_game


class GamePolicyTests(unittest.TestCase):
    def test_long_maps_are_explicit_exceptions_and_do_not_change_other_games(self):
        settings = Settings()
        rules = {"celeste": {"max_duration": 3600, "levels_only": True}}
        celeste = settings_for_game(settings, "Celeste", rules)
        self.assertEqual(celeste.max_duration, 3600)
        self.assertTrue(celeste.levels_only)
        self.assertEqual(celeste.segment_duration, settings.segment_duration)
        self.assertEqual(settings_for_game(settings, "smb1", rules), settings)
        self.assertEqual(settings.max_duration, 300)

    def test_rules_are_validated_before_any_download(self):
        invalid = ([], {"celeste": []}, {"celeste": {"typo": True}}, {"celeste": {"levels_only": "true"}},
                   {"celeste": {"max_duration": -1}}, {"celeste": {"max_duration": float('inf')}},
                   {"celeste": {"max_duration": True}})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "rules.json")
            for rules in invalid:
                with self.subTest(rules=rules):
                    path.write_text(json.dumps(rules), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_game_rules(path)
            path.write_text('{"Celeste": {"max_duration": 1800, "levels_only": true}}', encoding="utf-8")
            self.assertEqual(load_game_rules(path)["celeste"]["max_duration"], 1800)

    def test_exception_cannot_be_shorter_than_global_minimum(self):
        settings = replace(Settings(), min_duration=60)
        with self.assertRaises(ValueError):
            settings_for_game(settings, "celeste", {"celeste": {"max_duration": 30}})
