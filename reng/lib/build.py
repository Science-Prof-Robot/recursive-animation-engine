"""
Build phase for the animation engine.

Builds video act by act using vision model loops for verification.
Patches everything together into a unified final output.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .plan import VideoAct, VideoPlan

from .engine import run as engine_run
from .events import EventLogger
from .plan import PlanError, VideoAct, VideoPlan
from .providers import (
    GeminiTTSProvider,
    ProviderError,
    get_tts_provider,
    get_vision_model_spec,
    get_vision_provider,
)
from .verify import extract_keyframes
from .vision import analyze, is_approval


class BuildError(RuntimeError):
    """Error in build phase."""

    pass


@dataclass
class ActBuildResult:
    """Result of building a single act."""

    act_number: int
    video_path: Path | None
    voiceover_path: Path | None
    frames: list[Path] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    passed: bool = False
    iterations: int = 0


@dataclass
class FinalBuildResult:
    """Final result after building all acts and combining."""

    status: str  # "complete", "partial", "failed"
    final_video: Path | None
    act_results: list[ActBuildResult]
    combined_voiceover: Path | None = None
    metadata: dict = field(default_factory=dict)


def build_act(
    act: VideoAct,
    project_dir: Path,
    plan: VideoPlan,
    max_iterations: int = 3,
    frames_per_check: int = 3,
    generate_voiceover: bool = True,
    patch_fn: Callable[[ActBuildResult], None] | None = None,
    event_log: Path | None = None,
    run_id: str | None = None,
) -> ActBuildResult:
    """
    Build a single video act with vision loop verification.

    Args:
        act: The VideoAct to build
        project_dir: Directory containing the act's HTML/CSS/JS
        plan: Full video plan (for context)
        max_iterations: Max render-verify-fix cycles
        frames_per_check: Number of keyframes to verify
        generate_voiceover: Whether to generate TTS for this act
        patch_fn: Optional callback for auto-fixing issues
        event_log: Event log path
        run_id: Run identifier

    Returns:
        ActBuildResult with video path, issues, and pass status
    """
    import uuid

    run_id = run_id or f"act{act.act_number}-{uuid.uuid4().hex[:8]}"
    log = EventLogger(run_id, event_log)

    log.run_start(str(project_dir), max_iterations)

    # Generate voiceover first if requested
    voiceover_path: Path | None = None
    if generate_voiceover and act.voiceover_script:
        try:
            tts = get_tts_provider()
            voiceover_path = project_dir / f"act{act.act_number}_voiceover.mp3"
            tts.generate_voiceover(
                text=act.voiceover_script,
                voice_name=_select_voice_for_mood(plan.concept.mood_tone),
                speaking_rate=1.0,
                output_path=voiceover_path,
            )
        except ProviderError as e:
            log.emit("voiceover_fail", error=str(e))

    # Build verification prompt specific to this act
    verification_prompt = _build_act_verification_prompt(act, plan)

    result = ActBuildResult(
        act_number=act.act_number,
        video_path=None,
        voiceover_path=voiceover_path,
    )

    # Run the recursive engine
    engine_result = engine_run(
        project_dir,
        intent=f"{act.title}: {act.description}",
        max_iterations=max_iterations,
        frames=frames_per_check,
        verification_prompt=verification_prompt,
        patch_fn=patch_fn,
        run_id=run_id,
        event_log=event_log,
    )

    # Extract results
    if engine_result.final_video:
        result.video_path = Path(engine_result.final_video)

    result.iterations = len(engine_result.iterations)

    # Get issues from the last iteration
    if engine_result.iterations:
        last_it = engine_result.iterations[-1]
        result.frames = last_it.frames
        result.issues = last_it.issues
        result.passed = last_it.passed

    result.passed = engine_result.status == "passed"
    log.run_end(engine_result.status, str(result.video_path) if result.video_path else None, result.iterations)

    return result


def _build_act_verification_prompt(act: VideoAct, plan: VideoPlan) -> str:
    """Build a verification prompt specific to this act."""
    visual_elements = "\n".join(f"- {e}" for e in act.key_visual_elements) or "- Clean typography\n- Smooth animation"

    prompt = f"""Verify this animation frame for Act {act.act_number}: "{act.title}"

Act Description: {act.description}
Required Visual Elements:
{visual_elements}

Video Style: {plan.concept.visual_style}
Mood/Tone: {plan.concept.mood_tone or "Professional"}

Check for:
1. All required visual elements are present
2. Text is readable (no clipping, good contrast)
3. Animation is smooth (no glitches or jumps)
4. Style matches the overall video aesthetic
5. No rendering artifacts or broken layouts

If everything looks correct, reply exactly with 'OK'.
If there are issues, describe them clearly and specifically."""

    return prompt


def _select_voice_for_mood(mood: str | None) -> str:
    """Select an appropriate voice based on mood."""
    mood = (mood or "").lower()

    if "professional" in mood or "corporate" in mood:
        return "en-US-Neural2-D"
    elif "energetic" in mood or "upbeat" in mood:
        return "en-US-Neural2-F"
    elif "calm" in mood or "soothing" in mood:
        return "en-US-Neural2-C"
    elif "british" in mood or "uk" in mood:
        return "en-GB-Neural2-B"
    else:
        return "en-US-Neural2-D"  # default


def build_all_acts(
    plan: VideoPlan,
    base_project_dir: Path,
    max_iterations: int = 3,
    generate_voiceovers: bool = True,
    combine_acts: bool = True,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> FinalBuildResult:
    """
    Build all acts in a plan sequentially.

    Args:
        plan: The VideoPlan with all acts to build
        base_project_dir: Base directory containing act subdirectories
        max_iterations: Max iterations per act
        generate_voiceovers: Whether to generate TTS for voiceover acts
        combine_acts: Whether to combine act videos into final output
        progress_callback: Optional callback(act_num, total, status)

    Returns:
        FinalBuildResult with all act results and combined video
    """
    act_results: list[ActBuildResult] = []

    for i, act in enumerate(plan.acts, 1):
        if progress_callback:
            progress_callback(i, len(plan.acts), f"Building act {i}: {act.title}")

        # Each act has its own subdirectory
        act_dir = base_project_dir / f"act{i:02d}"
        act_dir.mkdir(parents=True, exist_ok=True)

        # Build this act
        result = build_act(
            act=act,
            project_dir=act_dir,
            plan=plan,
            max_iterations=max_iterations,
            generate_voiceover=generate_voiceovers and bool(act.voiceover_script),
        )

        act_results.append(result)

    # Determine overall status
    all_passed = all(r.passed for r in act_results)
    any_passed = any(r.passed for r in act_results)

    status = "complete" if all_passed else "partial" if any_passed else "failed"

    # Combine if requested and at least one act succeeded
    final_video: Path | None = None
    combined_voiceover: Path | None = None

    if combine_acts and any_passed:
        if progress_callback:
            progress_callback(len(plan.acts), len(plan.acts), "Combining acts...")

        final_video = _combine_act_videos(act_results, base_project_dir)

        if generate_voiceovers:
            combined_voiceover = _combine_voiceovers(act_results, base_project_dir)

    return FinalBuildResult(
        status=status,
        final_video=final_video,
        act_results=act_results,
        combined_voiceover=combined_voiceover,
        metadata={
            "plan_id": plan.plan_id,
            "acts_count": len(plan.acts),
            "acts_passed": sum(1 for r in act_results if r.passed),
        },
    )


def _combine_act_videos(
    act_results: list[ActBuildResult],
    output_dir: Path,
) -> Path | None:
    """
    Combine individual act videos into a single final video using ffmpeg.

    Uses concat demuxer for seamless joining with appropriate transitions.
    """
    # Filter to successful videos
    videos = [r.video_path for r in act_results if r.video_path and r.video_path.exists()]

    if not videos:
        return None

    if len(videos) == 1:
        # Just copy the single video
        final_path = output_dir / "final.mp4"
        shutil.copy(videos[0], final_path)
        return final_path

    # Create concat file list
    concat_file = output_dir / "concat_list.txt"
    with concat_file.open("w") as f:
        for video in videos:
            f.write(f"file '{video.absolute()}'\n")

    # Use ffmpeg concat
    final_path = output_dir / "final.mp4"

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-y",
                str(final_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise BuildError(f"Failed to combine videos: {e.stderr.decode()}")
    except FileNotFoundError:
        raise BuildError("ffmpeg not found for video combination")
    finally:
        concat_file.unlink(missing_ok=True)

    return final_path


def _combine_voiceovers(
    act_results: list[ActBuildResult],
    output_dir: Path,
) -> Path | None:
    """
    Combine individual act voiceovers into a single audio track.

    Adds appropriate pauses between acts for transitions.
    """
    # Filter to successful voiceovers
    voiceovers = [
        r.voiceover_path for r in act_results
        if r.voiceover_path and r.voiceover_path.exists()
    ]

    if not voiceovers:
        return None

    if len(voiceovers) == 1:
        final_path = output_dir / "final_voiceover.mp3"
        shutil.copy(voiceovers[0], final_path)
        return final_path

    # For multiple voiceovers, we need to add silence between them
    # and concatenate
    final_path = output_dir / "final_voiceover.mp3"

    # Create a filter_complex command to add 1-second silence between tracks
    inputs = []
    filters = []
    current = 0

    for i, vo in enumerate(voiceovers):
        inputs.extend(["-i", str(vo)])
        if i < len(voiceovers) - 1:
            # Add adelay filter (1 second = 1000ms)
            filters.append(f"[{i}:a]adelay={current * 1000}:all=1[a{i}]")
            current += 1  # duration + 1s gap (simplified, actual duration needed)

    # Simpler approach: use the concat demuxer
    concat_file = output_dir / "audio_concat_list.txt"
    with concat_file.open("w") as f:
        for vo in voiceovers:
            # Add each voiceover with a duration
            duration = _get_audio_duration(vo)
            f.write(f"file '{vo.absolute()}'\n")
            f.write(f"duration {duration}\n")
            # Add 1 second of silence
            f.write(f"file 'anullsrc=duration=1:r=44100:cl=mono'\n")
            f.write(f"duration 1\n")

    # Actually, simpler: just use concat directly
    concat_file.unlink(missing_ok=True)

    # Rebuild with simpler approach using filter_complex
    try:
        # First, create a file with all inputs
        filter_inputs = ""
        filter_complex = ""

        for i, vo in enumerate(voiceovers):
            filter_inputs += f"[{i}:a]"

        filter_complex = f"{filter_inputs}concat=n={len(voiceovers)}:v=0:a=1[outa]"

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        for vo in voiceovers:
            cmd.extend(["-i", str(vo)])
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outa]",
            "-y",
            str(final_path),
        ])

        subprocess.run(cmd, check=True, capture_output=True)

    except subprocess.CalledProcessError as e:
        # Fallback: just concatenate without gaps
        concat_file = output_dir / "audio_concat.txt"
        with concat_file.open("w") as f:
            for vo in voiceovers:
                f.write(f"file '{vo.absolute()}'\n")

        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-y",
                str(final_path),
            ],
            check=True,
            capture_output=True,
        )
        concat_file.unlink(missing_ok=True)

    except FileNotFoundError:
        raise BuildError("ffmpeg not found for audio combination")

    return final_path


def _get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 5.0  # Default estimate


def mix_audio_with_video(
    video_path: Path,
    voiceover_path: Path,
    output_path: Path,
    background_music: Path | None = None,
    music_volume: float = 0.3,
) -> Path:
    """
    Mix voiceover and optional background music with video.

    Args:
        video_path: Path to the video file
        voiceover_path: Path to the voiceover audio
        output_path: Where to save the mixed output
        background_music: Optional background music track
        music_volume: Volume level for background music (0.0-1.0)

    Returns:
        Path to the mixed video
    """
    try:
        if background_music and background_music.exists():
            # Mix voiceover + background music + video
            filter_complex = (
                f"[1:a]volume=1.0[vo];"
                f"[2:a]volume={music_volume}[bg];"
                f"[vo][bg]amix=inputs=2:duration=first:dropout_transition=3[audio]"
            )

            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-i", str(video_path),
                    "-i", str(voiceover_path),
                    "-i", str(background_music),
                    "-filter_complex", filter_complex,
                    "-map", "0:v",
                    "-map", "[audio]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    "-y",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
            )
        else:
            # Just mix voiceover with video
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-i", str(video_path),
                    "-i", str(voiceover_path),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    "-y",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
            )

    except subprocess.CalledProcessError as e:
        raise BuildError(f"Failed to mix audio: {e.stderr.decode()}")
    except FileNotFoundError:
        raise BuildError("ffmpeg not found for audio mixing")

    return output_path
