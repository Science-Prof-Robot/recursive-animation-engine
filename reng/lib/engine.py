"""
The recursive animation engine.

Given a project directory, runs a render -> verify -> decide loop:

    for iteration in 1..max:
        video = render(project_dir)
        frames = extract_keyframes(video)
        issues = vision_verify(frames, user_intent)
        if not issues:
            return video              # shipped
        if iteration == max:
            return video              # ship best effort
        # caller / agent is expected to patch the project between iterations

The engine itself doesn't patch HTML — that's the caller's (or the
agent's) job. The engine just orchestrates render + verify + decide
and emits structured events so `reng watch` can show progress live.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .events import EventLogger
from .render import RenderError, render
from .verify import VerifyError, extract_keyframes
from .vision import VisionError, analyze, is_approval


DEFAULT_VERIFICATION_PROMPT = (
    "Describe what you see in this animation keyframe. "
    "List any visible problems with layout, text clipping, "
    "color contrast, or obvious rendering artifacts. "
    "If everything looks clean and correct, reply exactly with 'OK'."
)


@dataclass
class IterationResult:
    iteration: int
    video: Path | None
    frames: list[Path] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    passed: bool = False


@dataclass
class RunResult:
    status: str                         # "passed" | "max_iterations" | "error"
    final_video: Path | None
    iterations: list[IterationResult]
    error: str | None = None


# Callback invoked between iterations so the caller (or agent) can
# patch the project based on the reported issues. If not provided, the
# engine stops at the first failed iteration because there's nothing
# automated to do.
PatchFn = Callable[[IterationResult], None]




def run(
    project_dir: str | Path,
    *,
    intent: str = "",
    max_iterations: int = 3,
    frames: int = 3,
    verification_prompt: str | None = None,
    patch_fn: PatchFn | None = None,
    run_id: str | None = None,
    event_log: Path | None = None,
) -> RunResult:
    """
    Run the recursive render loop for a project.

    Args:
        project_dir: path to a Hyperframes project directory.
        intent: free-text description of what the user asked for.
            Appended to the verification prompt so the vision model
            can judge against user intent, not just generic aesthetics.
        max_iterations: hard cap on render+verify cycles (default 3).
        frames: keyframes sampled per verification pass (default 3).
        verification_prompt: override the default vision prompt.
        patch_fn: optional callback invoked after a failed iteration;
            receives the IterationResult. Use it to apply fixes to the
            project before the next render.
        run_id: explicit run id; one is generated if omitted.
        event_log: override event log path (defaults to env/default).
    """
    project_dir = Path(project_dir).expanduser().resolve()
    run_id = run_id or uuid.uuid4().hex[:8]
    log = EventLogger(run_id, event_log)
    base_prompt = verification_prompt or DEFAULT_VERIFICATION_PROMPT
    full_prompt = f"{base_prompt}\n\nUser intent: {intent}" if intent else base_prompt

    log.run_start(str(project_dir), max_iterations)
    history: list[IterationResult] = []

    try:
        for i in range(1, max_iterations + 1):
            log.iteration_start(i)
            result = IterationResult(iteration=i, video=None)

            # 1) Render
            log.render_start(str(project_dir))
            try:
                video, elapsed = render(project_dir)
                result.video = video
                log.render_done(str(video), elapsed)
            except RenderError as e:
                log.render_fail(str(e))
                result.issues.append(f"render failed: {e}")
                history.append(result)
                log.iteration_end(i, passed=False, issues=result.issues)
                log.run_end("error", None, i)
                return RunResult("error", None, history, str(e))

            # 2) Extract keyframes
            try:
                log.verify_start(str(video), frames)
                result.frames = extract_keyframes(video, frames=frames)
            except VerifyError as e:
                result.issues.append(f"verify failed: {e}")
                history.append(result)
                log.iteration_end(i, passed=False, issues=result.issues)
                log.run_end("error", str(video), i)
                return RunResult("error", video, history, str(e))

            # 3) Vision-verify every frame
            all_passed = True
            for frame in result.frames:
                try:
                    text = analyze(frame, full_prompt)
                except VisionError as e:
                    result.issues.append(f"vision error on {frame.name}: {e}")
                    log.vision_check(str(frame), full_prompt, str(e), ok=False)
                    all_passed = False
                    continue

                ok = is_approval(text)
                if not ok:
                    result.issues.append(f"{frame.name}: {text}")
                    all_passed = False
                log.vision_check(str(frame), full_prompt, text, ok=ok)

            result.passed = all_passed
            log.iteration_end(i, passed=all_passed, issues=result.issues)
            history.append(result)

            if all_passed:
                log.run_end("passed", str(video), i)
                return RunResult("passed", video, history)

            # 4) Let the caller patch, or stop if nothing can fix it
            if patch_fn is not None and i < max_iterations:
                patch_fn(result)
            # If no patch_fn provided, loop simply re-renders the same input;
            # useful for non-deterministic renderers but otherwise wasteful.

    except Exception as e:
        log.run_end("error", None, len(history))
        return RunResult("error", None, history, str(e))

    last = history[-1]
    log.run_end("max_iterations", str(last.video) if last.video else None, len(history))
    return RunResult("max_iterations", last.video, history)
