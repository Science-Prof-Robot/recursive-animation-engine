"""
Keyframe extraction for visual verification.

Samples N evenly-spaced frames from the interior 10%..90% of an MP4,
avoiding black first/last frames. Uses ffmpeg via subprocess.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class VerifyError(RuntimeError):
    pass


def _probe_duration(video: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", str(video),
            ],
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise VerifyError("ffprobe not found -- install ffmpeg")
    except subprocess.CalledProcessError as e:
        raise VerifyError(f"ffprobe failed: {e.stderr.decode(errors='replace')}")

    try:
        return float(json.loads(out)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise VerifyError(f"could not parse ffprobe output: {out!r}")


def _extract(video: Path, at_seconds: float, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_seconds:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        raise VerifyError("ffmpeg not found -- install ffmpeg")
    except subprocess.CalledProcessError as e:
        raise VerifyError(
            f"ffmpeg failed at {at_seconds}s: {e.stderr.decode(errors='replace')}"
        )


def extract_keyframes(video: str | Path, frames: int = 3) -> list[Path]:
    """
    Extract `frames` evenly-spaced keyframes from the video's interior.

    Returns a list of PNG file paths written next to the video.
    """
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise VerifyError(f"video not found: {video}")

    duration = _probe_duration(video)
    if duration <= 0:
        raise VerifyError(f"video has invalid duration: {duration}s")

    n = max(2, frames)
    # Sample inside the 10%..90% window so we never hit a fade-in/fade-out
    ratios = [0.1 + (0.8 * i / (n - 1)) for i in range(n)]

    paths: list[Path] = []
    for i, ratio in enumerate(ratios, start=1):
        ts = duration * ratio
        out = video.parent / f"{video.stem}_frame{i:02d}.png"
        _extract(video, ts, out)
        paths.append(out)

    return paths
