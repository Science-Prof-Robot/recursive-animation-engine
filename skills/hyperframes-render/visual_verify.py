#!/usr/bin/env python3
"""
Keyframe extractor for the hyperframes-render self-correction loop.

Given an MP4, extracts 3 representative keyframes (10%, 50%, 90% of
duration) to PNG files next to the video. Prints the resulting paths,
one per line, so the agent can feed them into the vision skill.

Usage:
    python visual_verify.py <video.mp4>
    python visual_verify.py <video.mp4> --frames 5

Requires ffmpeg on PATH.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def fail(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def ffprobe_duration(video: Path) -> float:
    """Return the video's duration in seconds via ffprobe."""
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
        fail("ffprobe not found -- install ffmpeg and ensure it's on PATH")
    except subprocess.CalledProcessError as e:
        fail(f"ffprobe failed: {e.stderr.decode(errors='replace')}")

    data = json.loads(out)
    try:
        return float(data["format"]["duration"])
    except (KeyError, ValueError):
        fail(f"Could not parse duration from ffprobe output: {out!r}")


def extract_frame(video: Path, at_seconds: float, out_path: Path) -> None:
    """Extract a single frame at the given timestamp to out_path."""
    # -ss before -i is fast seek; good enough for keyframe sampling
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_seconds:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "2",  # high quality JPEG-equivalent for PNG
        "-y",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        fail("ffmpeg not found -- install ffmpeg and ensure it's on PATH")
    except subprocess.CalledProcessError as e:
        fail(f"ffmpeg failed at {at_seconds}s: {e.stderr.decode(errors='replace')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="path to MP4 file")
    parser.add_argument(
        "--frames", type=int, default=3,
        help="number of keyframes to extract (default 3: start/middle/end)",
    )
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        fail(f"video not found: {video}")

    duration = ffprobe_duration(video)
    if duration <= 0:
        fail(f"video has invalid duration: {duration}s")

    # Sample evenly in the interior 10%..90% window so we never pick
    # a black first/last frame.
    n = max(2, args.frames)
    ratios = [0.1 + (0.8 * i / (n - 1)) for i in range(n)]

    out_paths: list[Path] = []
    for i, ratio in enumerate(ratios, start=1):
        ts = duration * ratio
        out_path = video.parent / f"{video.stem}_frame{i:02d}.png"
        extract_frame(video, ts, out_path)
        out_paths.append(out_path)

    for p in out_paths:
        print(p)


if __name__ == "__main__":
    main()
