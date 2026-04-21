"""
Main CLI entry point.

Subcommands:
    reng render  <project_dir>     run the recursive engine once
    reng watch                     always-on progress viewer
    reng vision  <image> <q>       standalone single-image analysis
    reng verify  <video>           standalone keyframe extraction
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .lib.engine import run as engine_run
from .lib.verify import extract_keyframes
from .lib.vision import analyze
from .watch import main as watch_main


def _cmd_render(args) -> int:
    result = engine_run(
        args.project_dir,
        intent=args.intent or "",
        max_iterations=args.max_iterations,
        frames=args.frames,
    )
    print(f"\nStatus: {result.status}")
    print(f"Iterations: {len(result.iterations)}")
    if result.final_video:
        print(f"Final video: {result.final_video}")
    if result.status != "passed":
        for it in result.iterations:
            for issue in it.issues:
                print(f"  [iter {it.iteration}] {issue}")
    return 0 if result.status in ("passed", "max_iterations") else 1


def _cmd_watch(args) -> int:
    remaining = []
    if args.log:
        remaining += ["--log", str(args.log)]
    if args.follow_run:
        remaining += ["--follow-run", args.follow_run]
    if args.since:
        remaining += ["--since", args.since]
    return watch_main(remaining)


def _cmd_vision(args) -> int:
    try:
        print(analyze(args.image, args.question))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_verify(args) -> int:
    try:
        frames = extract_keyframes(args.video, frames=args.frames)
        for f in frames:
            print(f)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reng",
        description="Recursive Animation Engine — render, verify, iterate",
    )
    parser.add_argument("--version", action="version", version=f"reng {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # render
    p_render = sub.add_parser("render", help="Run the recursive engine on a project")
    p_render.add_argument("project_dir", help="path to a Hyperframes project directory")
    p_render.add_argument("--intent", help="free-text description of user intent")
    p_render.add_argument("--max-iterations", type=int, default=3)
    p_render.add_argument("--frames", type=int, default=3,
                          help="keyframes per verification pass")
    p_render.set_defaults(func=_cmd_render)

    # watch
    p_watch = sub.add_parser("watch", help="Always-on progress viewer")
    p_watch.add_argument("--log")
    p_watch.add_argument("--follow-run")
    p_watch.add_argument("--since")
    p_watch.set_defaults(func=_cmd_watch)

    # vision
    p_vision = sub.add_parser("vision", help="Single-shot image analysis")
    p_vision.add_argument("image", help="path to an image file")
    p_vision.add_argument("question", help="what to ask about the image")
    p_vision.set_defaults(func=_cmd_vision)

    # verify
    p_verify = sub.add_parser("verify", help="Extract keyframes from a video")
    p_verify.add_argument("video", help="path to an MP4 file")
    p_verify.add_argument("--frames", type=int, default=3)
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
