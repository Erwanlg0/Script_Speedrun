from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from speedrun.config import Settings
from speedrun.models import Run
from speedrun.render import probe_video, process_video


TOOLS = Settings()


@unittest.skipUnless(shutil.which(TOOLS.ffmpeg) and shutil.which(TOOLS.ffprobe), "FFmpeg et ffprobe requis")
class NativeRenderTests(unittest.TestCase):
    def test_real_encoder_stays_within_three_minute_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = replace(TOOLS, output_dir=root / "exports", width=160, height=288, fps=5, segment_duration=180)
            source = root / "long-map.mp4"
            subprocess.run(
                [settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                 "-f", "lavfi", "-i", "testsrc2=size=128x72:rate=5",
                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                 "-t", "180.2", "-c:v", "libx264", "-c:a", "aac", str(source)],
                check=True, capture_output=True, timeout=60
            )
            run = Run("long-map", "celeste", "test", "Carte de test", "Any%", "Joueur", "Unknown",
                      "2026-10-28", "https://youtu.be/test", "https://speedrun.com/runs/test", "", 180.2)
            output = process_video(source, run, settings)
            parts = sorted(output.glob("*.mp4"))
            self.assertEqual(len(parts), 2)
            durations = [probe_video(part, settings)["duration"] for part in parts]
            self.assertTrue(all(duration <= 180 for duration in durations))
            self.assertAlmostEqual(sum(durations), 180.2, delta=0.2)

    def test_real_segmentation_audio_silence_and_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Vidéos de test"
            root.mkdir()
            settings = replace(TOOLS, output_dir=root / "exports", width=360, height=640, segment_duration=1)
            for has_audio in (True, False):
                with self.subTest(has_audio=has_audio):
                    source = root / f"source-{has_audio}.mp4"
                    command = [settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                               "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30"]
                    if has_audio:
                        command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
                    command += ["-t", "2.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)]
                    subprocess.run(command, check=True, capture_output=True, timeout=60)
                    run = Run(f"native-{has_audio}", "demo", "test", "Exemple de test", "Any%", "Joueur", "Unknown",
                              "2026-10-28", "https://youtu.be/test", "https://speedrun.com/runs/test", "", 2.2)
                    output = process_video(source, run, settings)
                    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
                    self.assertEqual(len(metadata["segments"]), 3)
                    durations = []
                    for filename in metadata["segments"]:
                        part = output / filename
                        info = probe_video(part, settings)
                        self.assertEqual((info["width"], info["height"]), (360, 640))
                        self.assertEqual(info["has_audio"], has_audio)
                        self.assertLessEqual(info["duration"], 1 + 1 / 30)
                        durations.append(info["duration"])
                        subprocess.run(
                            [settings.ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", str(part), "-f", "null", "-"],
                            check=True, capture_output=True, timeout=60
                        )
                    self.assertAlmostEqual(sum(durations), 2.2, delta=0.1)
                    self.assertTrue((output / "description.txt").is_file())
                    self.assertEqual(process_video(source, run, settings), output)
