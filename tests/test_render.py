from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from speedrun.config import Settings
from speedrun.layout import LAYOUT_VERSION, create_overlay, geometry
from speedrun.models import Run
from speedrun.render import probe_video, process_video


def example_run(**changes):
    run = Run(
        run_id='abcd1234', game_id='game', category_id='category',
        game_name='Jeu de précision', category_name='Any% — sans raccourci',
        player_name='Émilie', country='Unknown', date='2026-10-28',
        video_url='https://youtu.be/example', run_link='https://www.speedrun.com/runs/abcd1234',
        player_profile_link='https://www.speedrun.com/user/example', duration=42.125,
    )
    return replace(run, **changes)


class ProbeTests(unittest.TestCase):
    def test_reads_video_dimensions_duration_and_optional_audio(self):
        for audio in [False, True]:
            with self.subTest(audio=audio):
                streams = [{'codec_type': 'video', 'width': 1920, 'height': 1080}]
                if audio:
                    streams.append({'codec_type': 'audio'})
                result = subprocess.CompletedProcess([], 0, json.dumps({'format': {'duration': '90.5'}, 'streams': streams}))
                with patch('speedrun.render.subprocess.run', return_value=result) as execute:
                    self.assertEqual(probe_video('source.mp4', Settings()), {
                        'duration': 90.5, 'width': 1920, 'height': 1080, 'has_audio': audio,
                    })
                self.assertEqual(execute.call_args.kwargs['timeout'], 30)

    def test_rejects_malformed_or_missing_video_metadata(self):
        for payload in ['not json', '{}', '{"streams": []}', json.dumps({
            'streams': [{'codec_type': 'video', 'width': 0, 'height': 1080}],
            'format': {'duration': 'nan'},
        })]:
            with self.subTest(payload=payload):
                with patch('speedrun.render.subprocess.run', return_value=subprocess.CompletedProcess([], 0, payload)):
                    with self.assertRaisesRegex(ValueError, 'métadonnées invalides'):
                        probe_video('source.mp4', Settings())

    def test_probe_failures_are_reported_as_actionable_errors(self):
        errors = [
            subprocess.CalledProcessError(1, ['ffprobe'], stderr='invalid source'),
            subprocess.TimeoutExpired(['ffprobe'], 30), FileNotFoundError('ffprobe'),
        ]
        for error in errors:
            with self.subTest(error=error):
                with patch('speedrun.render.subprocess.run', side_effect=error):
                    with self.assertRaises(RuntimeError):
                        probe_video('source.mp4', Settings())


class RenderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'source video')
        self.output_dir = self.root / 'output'
        self.settings = Settings(output_dir=self.output_dir, flags_dir=self.root / 'flags')
        self.run = example_run()

    @staticmethod
    def overlay(run, settings, part, total, path):
        Path(path).write_bytes(b'overlay')
        return Path(path)

    @staticmethod
    def encode(command, **kwargs):
        Path(command[-1]).write_text(command[command.index('-t') + 1], encoding='ascii')
        return subprocess.CompletedProcess(command, 0)

    def render(self, source_duration=120, **kwargs):
        def probe(path, settings):
            duration = source_duration if Path(path) == self.source else float(Path(path).read_text(encoding='ascii'))
            return {'duration': duration, 'width': 1920, 'height': 1080, 'has_audio': False}

        with patch('speedrun.render.probe_video', side_effect=probe):
            with patch('speedrun.render.create_overlay', side_effect=self.overlay):
                return process_video(self.source, self.run, self.settings, **kwargs)

    def test_encodes_all_segments_with_safe_vertical_settings(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode) as execute:
            folder = self.render()
        self.assertEqual(folder.name, 'run-abcd1234')
        self.assertEqual(len(list(folder.glob('*.mp4'))), 3)
        self.assertEqual(len(list(folder.iterdir())), 5)
        metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['run']['run_id'], self.run.run_id)
        self.assertEqual(len(metadata['segments']), 3)
        self.assertEqual(metadata['render']['layout'], LAYOUT_VERSION)
        self.assertEqual(metadata['render']['font'], self.settings.font)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertEqual([command[command.index('-ss') + 1] for command in commands], ['0.000000', '59.000000', '118.000000'])
        self.assertEqual([command[command.index('-t') + 1] for command in commands], ['59.000000', '59.000000', '2.000000'])
        graph = commands[0][commands[0].index('-filter_complex') + 1]
        self.assertIn('force_original_aspect_ratio=decrease', graph)
        self.assertIn('reset_sar=1', graph)
        self.assertNotIn('crop', graph)
        self.assertIn('pad=1080:1920', graph)
        self.assertIn('0:a?', commands[0])
        self.assertIn('+faststart', commands[0])
        self.assertIn('yuv420p', commands[0])

    def test_start_time_applies_to_each_segment(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode) as execute:
            self.render(start_time=15)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertEqual([command[command.index('-ss') + 1] for command in commands], ['15.000000', '74.000000'])
        self.assertEqual([command[command.index('-t') + 1] for command in commands], ['59.000000', '46.000000'])

    def test_manual_range_limits_every_segment_to_the_requested_video_interval(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode) as execute:
            folder = self.render(start_time=10, end_time=100)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertEqual([command[command.index('-ss') + 1] for command in commands], ['10.000000', '69.000000'])
        self.assertEqual([command[command.index('-t') + 1] for command in commands], ['59.000000', '31.000000'])
        metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['render']['end_time'], 100)
        self.assertEqual(metadata['run']['duration'], self.run.duration)

    def test_encoder_failure_discards_staging_and_preserves_existing_outputs(self):
        old = self.output_dir / 'other-run'
        old.mkdir(parents=True)
        original = old / 'original.mp4'
        original.write_bytes(b'original')
        attempts = []

        def encode(command, **kwargs):
            attempts.append(command)
            if len(attempts) == 2:
                raise subprocess.CalledProcessError(1, command, stderr='encoder failed')
            return self.encode(command, **kwargs)

        with patch('speedrun.render.subprocess.run', side_effect=encode):
            with self.assertRaisesRegex(RuntimeError, 'partie 2/3.*encoder failed'):
                self.render()
        self.assertEqual(original.read_bytes(), b'original')
        self.assertEqual(list(self.output_dir.iterdir()), [old])

    def test_existing_destination_is_never_overwritten(self):
        existing = self.output_dir / 'run-abcd1234'
        existing.mkdir(parents=True)
        original = existing / 'original.mp4'
        original.write_bytes(b'original')
        with patch('speedrun.render.subprocess.run') as execute:
            with self.assertRaises(FileExistsError):
                self.render()
        execute.assert_not_called()
        self.assertEqual(original.read_bytes(), b'original')

    def test_missing_encoder_output_is_an_error(self):
        with patch('speedrun.render.subprocess.run', return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(RuntimeError, "n'a pas produit"):
                self.render()
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_publication_failure_does_not_publish_a_partial_output(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode):
            with patch('speedrun.render.write_publication_files', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    self.render()
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_completed_identical_render_is_reused(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode):
            folder = self.render()
        with patch('speedrun.render.subprocess.run') as execute:
            self.assertEqual(self.render(), folder)
        execute.assert_not_called()

    def test_old_layout_or_other_font_is_never_reused(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode):
            folder = self.render()
        metadata_path = folder / 'metadata.json'
        original = json.loads(metadata_path.read_text(encoding='utf-8'))
        for field, value in (('layout', 'previous-layout'), ('font', 'another-font.ttf')):
            with self.subTest(field=field):
                metadata = {**original, 'render': {**original['render'], field: value}}
                content = json.dumps(metadata)
                metadata_path.write_text(content, encoding='utf-8')
                with patch('speedrun.render.subprocess.run') as execute:
                    with self.assertRaises(FileExistsError):
                        self.render()
                execute.assert_not_called()
                self.assertEqual(metadata_path.read_text(encoding='utf-8'), content)

    def test_changed_render_settings_are_not_reused(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode):
            folder = self.render()
        original = (folder / 'metadata.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.render(start_time=1)
        with self.assertRaises(FileExistsError):
            self.render(end_time=119)
        self.settings = replace(self.settings, width=720, height=1280)
        with self.assertRaises(FileExistsError):
            self.render()
        self.assertEqual((folder / 'metadata.json').read_bytes(), original)

    def test_missing_segment_is_never_reused(self):
        with patch('speedrun.render.subprocess.run', side_effect=self.encode):
            folder = self.render()
        next(folder.glob('*.mp4')).unlink()
        with self.assertRaises(FileExistsError):
            self.render()

    def test_invalid_timing_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(start_time=120)
        with self.assertRaises(ValueError):
            self.render(start_time=-1)
        self.settings = replace(self.settings, segment_duration=0)
        with self.assertRaises(ValueError):
            self.render()

    def test_invalid_manual_ranges_are_rejected_before_creating_outputs(self):
        for start, end in [(0, 121), (10, 10), (10, 9), (0, 0), (0, float('nan')), (0, float('inf')), (0, '100')]:
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    self.render(start_time=start, end_time=end)
        self.assertFalse(self.output_dir.exists())

    def test_platform_segment_limit_applies_to_direct_render_calls(self):
        self.settings = replace(self.settings, segment_duration=181)
        with self.assertRaisesRegex(ValueError, '180 secondes'):
            self.render()
        self.assertFalse(self.output_dir.exists())

    def test_encoded_duration_above_platform_limit_is_never_published(self):
        def oversized_output(command, **kwargs):
            Path(command[-1]).write_text('180.001', encoding='ascii')
            return subprocess.CompletedProcess(command, 0)

        with patch('speedrun.render.subprocess.run', side_effect=oversized_output):
            with patch('speedrun.render.write_publication_files') as publish:
                with self.assertRaisesRegex(RuntimeError, 'partie 1/3.*180.001000.*plafond de 180'):
                    self.render()
        publish.assert_not_called()
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_exact_platform_limit_is_allowed(self):
        self.settings = replace(self.settings, segment_duration=180)
        with patch('speedrun.render.subprocess.run', side_effect=self.encode) as execute:
            self.render(source_duration=400, start_time=20, end_time=380)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertEqual([command[command.index('-ss') + 1] for command in commands], ['20.000000', '200.000000'])
        self.assertEqual([command[command.index('-t') + 1] for command in commands], ['180.000000', '180.000000'])


class LayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings(flags_dir=self.root)

    def test_overlay_keeps_gameplay_clear_and_contains_unicode_metadata(self):
        run = example_run(game_name='Épopée très longue ' * 12, player_name='Émilie œuf à Noël')
        path = create_overlay(run, self.settings, 1, 2, self.root / 'overlay.png')
        x, y, width, height = geometry(self.settings)
        with Image.open(path) as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getchannel('A').crop((x, y, x + width, y + height)).getextrema(), (0, 0))
            self.assertEqual(image.getpixel((64, 1500))[3], 255)
            self.assertEqual(image.getpixel((1000, 1850)), (13, 15, 18, 255))

    def test_long_unicode_and_cooperative_names_keep_gameplay_clear_at_both_sizes(self):
        run = example_run(
            game_name='Épopée très longue à travers les étoiles ' * 10,
            category_name='World 1 — Any% — Level: 1-6 — Édition spéciale ' * 8,
            player_name='Émilie œuf à Noël & François & Zoë & Łukasz ' * 8,
        )
        for width, height in ((1080, 1920), (720, 1280)):
            with self.subTest(width=width):
                settings = replace(self.settings, width=width, height=height)
                path = create_overlay(run, settings, 2, 3, self.root / f'overlay-{width}.png')
                x, y, game_width, game_height = geometry(settings)
                with Image.open(path) as image:
                    self.assertEqual(image.size, (width, height))
                    self.assertEqual(image.mode, 'RGBA')
                    gameplay_alpha = image.getchannel('A').crop((x, y, x + game_width, y + game_height))
                    self.assertEqual(gameplay_alpha.getextrema(), (0, 0))

    def test_real_country_flag_is_used_without_a_converter_for_png(self):
        Image.new('RGB', (68, 44), '#ff0000').save(self.root / 'fr.png')
        with patch('speedrun.layout.subprocess.run') as execute:
            path = create_overlay(example_run(country='fr'), self.settings, 1, 1, self.root / 'overlay.png')
        execute.assert_not_called()
        with Image.open(path) as image:
            self.assertEqual(image.getpixel((70, 1510)), (255, 0, 0, 255))

    def test_svg_conversion_failure_keeps_video_overlay_usable(self):
        (self.root / 'fr.svg').write_text('<svg/>', encoding='utf-8')
        with patch('speedrun.layout.subprocess.run', side_effect=FileNotFoundError('magick')):
            with self.assertLogs('speedrun.layout', level='WARNING'):
                path = create_overlay(example_run(country='fr'), self.settings, 1, 1, self.root / 'overlay.png')
        self.assertTrue(path.is_file())
