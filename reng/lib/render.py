"""
HTML → MP4 rendering via the Hyperframes CLI.

Resolves the CLI in this order:

1. Explicit ``cli=`` argument to ``render()``.
2. ``HYPERFRAMES_CLI`` env: if it points to a ``.js`` file, run
   ``node <path> render <dir>`` (legacy monorepo build). Otherwise run that
   executable with ``render -o <dir>/out.mp4 <dir>`` (wrapper or npm binary).
3. ``<repo>/node_modules/.bin/hyperframes`` (and a short walk upward from
   ``os.getcwd()`` so venv installs can still find a sibling checkout).
4. Legacy default ``~/hyperframes/packages/cli/dist/cli.js`` with the Node
   invocation.

The npm-installed Hyperframes CLI (v0.4+) expects ``render -o ...`` to pin
``out.mp4`` in the project directory; the engine still treats ``out.mp4`` as
the primary artifact path.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


class RenderError(RuntimeError):
    pass


def _legacy_default_js() -> Path:
    """Built Hyperframes monorepo CLI (clone + bun build)."""
    return Path.home() / "hyperframes" / "packages" / "cli" / "dist" / "cli.js"


def _candidate_repo_roots() -> list[Path]:
    """
    Directories that might contain ``node_modules/.bin/hyperframes``.

    Includes the parent of the installed ``reng`` package (editable checkout
    layout) and ancestors of the current working directory (so a project in a
    subfolder of the repo still resolves the repo-level install).
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        p = p.resolve()
        if p not in seen:
            seen.add(p)
            roots.append(p)

    # reng/lib/render.py -> …/reng -> …/repo_root
    here = Path(__file__).resolve()
    add(here.parents[2])

    cwd = Path.cwd().resolve()
    add(cwd)
    for i, parent in enumerate(cwd.parents):
        if i > 12:
            break
        add(parent)
    return roots


def _bundled_hyperframes_bin() -> Path | None:
    """First ``node_modules/.bin/hyperframes`` found on candidate roots."""
    name = "hyperframes.cmd" if os.name == "nt" else "hyperframes"
    for root in _candidate_repo_roots():
        candidate = root / "node_modules" / ".bin" / name
        if candidate.is_file():
            return candidate
    return None


def resolve_hyperframes_invocation(
    project_dir: Path,
    *,
    cli_override: str | None = None,
) -> tuple[list[str], Path]:
    """
    Build argv for ``subprocess`` and the expected ``out.mp4`` path.

    Returns:
        argv: full argument list including executable
        expected_out: primary output path (``<project_dir>/out.mp4``)
    """
    project_dir = project_dir.expanduser().resolve()
    expected_out = project_dir / "out.mp4"

    if cli_override:
        cli_raw = cli_override
    elif os.environ.get("HYPERFRAMES_CLI"):
        cli_raw = os.environ["HYPERFRAMES_CLI"]
    else:
        bundled = _bundled_hyperframes_bin()
        if bundled is not None:
            return (
                [
                    str(bundled),
                    "render",
                    "-o",
                    str(expected_out),
                    str(project_dir),
                ],
                expected_out,
            )
        cli_raw = str(_legacy_default_js())

    cli_path = Path(cli_raw).expanduser()
    if not cli_path.is_file():
        raise RenderError(
            f"Hyperframes CLI not found at {cli_path}. "
            "Run `npm install` at the recursive-animation-engine repo root, "
            "or set HYPERFRAMES_CLI to your hyperframes binary or legacy cli.js."
        )

    # Legacy monorepo: node …/cli.js render <dir> (writes out.mp4 per older CLI)
    if cli_path.suffix.lower() == ".js":
        return (
            ["node", str(cli_path), "render", str(project_dir)],
            expected_out,
        )

    # Custom executable or npm hyperframes binary
    return (
        [
            str(cli_path),
            "render",
            "-o",
            str(expected_out),
            str(project_dir),
        ],
        expected_out,
    )


def render(project_dir: str | Path, *, cli: str | None = None, timeout: float = 600.0) -> tuple[Path, float]:
    """
    Render a Hyperframes project directory to MP4.

    Returns (video_path, seconds_elapsed). The video is written by the
    CLI into the project directory (typically ``out.mp4``).

    Raises RenderError on any failure.
    """
    project_dir = Path(project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        raise RenderError(f"project directory not found: {project_dir}")

    try:
        argv, expected_out = resolve_hyperframes_invocation(
            project_dir,
            cli_override=cli,
        )
    except RenderError:
        raise
    except Exception as e:
        raise RenderError(str(e)) from e

    start = time.monotonic()
    try:
        subprocess.run(
            argv,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RenderError(f"render timed out after {timeout}s")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        raise RenderError(f"render failed: {stderr.strip() or 'unknown error'}")
    except FileNotFoundError as e:
        # argv[0] missing (e.g. node or hyperframes not on PATH)
        raise RenderError(f"executable not found: {e}")

    elapsed = time.monotonic() - start

    if expected_out.is_file():
        return expected_out, elapsed

    # Legacy / edge: scan project dir and renders/ for newest mp4
    mp4s = sorted(project_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    renders_dir = project_dir / "renders"
    if renders_dir.is_dir():
        mp4s += sorted(renders_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if mp4s:
        return mp4s[0], elapsed

    raise RenderError(f"render completed but no MP4 found in {project_dir}")
