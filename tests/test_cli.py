from contextlib import redirect_stderr
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from speedrun.cli import main


class CliTests(unittest.TestCase):
    def test_invalid_arguments_fail_before_work(self):
        cases = (
            ["--max-videos", "0"], ["--min-duration", "nan"],
            ["--min-duration", "60", "--max-duration", "30"],
            ["--video", "source.mp4"], ["--metadata", "metadata.json"],
            ["--start", "-1"], ["--start", "5"], ["--top", "4"],
            ["--segment-duration", "181"], ["--end", "30"],
            ["--video", "source.mp4", "--metadata", "metadata.json", "--start", "10", "--end", "9"],
            ["--list-only", "--video", "source.mp4", "--metadata", "metadata.json"]
        )
        with patch("speedrun.cli.run_batch") as batch:
            for args in cases:
                with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
            batch.assert_not_called()

    def test_preview_does_not_require_native_tools(self):
        with patch("speedrun.cli.run_batch", return_value=[]) as batch, patch("speedrun.cli.shutil.which", return_value=None):
            self.assertEqual(main(["--list-only", "--max-videos", "1"]), 0)
        self.assertTrue(batch.call_args.kwargs["list_only"])
        self.assertEqual(batch.call_args.args[0].max_videos, 1)

    def test_missing_tools_return_actionable_failure(self):
        with patch("speedrun.cli.shutil.which", return_value=None), self.assertLogs(level="ERROR") as logs:
            self.assertEqual(main([]), 1)
        self.assertIn("introuvable", logs.output[0])

    def test_local_render_has_no_download_or_history_side_effect(self):
        with patch("speedrun.cli.shutil.which", return_value="ffmpeg"), \
             patch("speedrun.cli.load_run_metadata", return_value=object()) as load, \
             patch("speedrun.cli.process_video", return_value=Path("output")) as render, \
             patch("speedrun.cli.run_batch") as batch:
            self.assertEqual(main(["--video", "source.mp4", "--metadata", "metadata.json", "--start", "4.5", "--end", "30"]), 0)
        load.assert_called_once_with(Path("metadata.json"))
        self.assertEqual(render.call_args.kwargs["start_time"], 4.5)
        self.assertEqual(render.call_args.kwargs["end_time"], 30)
        batch.assert_not_called()
