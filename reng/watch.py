"""
Always-on progress viewer.

Tails the shared event log and pretty-prints each event as it arrives.
Run in a dedicated terminal while the engine is working — it's purely
a reader, safe to start/stop any time.

Usage:
    reng watch                       # tail default log
    reng watch --follow-run <id>     # only show events for one run
    reng watch --since 1h            # replay recent history then tail
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from .lib.events import DEFAULT_LOG


# Terminal color codes; disabled automatically if stdout isn't a TTY.
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def _dim(t: str)    -> str: return _c("2",   t)
def _red(t: str)    -> str: return _c("31",  t)
def _green(t: str)  -> str: return _c("32",  t)
def _yellow(t: str) -> str: return _c("33",  t)
def _blue(t: str)   -> str: return _c("34",  t)
def _cyan(t: str)   -> str: return _c("36",  t)
def _bold(t: str)   -> str: return _c("1",   t)


def _parse_since(spec: str) -> float:
    """Parse strings like '30s', '5m', '2h', '1d' to seconds."""
    m = re.fullmatch(r"(\d+)\s*([smhd])", spec.strip())
    if not m:
        raise ValueError(f"invalid --since value: {spec!r} (use e.g. 30s, 5m, 2h, 1d)")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _format_event(record: dict, run_filter: str | None) -> str | None:
    """Render one event record into a single pretty line."""
    run_id = record.get("run_id", "?")
    if run_filter and run_id != run_filter:
        return None

    ts = record.get("ts", 0.0)
    when = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    event = record.get("event", "?")
    run_short = run_id[:6]
    prefix = f"{_dim(when)} {_cyan(run_short)}"

    match event:
        case "run_start":
            return (f"{prefix} {_bold('▶ run start')}  "
                    f"{_dim(record.get('project_dir', ''))}  "
                    f"max={record.get('max_iterations', '?')}")

        case "iteration_start":
            i = record.get("iteration", "?")
            return f"{prefix} {_blue(f'■ iteration {i}')}"

        case "render_start":
            return f"{prefix}   {_dim('render…')}"

        case "render_done":
            sec = record.get("render_seconds", 0)
            video = Path(record.get("video_path", "")).name
            return f"{prefix}   {_green('✓ rendered')} {video} {_dim(f'({sec:.1f}s)')}"

        case "render_fail":
            return f"{prefix}   {_red('✗ render failed')} {record.get('error', '')}"

        case "verify_start":
            n = record.get("frames", 0)
            return f"{prefix}   {_dim(f'extracting {n} keyframe(s)…')}"

        case "vision_check":
            frame = Path(record.get("frame", "")).name
            result = record.get("result", "").strip().splitlines()[0] if record.get("result") else ""
            if len(result) > 100:
                result = result[:97] + "…"
            if record.get("passed"):
                return f"{prefix}     {_green('✓')} {frame} {_dim(result)}"
            return f"{prefix}     {_yellow('◦')} {frame} {result}"

        case "iteration_end":
            i = record.get("iteration", "?")
            if record.get("passed"):
                return f"{prefix} {_green(f'✓ iteration {i} passed')}"
            issues = record.get("issues", [])
            return f"{prefix} {_yellow(f'◦ iteration {i} — {len(issues)} issue(s)')}"

        case "run_end":
            status = record.get("status", "?")
            iters = record.get("iterations", "?")
            video = record.get("final_video")
            color = _green if status == "passed" else _yellow if status == "max_iterations" else _red
            tail = f" → {Path(video).name}" if video else ""
            return f"{prefix} {color(f'■ run {status}')} ({iters} iter){tail}"

    return f"{prefix} {_dim(event)}  {_dim(json.dumps({k: v for k, v in record.items() if k not in ('ts', 'run_id', 'event')}))}"


def _iter_lines_tail(path: Path, from_offset: int = 0):
    """Generator that yields new lines appended to a file, forever."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r", encoding="utf-8") as f:
        f.seek(from_offset)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.25)


def _replay(path: Path, since_seconds: float | None) -> int:
    """Dump past events newer than `since_seconds`. Returns file offset after replay."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return 0
    cutoff = time.time() - since_seconds if since_seconds else None
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None and rec.get("ts", 0) < cutoff:
                continue
            out = _format_event(rec, None)
            if out:
                print(out)
        return f.tell()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reng watch",
        description="Always-on progress viewer for the recursive animation engine",
    )
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG,
                        help=f"event log path (default: {DEFAULT_LOG})")
    parser.add_argument("--follow-run", metavar="RUN_ID",
                        help="show only events for the given run id")
    parser.add_argument("--since", metavar="DURATION",
                        help="replay history newer than e.g. 30s/5m/2h/1d before tailing")
    args = parser.parse_args(argv)

    log_path = Path(args.log).expanduser()
    since_s = _parse_since(args.since) if args.since else None

    print(_dim(f"reng watch — tailing {log_path}"))
    if args.follow_run:
        print(_dim(f"  filtering run_id = {args.follow_run}"))
    print()

    # Replay history first, then tail forever
    offset = _replay(log_path, since_s) if since_s else (log_path.stat().st_size if log_path.exists() else 0)

    try:
        for raw in _iter_lines_tail(log_path, from_offset=offset):
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            out = _format_event(rec, args.follow_run)
            if out:
                print(out, flush=True)
    except KeyboardInterrupt:
        print(_dim("\n(watch stopped)"))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
