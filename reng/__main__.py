"""
Main CLI entry point.

Subcommands:
    reng render  <project_dir>     run the recursive engine once
    reng watch                     always-on progress viewer
    reng vision  <image> <q>       standalone single-image analysis
    reng verify  <video>           standalone keyframe extraction
    reng plan [--llm]              create a video plan (stdin Q&A or one-shot LLM brief)
    reng build <plan.json>         build a video from plan (act by act)
    reng voiceover <text>          generate TTS audio using Gemini Flash
    reng provider <command>          manage and test LLM providers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .lib.build import ActBuildResult, build_act, build_all_acts, mix_audio_with_video
from .lib.engine import run as engine_run
from .lib.plan import (
    PlanError,
    gather_answers_via_llm,
    get_planning_questions,
    reason_over_acts,
)
from .lib.providers import (
    GeminiTTSProvider,
    ProviderError,
    get_provider,
    get_vision_model_spec,
)
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
        provider_name = args.provider
        model_spec = None

        if args.model:
            model_spec = get_vision_model_spec()
            # Override with specified model
            from .providers import ModelSpec

            model_spec = ModelSpec(
                provider=provider_name or model_spec.provider,
                model_id=args.model,
                supports_vision=True,
                max_tokens=args.max_tokens or 2048,
            )

        result = analyze(
            args.image,
            args.question,
            provider_name=provider_name,
            model_spec=model_spec,
            max_tokens=args.max_tokens or 2048,
        )
        print(result)
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


def _cmd_plan(args) -> int:
    """Interactive planning mode - ask questions and create a video plan."""
    print("=" * 60)
    print("RECURSIVE ANIMATION ENGINE - PLAN PHASE")
    print("=" * 60)

    questions = get_planning_questions()
    to_ask = [q for q in questions if not (args.quick and not q.get("required", False))]

    answers: dict[str, str] = {}

    if args.llm:
        # One free-form brief → LLM fills every planning field (OpenRouter / Gemini / Fireworks).
        print(
            "\nUsing LLM to turn your brief into structured planning answers "
            f"(provider: {args.provider or 'RENG_TEXT_PROVIDER / RENG_LLM_PROVIDER'}).\n"
        )
        print("Describe the video you want (2–8 sentences is ideal):\n")
        brief = input("> ").strip()
        if not brief:
            print("Error: empty brief — add a description or run without --llm.", file=sys.stderr)
            return 1
        try:
            answers = gather_answers_via_llm(
                brief,
                questions=to_ask,
                provider_name=args.provider,
                quick=args.quick,
            )
        except PlanError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        print("\n--- Structured answers (from LLM) ---")
        for q in to_ask:
            qid = q["id"]
            text = answers.get(qid, "")
            preview = (text[:220] + "…") if len(text) > 220 else text
            print(f"\n[{qid}] {preview}")
        print("\nPress Enter to generate the full plan from these answers (Ctrl+C to abort).")
        try:
            input()
        except EOFError:
            pass
    else:
        print(
            "\nLet me ask you some questions about your video...\n"
            "(Tip: `reng plan --llm --provider openrouter` fills this from one short brief.)\n"
        )

        for q in to_ask:
            print(f"\n{q['question']}")
            if not q.get("required", False):
                print("(Press Enter to skip this optional question)")

            answer = input("> ").strip()

            if answer or q.get("required", False):
                answers[q["id"]] = answer if answer else "N/A"

    print("\n" + "=" * 60)
    print("Reasoning over your answers and structuring the video plan...")
    print("=" * 60)

    try:
        # Check if we're in Claude Code context (native provider)
        # If not, use configured provider
        plan = reason_over_acts(answers, provider_name=args.provider)

        # Save plan to file
        output_path = Path(args.output)
        plan.save(output_path)

        print(f"\nPlan created with ID: {plan.plan_id}")
        print(f"Total duration: {plan.total_duration:.1f} seconds")
        print(f"Number of acts: {len(plan.acts)}")
        print(f"\nPlan saved to: {output_path}")

        print("\nActs breakdown:")
        for act in plan.acts:
            print(f"  Act {act.act_number}: {act.title} ({act.duration_seconds:.1f}s)")
            print(f"    - {act.description[:80]}...")
            if act.voiceover_script:
                print(f"    - Has voiceover: {len(act.voiceover_script.split())} words")

        if plan.audio_plan.get("has_voiceover"):
            print(f"\nVoiceover: Enabled ({plan.audio_plan.get('voiceover_tone', 'casual')} tone)")

        print(f"\nNext step: Run 'reng build {args.output}' to start building")

        return 0

    except Exception as e:
        print(f"Error creating plan: {e}", file=sys.stderr)
        return 1


def _cmd_build(args) -> int:
    """Build phase - construct video act by act from a plan."""
    from .lib.plan import VideoPlan

    print("=" * 60)
    print("RECURSIVE ANIMATION ENGINE - BUILD PHASE")
    print("=" * 60)

    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"Plan file not found: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan = VideoPlan.load(plan_path)
    except Exception as e:
        print(f"Error loading plan: {e}", file=sys.stderr)
        return 1

    print(f"\nLoaded plan: {plan.plan_id}")
    print(f"Video: {plan.concept.title}")
    print(f"Acts to build: {len(plan.acts)}")
    print(f"Max iterations per act: {args.max_iterations}")
    print()

    # Create project directory
    base_dir = Path(args.project_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    def progress_callback(act_num: int, total: int, status: str):
        print(f"[{act_num}/{total}] {status}")

    try:
        result = build_all_acts(
            plan=plan,
            base_project_dir=base_dir,
            max_iterations=args.max_iterations,
            generate_voiceovers=args.voiceover and plan.audio_plan.get("has_voiceover", False),
            combine_acts=args.combine,
            progress_callback=progress_callback,
        )

        print("\n" + "=" * 60)
        print(f"BUILD STATUS: {result.status.upper()}")
        print("=" * 60)

        print("\nAct Results:")
        for r in result.act_results:
            status = "OK" if r.passed else "NEEDS REVIEW"
            video_str = str(r.video_path) if r.video_path else "N/A"
            print(f"  Act {r.act_number}: {status} ({r.iterations} iterations)")
            if r.issues and not r.passed:
                for issue in r.issues[:2]:
                    print(f"    - {issue[:100]}...")

        if result.final_video:
            print(f"\nFinal combined video: {result.final_video}")

        if result.combined_voiceover:
            print(f"Combined voiceover: {result.combined_voiceover}")

            # Mix audio if both video and voiceover exist
            if result.final_video and args.mix_audio:
                final_with_audio = base_dir / "final_with_audio.mp4"
                print(f"\nMixing voiceover with video...")
                try:
                    mix_audio_with_video(
                        result.final_video,
                        result.combined_voiceover,
                        final_with_audio,
                    )
                    print(f"Final with audio: {final_with_audio}")
                except Exception as e:
                    print(f"Warning: Audio mixing failed: {e}")

        # Save build metadata
        metadata_path = base_dir / "build_metadata.json"
        metadata = {
            "plan_id": plan.plan_id,
            "status": result.status,
            "acts": len(plan.acts),
            "acts_passed": sum(1 for r in result.act_results if r.passed),
            "final_video": str(result.final_video) if result.final_video else None,
            "voiceover": str(result.combined_voiceover) if result.combined_voiceover else None,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
        print(f"\nBuild metadata: {metadata_path}")

        return 0 if result.status in ("complete", "partial") else 1

    except Exception as e:
        print(f"Build error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def _cmd_voiceover(args) -> int:
    """Generate voiceover audio using Gemini TTS 3.1 Flash."""
    try:
        tts = GeminiTTSProvider()

        # Read from file if --file specified, otherwise use args.text
        if args.file:
            text = Path(args.file).read_text()
        else:
            text = args.text

        if not text:
            print("Error: No text provided. Use <text> or --file <path>", file=sys.stderr)
            return 1

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if text is SSML
        if text.strip().startswith("<") and "<speak>" in text:
            result = tts.generate_voiceover_ssml(
                ssml=text,
                voice_name=args.voice,
                output_path=output_path,
            )
            print(f"SSML voiceover generated: {result}")
        else:
            result = tts.generate_voiceover(
                text=text,
                voice_name=args.voice,
                speaking_rate=args.rate,
                pitch=args.pitch,
                output_path=output_path,
            )
            print(f"Voiceover generated: {result}")
            print(f"Duration estimate: ~{len(text.split()) / 2.5:.1f} seconds")

        return 0

    except ProviderError as e:
        print(f"TTS Error: {e}", file=sys.stderr)
        print("Make sure GEMINI_API_KEY is set", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_provider(args) -> int:
    """Test and manage LLM providers."""
    if args.provider_command == "test":
        # Test all configured providers
        print("Testing LLM providers...\n")

        providers = ["openrouter", "gemini", "fireworks"]

        for provider_name in providers:
            print(f"Testing {provider_name}...")
            try:
                provider = get_provider(provider_name)
                model_spec = get_vision_model_spec()

                # Simple test query
                response = provider.analyze(
                    question="Say 'OK' if you can read this.",
                    model_spec=model_spec,
                    max_tokens=100,
                )
                print(f"  Status: OK")
                print(f"  Response: {response[:50]}...")
            except Exception as e:
                print(f"  Status: FAILED - {e}")
            print()

        return 0

    elif args.provider_command == "list-models":
        # List recommended models
        print("Recommended Vision Models (Gemma series):")
        print("  - google/gemma-3-27b-it (default, vision-capable)")
        print("  - google/gemma-3-12b-it")
        print("  - google/gemma-3-4b-it")
        print()
        print("Recommended Text Models:")
        print("  - native (uses Claude Code context - default)")
        print("  - google/gemma-3-27b-it (fallback)")
        print("  - anthropic/claude-sonnet-4 (via OpenRouter)")
        print()
        print("Set via environment variables:")
        print("  RENG_VISION_MODEL=google/gemma-3-27b-it")
        print("  RENG_TEXT_MODEL=native")
        print()

        return 0

    elif args.provider_command == "env":
        # Show environment setup
        print("Required environment variables:")
        print()
        print("For OpenRouter (default):")
        print("  export OPENROUTER_API_KEY='your-key'")
        print()
        print("For Gemini API:")
        print("  export GEMINI_API_KEY='your-key'")
        print()
        print("For Fireworks:")
        print("  export FIREWORKS_API_KEY='your-key'")
        print()
        print("Optional configuration:")
        print("  export RENG_LLM_PROVIDER=openrouter  # Default provider")
        print("  export RENG_VISION_PROVIDER=openrouter")
        print("  export RENG_TEXT_PROVIDER=native     # Uses Claude Code")
        print("  export RENG_VISION_MODEL=google/gemma-3-27b-it")
        print("  export RENG_TEXT_MODEL=native")
        print()

        return 0

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reng",
        description="Recursive Animation Engine - render, verify, iterate, plan, build",
    )
    parser.add_argument("--version", action="version", version=f"reng {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # render
    p_render = sub.add_parser("render", help="Run the recursive engine on a project")
    p_render.add_argument("project_dir", help="path to a Hyperframes project directory")
    p_render.add_argument("--intent", help="free-text description of user intent")
    p_render.add_argument("--max-iterations", type=int, default=3)
    p_render.add_argument(
        "--frames", type=int, default=3, help="keyframes per verification pass"
    )
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
    p_vision.add_argument(
        "--provider",
        choices=["openrouter", "gemini", "fireworks"],
        help="Which provider to use",
    )
    p_vision.add_argument(
        "--model",
        help="Override model ID (e.g., google/gemma-3-27b-it)",
    )
    p_vision.add_argument("--max-tokens", type=int, default=2048)
    p_vision.set_defaults(func=_cmd_vision)

    # verify
    p_verify = sub.add_parser("verify", help="Extract keyframes from a video")
    p_verify.add_argument("video", help="path to an MP4 file")
    p_verify.add_argument("--frames", type=int, default=3)
    p_verify.set_defaults(func=_cmd_verify)

    # plan
    p_plan = sub.add_parser("plan", help="Create a video plan from user answers")
    p_plan.add_argument(
        "-o", "--output", default="video_plan.json",
        help="Output path for the plan JSON"
    )
    p_plan.add_argument(
        "--quick", action="store_true",
        help="Skip optional questions"
    )
    p_plan.add_argument(
        "--llm",
        action="store_true",
        help="Ask once for a free-form brief, then use the text LLM to fill all planning answers",
    )
    p_plan.add_argument(
        "--provider",
        choices=["native", "openrouter", "gemini", "fireworks"],
        help="Provider for plan reasoning (default: native uses Claude Code context)",
    )
    p_plan.set_defaults(func=_cmd_plan)

    # build
    p_build = sub.add_parser("build", help="Build a video from a plan (act by act)")
    p_build.add_argument("plan", help="Path to plan JSON file")
    p_build.add_argument(
        "project_dir", nargs="?", default="./build_output",
        help="Directory for build output"
    )
    p_build.add_argument(
        "--max-iterations", type=int, default=3,
        help="Max render-verify cycles per act"
    )
    p_build.add_argument(
        "--no-voiceover", dest="voiceover", action="store_false", default=True,
        help="Skip voiceover generation"
    )
    p_build.add_argument(
        "--no-combine", dest="combine", action="store_false", default=True,
        help="Don't combine acts into final video"
    )
    p_build.add_argument(
        "--no-mix-audio", dest="mix_audio", action="store_false", default=True,
        help="Don't mix voiceover with final video"
    )
    p_build.set_defaults(func=_cmd_build)

    # voiceover
    p_voiceover = sub.add_parser("voiceover", help="Generate voiceover with Gemini TTS 3.1 Flash")
    p_voiceover.add_argument(
        "text", nargs="?",
        help="Text to speak (or use --file for a script file)"
    )
    p_voiceover.add_argument(
        "--file", "-f",
        help="Path to a text/SSML file to speak"
    )
    p_voiceover.add_argument(
        "-o", "--output", default="voiceover.mp3",
        help="Output MP3 path"
    )
    p_voiceover.add_argument(
        "--voice", default="en-US-Neural2-D",
        help="Voice name (en-US-Neural2-D, en-GB-Neural2-B, etc)"
    )
    p_voiceover.add_argument(
        "--rate", type=float, default=1.0,
        help="Speaking rate (0.25 to 4.0)"
    )
    p_voiceover.add_argument(
        "--pitch", type=float, default=0.0,
        help="Pitch adjustment (-20.0 to 20.0)"
    )
    p_voiceover.set_defaults(func=_cmd_voiceover)

    # provider
    p_provider = sub.add_parser("provider", help="Manage and test LLM providers")
    p_provider.add_argument(
        "provider_command",
        choices=["test", "list-models", "env"],
        nargs="?",
        default="test",
        help="Provider subcommand"
    )
    p_provider.set_defaults(func=_cmd_provider)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
