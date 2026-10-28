from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from speedrun.models import Run
from speedrun.publication import load_run_metadata, write_publication_files


class PublicationTests(unittest.TestCase):
    def test_credits_metadata_and_round_trip(self):
        run = Run("id", "game", "category", "Jeu épatant", "Any%", "Joueur", "fr", "2026-10-28",
                  "https://youtu.be/source", "https://speedrun.com/runs/id", "https://speedrun.com/users/player", 31.25)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            write_publication_files(run, folder, [folder / "part-01.mp4"], {"width": 1080})
            self.assertEqual(load_run_metadata(folder / "metadata.json"), run)
            description = (folder / "description.txt").read_text(encoding="utf-8")
            for value in (run.game_name, run.player_name, run.video_url, run.run_link, "0:31.250"):
                self.assertIn(value, description)
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["segments"], ["part-01.mp4"])
            self.assertEqual(metadata["render"], {"width": 1080})

    def test_invalid_metadata_is_rejected(self):
        run = Run("id", "game", "cat", "Game", "Any%", "Player", "fr", "2026-01-01", "", "", "", 31)
        for payload in ([], {}, {"run": []}, {"run": {**asdict(run), "duration": -1}},
                        {"run": {**asdict(run), "duration": True}}, {"run": {**asdict(run), "rank": True}},
                        {"run": {**asdict(run), "player_name": None}}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                path = Path(directory, "metadata.json")
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_run_metadata(path)
