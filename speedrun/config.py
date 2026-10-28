from dataclasses import dataclass
import os
from pathlib import Path
import shutil


BASE_DIR = Path(__file__).resolve().parent.parent
MAX_SEGMENT_DURATION = 180


def find_binary(environment_name, executable):
    configured = os.environ.get(environment_name)
    if configured:
        return configured
    available = shutil.which(executable)
    if available:
        return available
    local = BASE_DIR / ".tools" / f"{executable}.exe"
    if executable == "magick" and not local.is_file():
        local = BASE_DIR / ".tools" / "imagemagick" / "magick.exe"
    return str(local) if local.is_file() else executable


@dataclass(frozen=True)
class Settings:
    game_urls_file: Path = BASE_DIR / "game_urls.txt"
    game_rules_file: Path = BASE_DIR / "game_rules.json"
    history_file: Path = BASE_DIR / "used_runs_db.json"
    download_dir: Path = BASE_DIR / "Video_download"
    output_dir: Path = BASE_DIR / "Video_final"
    flags_dir: Path = BASE_DIR / "flags"
    ffmpeg: str = find_binary("FFMPEG_BINARY", "ffmpeg")
    ffprobe: str = find_binary("FFPROBE_BINARY", "ffprobe")
    imagemagick: str = find_binary("IMAGEMAGICK_BINARY", "magick")
    font: str | None = os.environ.get("SPEEDRUN_FONT")
    min_duration: float = 20
    max_duration: float = 300
    levels_only: bool = False
    segment_duration: float = 59
    max_videos: int = 3
    top: int = 3
    width: int = 1080
    height: int = 1920
    fps: int = 30
