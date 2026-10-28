import unittest

from speedrun.utils import extract_game_id_from_url, format_duration, get_video_id_from_url, safe_filename


class UrlTests(unittest.TestCase):
    def test_supported_video_urls(self):
        cases = (
            ("https://www.youtube.com/watch?v=abc&list=xyz", "abc"),
            ("https://youtu.be/abc?t=2", "abc"),
            ("https://youtube.com/shorts/abc", "abc"),
            ("https://youtube.com/embed/abc", "abc"),
            ("https://www.twitch.tv/videos/1234", "v1234"),
            ("https://www.twitch.tv/player/clip/example", "example"),
            ("https://clips.twitch.tv/example", "example"),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(get_video_id_from_url(url), expected)

    def test_invalid_and_fake_domains_are_rejected(self):
        for url in (
            None, "https://youtube.com/watch", "https://youtu.be/",
            "https://youtube.com.evil.example/watch?v=abc", "https://evil.example/youtube.com/abc",
            "file://youtube.com/watch?v=abc", "https://[invalid"
        ):
            with self.subTest(url=url):
                self.assertIsNone(get_video_id_from_url(url))

    def test_game_locale_trailing_slash_and_query(self):
        self.assertEqual(extract_game_id_from_url("https://www.speedrun.com/fr-FR/example/?x=1"), "example")
        for url in ("https://speedrun.com/", "https://speedrun.com/fr-FR/", "https://example.com/game", "https://speedrun.com/game/runs"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                extract_game_id_from_url(url)


class FormattingTests(unittest.TestCase):
    def test_windows_filename_limits(self):
        self.assertEqual(safe_filename('joueur\\jeu/:*?"<>|\x00\n. '), 'joueurjeu')
        self.assertEqual(safe_filename(' /:. '), 'video')
        self.assertEqual(safe_filename('CON'), '_CON')
        self.assertEqual(safe_filename('LPT1.txt'), '_LPT1.txt')
        self.assertLessEqual(len(safe_filename('a' * 200)), 100)

    def test_official_timer_preserves_milliseconds_and_rolls_over(self):
        for value, expected in ((31, "0:31.000"), (59.9999, "1:00.000"), (3661.234, "1:01:01.234")):
            with self.subTest(value=value):
                self.assertEqual(format_duration(value), expected)
        for value in (-1, float('nan'), float('inf'), "31"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                format_duration(value)
