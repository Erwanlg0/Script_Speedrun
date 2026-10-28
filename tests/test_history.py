from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from speedrun.history import is_used, load_history, record_run
from speedrun.models import Run


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name, "history.json")
        self.run = Run(
            run_id="record", game_id="game", category_id="category", game_name="Jeu",
            category_name="Any%", player_name="Joueur", country="fr", date="2026-10-28",
            video_url="https://youtu.be/one", run_link="https://speedrun.com/runs/record",
            player_profile_link="https://speedrun.com/users/player", duration=30
        )

    def test_missing_history_is_empty(self):
        self.assertEqual(load_history(self.path), {})

    def test_record_preserves_legacy_history_and_all_new_successes(self):
        original = {"ancien": {"catégorie": [None, "previous"]}}
        self.path.write_text(json.dumps(original), encoding="utf-8")
        record_run(self.path, self.run)
        record_run(self.path, replace(self.run, video_url="https://youtu.be/two"))
        original["game"] = {"category": ["one", "two"]}
        self.assertEqual(load_history(self.path), original)

    def test_equivalent_urls_are_idempotent_in_same_category(self):
        record_run(self.path, self.run)
        equivalent = replace(self.run, video_url="https://youtube.com/watch?v=one")
        before = self.path.read_bytes()
        self.assertTrue(is_used(load_history(self.path), equivalent))
        record_run(self.path, equivalent)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(is_used(load_history(self.path), replace(self.run, category_id="other")))

    def test_twitch_history_uses_existing_video_id_format(self):
        run = replace(self.run, video_url="https://www.twitch.tv/videos/123")
        record_run(self.path, run)
        self.assertEqual(load_history(self.path), {"game": {"category": ["v123"]}})
        self.assertTrue(is_used(load_history(self.path), run))

    def test_invalid_url_does_not_create_history(self):
        run = replace(self.run, video_url="https://youtube.com.evil.example/watch?v=one")
        with self.assertRaises(ValueError):
            record_run(self.path, run)
        self.assertFalse(self.path.exists())

    def test_corrupt_json_is_preserved(self):
        self.path.write_text("broken JSON", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            record_run(self.path, self.run)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken JSON")

    def test_invalid_history_shapes_are_preserved(self):
        invalid = ([], {"game": []}, {"game": {"category": "one"}}, {"game": {"category": [42]}})
        for value in invalid:
            with self.subTest(value=value):
                serialized = json.dumps(value)
                self.path.write_text(serialized, encoding="utf-8")
                with self.assertRaises(ValueError):
                    record_run(self.path, self.run)
                self.assertEqual(self.path.read_text(encoding="utf-8"), serialized)

    def test_failed_replace_preserves_file_and_cleans_temporary_output(self):
        self.path.write_text('{"old": {}}', encoding="utf-8")
        with patch("speedrun.history.os.replace", side_effect=OSError("file locked")):
            with self.assertRaisesRegex(OSError, "file locked"):
                record_run(self.path, self.run)
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"old": {}}')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_serialization_preserves_file_and_cleans_temporary_output(self):
        self.path.write_text('{"old": {}}', encoding="utf-8")
        with patch("speedrun.history.json.dump", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                record_run(self.path, self.run)
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"old": {}}')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_new_history_directory_is_created(self):
        path = self.path.parent / "new" / "history.json"
        record_run(path, self.run)
        self.assertTrue(is_used(load_history(path), self.run))


if __name__ == "__main__":
    unittest.main()
