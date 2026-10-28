from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import tempfile

from .config import MAX_SEGMENT_DURATION
from .layout import BACKGROUND, LAYOUT_VERSION, create_overlay, geometry
from .publication import write_publication_files
from .utils import safe_filename


def probe_video(video_path, settings):
    try:
        result = subprocess.run(
            [settings.ffprobe, "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,duration", "-of", "json", str(video_path)],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "")[-2000:]
        raise RuntimeError(f"Analyse vidéo impossible : {video_path} : {detail}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Délai d'analyse vidéo dépassé : {video_path}") from error
    except OSError as error:
        raise RuntimeError(f"FFprobe indisponible : {error}") from error
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = float(data.get("format", {}).get("duration") or video.get("duration", 0))
        width, height = int(video["width"]), int(video["height"])
        if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
            raise ValueError("Métadonnées vidéo invalides")
    except (ValueError, TypeError, KeyError, StopIteration, AttributeError) as error:
        raise ValueError(f"Vidéo illisible ou métadonnées invalides : {video_path}") from error
    return {
        "duration": duration, "width": width, "height": height,
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
    }


def process_video(video_path, run, settings, start_time=0, end_time=None):
    if not isinstance(start_time, (int, float)) or not math.isfinite(start_time) or start_time < 0:
        raise ValueError("Le début de la vidéo doit être positif et fini.")
    if end_time is not None and (
        not isinstance(end_time, (int, float)) or not math.isfinite(end_time) or end_time <= start_time
    ):
        raise ValueError("La fin de la vidéo doit être finie et supérieure au début.")
    if (
        not isinstance(settings.segment_duration, (int, float))
        or not math.isfinite(settings.segment_duration)
        or not 0 < settings.segment_duration <= MAX_SEGMENT_DURATION
    ):
        raise ValueError(f"La durée des segments doit être positive et ne pas dépasser {MAX_SEGMENT_DURATION} secondes.")
    if settings.width < 2 or settings.height < 2 or settings.width % 2 or settings.height % 2 or settings.fps <= 0:
        raise ValueError("Dimensions paires et fréquence positives requises.")
    video_path = Path(video_path).resolve(strict=True)
    source_stat = video_path.stat()
    source = probe_video(video_path, settings)
    end = source["duration"] if end_time is None else end_time
    if end > source["duration"]:
        raise ValueError("La fin demandée dépasse la durée de la vidéo.")
    duration = end - start_time
    if duration <= 0:
        raise ValueError("Le début demandé dépasse la durée de la vidéo.")
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    identifier = safe_filename(run.run_id)
    destination = output_dir / f"run-{identifier}"
    part_count = math.ceil(duration / settings.segment_duration)
    expected_segments = [f"{identifier}-part-{part:02d}.mp4" for part in range(1, part_count + 1)]
    render_spec = {
        "layout": LAYOUT_VERSION, "font": settings.font,
        "width": settings.width, "height": settings.height, "fps": settings.fps,
        "segment_duration": settings.segment_duration, "start_time": start_time, "end_time": end_time,
        "source": str(video_path), "source_size": source_stat.st_size, "source_mtime_ns": source_stat.st_mtime_ns,
    }
    if destination.exists():
        try:
            metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
            complete = (
                metadata.get("run") == asdict(run) and metadata.get("render") == render_spec
                and metadata.get("segments") == expected_segments
                and all((destination / name).is_file() and (destination / name).stat().st_size > 0 for name in expected_segments)
                and (destination / "description.txt").is_file() and (destination / "description.txt").stat().st_size > 0
            )
        except (OSError, ValueError, AttributeError):
            complete = False
        if complete:
            return destination
        raise FileExistsError(f"Le dossier de rendu existe déjà : {destination}")
    x, y, width, height = geometry(settings)
    filter_graph = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1,"
        f"pad={settings.width}:{settings.height}:{x}+({width}-iw)/2:{y}+({height}-ih)/2:color=0x{BACKGROUND[1:]},"
        f"setsar=1[game];[game][1:v]overlay=0:0:shortest=1,format=yuv420p[video]"
    )
    with tempfile.TemporaryDirectory(prefix=".render-", dir=output_dir) as temporary:
        staging = Path(temporary)
        segments = []
        for part in range(1, part_count + 1):
            offset = (part - 1) * settings.segment_duration
            part_duration = min(settings.segment_duration, duration - offset)
            overlay = create_overlay(run, settings, part, part_count, staging / f"overlay-{part}.png")
            output = staging / f"{identifier}-part-{part:02d}.mp4"
            command = [
                settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-ss", f"{start_time + offset:.6f}", "-i", str(video_path),
                "-loop", "1", "-i", str(overlay), "-filter_complex", filter_graph,
                "-map", "[video]", "-map", "0:a?", "-t", f"{part_duration:.6f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-r", str(settings.fps), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                str(output),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or "")[-2000:]
                raise RuntimeError(f"Échec du rendu de la partie {part}/{part_count} : {detail}") from error
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError(f"FFmpeg n'a pas produit la partie {part}/{part_count}.")
            rendered_duration = probe_video(output, settings)["duration"]
            if rendered_duration > MAX_SEGMENT_DURATION:
                raise RuntimeError(
                    f"La partie {part}/{part_count} dure {rendered_duration:.6f} secondes, "
                    f"au-delà du plafond de {MAX_SEGMENT_DURATION} secondes."
                )
            segments.append(output)
            overlay.unlink()
        write_publication_files(run, staging, segments, render_spec)
        staging.rename(destination)
    return destination
