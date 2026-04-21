"""
HTML → MP4 rendering via the Hyperframes CLI.

Thin wrapper that shells out to `node <cli.js> render <project_dir>`.
Keeps the core engine independent of the renderer, so you can swap in
Remotion, Manim, Playwright-based recording, etc. by replacing this
module's `render()` function.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


class RenderError(RuntimeError):
    pass


def _default_cli() -> str:
    """Default location for the built Hyperframes CLI."""
    return os.environ.get(
        "HYPERFRAMES_CLI",
        str(Path.home() / "hyperframes" / "packages" / "cli" / "dist" / "cli.js"),
    )


def render(project_dir: str | Path, *, cli: str | None = None, timeout: float = 600.0) -> tuple[Path, float]:
    """
    Render a Hyperframes project directory to MP4.

    Returns (video_path, seconds_elapsed). The video is written by the
    CLI into the project directory (typically `out.mp4`).

    Raises RenderError on any failure.
    """
    project_dir = Path(project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        raise RenderError(f"project directory not found: {project_dir}")

    cli_path = cli or _default_cli()
    if not Path(cli_path).is_file():
        raise RenderError(
            f"Hyperframes CLI not found at {cli_path}. "
            "Set HYPERFRAMES_CLI or clone + build the hyperframes repo."
        )

    start = time.monotonic()
    try:
        subprocess.run(
            ["node", cli_path, "render", str(project_dir)],
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RenderError(f"render timed out after {timeout}s")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        raise RenderError(f"render failed: {stderr.strip() or 'unknown error'}")
    except FileNotFoundError:
        raise RenderError("`node` not found on PATH")

    elapsed = time.monotonic() - start

    # Hyperframes conventionally writes out.mp4 in the project dir
    out = project_dir / "out.mp4"
    if not out.is_file():
        # Fall back to scanning for any recent mp4 in the project dir
        mp4s = sorted(project_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not mp4s:
            raise RenderError(f"render completed but no MP4 found in {project_dir}")
        out = mp4s[0]

    return out, elapsed
