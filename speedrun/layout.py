from io import BytesIO
import logging
import os
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

from .utils import format_duration


BACKGROUND = '#0D0F12'
ACCENT = '#DFFF00'
FOREGROUND = '#F4F5ED'
MUTED = '#A5ADB8'
LAYOUT_VERSION = 'broadcast-2026-01'


def geometry(settings):
    return tuple(int(value / 2) * 2 for value in (
        settings.width * (48 / 1080), settings.height * (500 / 1920),
        settings.width * 0.9, settings.height * (930 / 1920),
    ))


def _font(settings, size, bold=False, mono=False):
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    filename = 'consolab.ttf' if mono else 'segoeuib.ttf' if bold else 'segoeui.ttf'
    candidates = [settings.font, fonts_dir / filename, "DejaVuSansMono.ttf" if mono else "DejaVuSans.ttf"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width):
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        remaining = paragraph.strip()
        while remaining:
            low, high = 1, len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                if draw.textlength(remaining[:middle], font=font) <= width:
                    low = middle
                else:
                    high = middle - 1
            length = low
            if length < len(remaining):
                space = remaining.rfind(' ', 0, length + 1)
                if space > 0:
                    length = space
            lines.append(remaining[:length])
            remaining = remaining[length:].lstrip()
    return lines or [""]


def _text(draw, text, box, settings, size, minimum, color, max_lines=2, bold=False, mono=False):
    x, y, width, height = box
    for font_size in range(max(1, size), max(0, minimum - 1), -1):
        font = _font(settings, font_size, bold, mono)
        lines = _wrap(draw, text, font, width)
        spacing = max(2, font_size // 6)
        bounds = draw.multiline_textbbox((0, 0), '\n'.join(lines), font=font, spacing=spacing)
        if len(lines) <= max_lines and bounds[3] - bounds[1] <= height:
            break
    visible = lines[:max_lines]
    while len(visible) > 1:
        bounds = draw.multiline_textbbox((0, 0), '\n'.join(visible), font=font, spacing=spacing)
        if bounds[3] - bounds[1] <= height:
            break
        visible.pop()
    if len(visible) < len(lines):
        lines = visible
        last = lines[-1]
        while last and draw.textlength(last + '…', font=font) > width:
            last = last[:-1]
        lines[-1] = last + '…'
    content = '\n'.join(lines)
    bounds = draw.multiline_textbbox((0, 0), content, font=font, spacing=spacing)
    draw.multiline_text((x - bounds[0], y - bounds[1]), content, font=font, fill=color, spacing=spacing)


def _flag(country, settings, size):
    code = (country or '').lower().split('/')[0]
    if not re.fullmatch(r'[a-z]{2}', code):
        return None, '—'
    for extension in ('png', 'svg'):
        path = Path(settings.flags_dir) / f"{code}.{extension}"
        if not path.is_file():
            continue
        try:
            source = path
            if extension == 'svg':
                result = subprocess.run(
                    [settings.imagemagick, "-background", "none", str(path), "-resize", f"{size[0]}x{size[1]}", "png:-"],
                    check=True, capture_output=True, timeout=15,
                )
                source = BytesIO(result.stdout)
            with Image.open(source) as image:
                flag = image.convert('RGBA')
            bounds = flag.getbbox()
            if bounds:
                flag = flag.crop(bounds)
            flag.thumbnail(size, Image.Resampling.LANCZOS)
            return flag, code.upper()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            logging.getLogger(__name__).warning("Drapeau %s indisponible : %s", code.upper(), error)
    return None, code.upper()


def create_overlay(run, settings, part, total, output_path):
    if part < 1 or total < part:
        raise ValueError("Numéro de partie invalide")
    width, height = settings.width, settings.height
    sx, sy = width / 1080, height / 1920
    image = Image.new('RGBA', (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    def box(x, y, w, h):
        return int(x * sx), int(y * sy), int(w * sx), int(h * sy)

    def text(value, bounds, size, minimum, color, max_lines=2, bold=False, mono=False):
        _text(draw, value, box(*bounds), settings, max(1, int(size * sx)), max(1, int(minimum * sx)), color, max_lines, bold, mono)

    text('SPEEDRUN', (64, 94, 440, 40), 30, 24, FOREGROUND, 1, True)
    draw.rounded_rectangle(
        (int(748 * sx), int(82 * sy), int(964 * sx), int(140 * sy)),
        radius=max(1, int(6 * sx)), fill=ACCENT,
    )
    text(f"RANG #{run.rank}", (770, 98, 172, 34), 27, 20, BACKGROUND, 1, True)
    text(run.game_name, (64, 190, 900, 216), 86, 42, FOREGROUND, 2, True)
    text(run.category_name, (64, 428, 900, 64), 32, 22, MUTED, 2)

    x, y, game_width, game_height = geometry(settings)
    draw.rectangle((x, y, x + game_width - 1, y + game_height - 1), fill=(0, 0, 0, 0))

    text('LE JOUEUR', (64, 1458, 600, 30), 23, 18, MUTED, 1)
    flag_size = max(1, int(72 * sx)), max(1, int(48 * sy))
    flag, country = _flag(run.country, settings, flag_size)
    if flag is not None:
        image.alpha_composite(flag, (int(64 * sx), int(1502 * sy)))
        flag.close()
    else:
        text(country, (64, 1504, 72, 42), 27, 18, MUTED, 1, True)
    text(run.player_name, (160, 1494, 804, 88), 58, 28, FOREGROUND, 2, True)

    draw.rounded_rectangle(
        (int(64 * sx), int(1606 * sy), int(964 * sx), int(1772 * sy)),
        radius=max(1, int(8 * sx)), fill=ACCENT,
    )
    text('TEMPS OFFICIEL', (88, 1626, 550, 30), 23, 18, BACKGROUND, 1, True)
    text(format_duration(run.duration), (80, 1668, 574, 86), 88, 40, BACKGROUND, 1, True, True)
    text(f"PARTIE {part:02d}/{total:02d}", (704, 1640, 236, 40), 27, 20, BACKGROUND, 1, True)
    text(run.date or 'Date inconnue', (704, 1700, 236, 32), 24, 18, BACKGROUND, 1)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format='PNG')
    image.close()
    return output_path
