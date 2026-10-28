from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from yt_dlp.utils import DownloadError

from speedrun.config import Settings
from speedrun.download import _reject_video, download_video


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.settings = replace(Settings(), download_dir=self.directory / "downloads")
        self.downloader = MagicMock()
        self.youtube_dl = patch("speedrun.download.yt_dlp.YoutubeDL")
        self.factory = self.youtube_dl.start()
        self.addCleanup(self.youtube_dl.stop)
        self.factory.return_value.__enter__.return_value = self.downloader

    def write_video(self, name):
        path = self.directory / name
        path.write_bytes(b"video content")
        return path

    def test_returns_actual_merged_file_instead_of_original_extension(self):
        merged = self.write_video("source.mkv")
        self.downloader.extract_info.return_value = {
            "duration": 30, "requested_downloads": [{"filepath": str(merged)}]
        }
        self.downloader.prepare_filename.return_value = str(self.directory / "source.webm")
        self.assertEqual(download_video("https://youtu.be/one", self.settings), merged.resolve())
        self.assertTrue(self.settings.download_dir.is_dir())
        self.downloader.extract_info.assert_called_once_with("https://youtu.be/one", download=True)
        self.factory.return_value.__exit__.assert_called_once()

    def test_single_stream_and_existing_download_paths(self):
        existing = self.write_video("source.mp4")
        for info in (
            {"duration": 30, "filepath": str(existing)},
            {"duration": 30, "requested_downloads": None},
        ):
            with self.subTest(info=info):
                self.downloader.extract_info.return_value = info
                self.downloader.prepare_filename.return_value = str(existing)
                self.assertEqual(download_video("https://youtu.be/one", self.settings), existing.resolve())
                self.assertEqual(existing.read_bytes(), b"video content")

    def test_unsupported_host_does_not_start_downloader(self):
        with self.assertRaises(ValueError):
            download_video("https://youtube.com.evil.example/watch?v=one", self.settings)
        self.factory.assert_not_called()
        self.assertFalse(self.settings.download_dir.exists())

    def test_download_error_keeps_its_cause(self):
        error = DownloadError("unavailable")
        self.downloader.extract_info.side_effect = error
        with self.assertRaisesRegex(RuntimeError, "unavailable") as raised:
            download_video("https://youtu.be/one", self.settings)
        self.assertIs(raised.exception.__cause__, error)

    def test_missing_or_empty_output_is_not_a_success(self):
        empty = self.directory / "empty.mp4"
        empty.touch()
        self.downloader.extract_info.return_value = {"duration": 30, "filepath": str(empty)}
        self.downloader.prepare_filename.return_value = str(self.directory / "absent.mp4")
        with self.assertRaises(FileNotFoundError):
            download_video("https://youtu.be/one", self.settings)
        self.assertTrue(empty.exists())

    def test_rejected_or_invalid_extraction_is_not_a_success(self):
        for info in (None, {"duration": None}, {"duration": 30, "is_live": True}):
            with self.subTest(info=info):
                self.downloader.extract_info.return_value = info
                with self.assertRaises(ValueError):
                    download_video("https://youtu.be/one", self.settings)

    def test_native_ffmpeg_location_is_passed_to_merger(self):
        path = self.write_video("merged.mkv")
        self.downloader.extract_info.return_value = {"duration": 30, "filepath": str(path)}
        with patch("speedrun.download.shutil.which", side_effect=lambda name: "C:/Tools/ffmpeg.exe" if name == self.settings.ffmpeg else None):
            download_video("https://youtu.be/one", self.settings)
        self.assertEqual(self.factory.call_args.args[0]["ffmpeg_location"], "C:/Tools/ffmpeg.exe")

    def test_existing_node_is_enabled_for_youtube_challenges(self):
        path = self.write_video("source.mp4")
        self.downloader.extract_info.return_value = {"duration": 30, "filepath": str(path)}
        with patch("speedrun.download.shutil.which", side_effect=lambda name: "C:/Tools/node.exe" if name == "node" else None):
            download_video("https://youtu.be/one", self.settings)
        self.assertEqual(self.factory.call_args.args[0]["js_runtimes"]["node"], {"path": "C:/Tools/node.exe"})

    def test_oversized_source_is_rejected_by_filter_before_transfer(self):
        transfer = MagicMock()

        def extract(url, download):
            metadata = {"duration": self.settings.max_duration + 121}
            match_filter = self.factory.call_args.args[0]["match_filter"]
            if match_filter(metadata, incomplete=False):
                return None
            transfer()
            return metadata

        self.downloader.extract_info.side_effect = extract
        with self.assertRaises(ValueError):
            download_video("https://youtu.be/one", self.settings)
        transfer.assert_not_called()


class VideoFilterTests(unittest.TestCase):
    def test_complete_replay_is_accepted(self):
        self.assertIsNone(_reject_video({"duration": 30, "live_status": "was_live"}))

    def test_live_upcoming_and_invalid_duration_are_rejected(self):
        invalid = (
            {"duration": 30, "is_live": True},
            {"duration": 30, "live_status": "is_upcoming"},
            {"duration": 30, "_type": "playlist"},
            {"duration": None}, {"duration": 0}, {"duration": -1},
            {"duration": float("inf")}, {"duration": float("nan")},
            {"duration": "30"}, {"duration": True},
        )
        for info in invalid:
            with self.subTest(info=info):
                self.assertIsNotNone(_reject_video(info))

    def test_duration_may_be_unknown_only_during_partial_metadata_extraction(self):
        self.assertIsNone(_reject_video({}, incomplete=True))
        self.assertIsNotNone(_reject_video({}, incomplete=False))

    def test_source_duration_limit_includes_boundary(self):
        self.assertIsNone(_reject_video({"duration": 420}, max_duration=420))
        self.assertIsNotNone(_reject_video({"duration": 421}, max_duration=420))


if __name__ == "__main__":
    unittest.main()
