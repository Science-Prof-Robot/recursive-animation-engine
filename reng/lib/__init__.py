"""Recursive Animation Engine core library."""

from .engine import IterationResult, RunResult, run
from .events import DEFAULT_LOG, EventLogger
from .render import RenderError, render
from .verify import VerifyError, extract_keyframes
from .vision import VisionError, analyze

__all__ = [
    "run",
    "IterationResult",
    "RunResult",
    "EventLogger",
    "DEFAULT_LOG",
    "render",
    "RenderError",
    "extract_keyframes",
    "VerifyError",
    "analyze",
    "VisionError",
]
