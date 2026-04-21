"""
Append-only event log for the recursive animation engine.

The engine writes progress events as NDJSON lines to a shared log file.
The `reng watch` CLI tails that file and pretty-prints in real time.

File-based so multiple processes can observe without any IPC or pubsub.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


DEFAULT_LOG = Path(os.environ.get(
    "RENG_EVENT_LOG",
    str(Path.home() / ".recursive-animation-engine" / "events.jsonl"),
))


class EventLogger:
    """Appends structured events to a shared NDJSON log file."""

    def __init__(self, run_id: str, log_path: Path | None = None):
        self.run_id = run_id
        self.log_path = log_path or DEFAULT_LOG
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **data) -> None:
        """Write one event line. Never raises — logging must not crash the engine."""
        record = {
            "ts": time.time(),
            "run_id": self.run_id,
            "event": event,
            **data,
        }
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
                f.flush()
        except Exception:
            # Never let event emission break the render
            pass

    # Convenience helpers for the standard lifecycle events
    def run_start(self, project_dir: str, max_iterations: int) -> None:
        self.emit("run_start", project_dir=project_dir, max_iterations=max_iterations)

    def iteration_start(self, iteration: int) -> None:
        self.emit("iteration_start", iteration=iteration)

    def render_start(self, project_dir: str) -> None:
        self.emit("render_start", project_dir=project_dir)

    def render_done(self, video_path: str, duration_s: float) -> None:
        self.emit("render_done", video_path=video_path, render_seconds=duration_s)

    def render_fail(self, error: str) -> None:
        self.emit("render_fail", error=error)

    def verify_start(self, video_path: str, frames: int) -> None:
        self.emit("verify_start", video_path=video_path, frames=frames)

    def vision_check(self, frame_path: str, question: str, result: str, ok: bool) -> None:
        self.emit("vision_check",
                  frame=frame_path,
                  question=question,
                  result=result,
                  passed=ok)

    def iteration_end(self, iteration: int, passed: bool, issues: list[str]) -> None:
        self.emit("iteration_end", iteration=iteration, passed=passed, issues=issues)

    def run_end(self, status: str, final_video: str | None, iterations: int) -> None:
        self.emit("run_end",
                  status=status,
                  final_video=final_video,
                  iterations=iterations)
