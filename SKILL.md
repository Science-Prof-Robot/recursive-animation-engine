---
name: recursive-animation-engine
description: Render HTML/CSS/JS animations to MP4 and verify them visually in a recursive self-correction loop. Use when the user asks for animations, motion graphics, video explainers, or any rendered visual output where correctness matters. Features multi-provider LLM support (OpenRouter, Gemini, Fireworks), Gemini TTS 3.1 Flash voiceover, and structured plan/build workflow. The engine handles render → extract keyframes → vision-check → iterate automatically, so you only need to write good HTML and let the loop correct it.
---

# Recursive Animation Engine

A comprehensive pipeline that renders HTML compositions to MP4 and uses vision models to verify the output is correct. Features multi-provider LLM support, TTS voiceover generation, and structured plan/build workflows for complex video productions.

## How it works

### Basic Loop (legacy)
```
1. you write HTML/CSS/JS
2. engine renders it to MP4                       (chromium + bun + ffmpeg)
3. engine extracts 3 keyframes from the MP4       (ffmpeg)
4. engine asks a vision model: "is this correct?" (Gemma via OpenRouter/Gemini/Fireworks)
5. if any frame fails → you patch the HTML → loop back to step 2
6. max 3 iterations, then ship the best version
```

### Full Workflow (plan → build → combine)
```
1. PLAN PHASE: Ask user structured questions about the video
2. REASON: LLM reasons over acts/scenes based on answers
3. BUILD PHASE: Build each act with vision loop verification
4. VOICEOVER: Generate Gemini TTS 3.1 Flash narration per act
5. COMBINE: Stitch acts together, mix audio, deliver final MP4
```

All progress is streamed to `~/.recursive-animation-engine/events.jsonl` — run `reng watch` in a separate terminal to see what's happening in real time.

## Using it from an agent

### Plan Phase (structured video planning)

```bash
reng plan -o video_plan.json
```

This interactively asks the user about:
- Purpose (educational, promotional, demo, etc.)
- Topic/content
- Target duration (short/medium/long)
- Target audience
- Visual style preference
- Voiceover needs
- Existing assets

Then reasons over the answers to produce a structured `VideoPlan` with acts, timing, and narration scripts.

### Build Phase (act-by-act construction)

```bash
reng build video_plan.json ./build_output
```

Builds each act sequentially:
- Renders HTML/CSS for each act
- Vision verification per act
- Voiceover generation per act (if scripted)
- Combines all acts into final video
- Mixes audio tracks

Options:
- `--max-iterations N` - Max render-verify cycles per act (default: 3)
- `--no-voiceover` - Skip TTS generation
- `--no-combine` - Don't concatenate acts
- `--no-mix-audio` - Don't mix voiceover with final video

### Fully-automated one-shot

```bash
reng render ./renders/my-scene --intent "spinning progress bar from 0 to 100%"
```

The CLI renders, verifies, and exits with 0 if it passed. Exit code 1 means the render or vision call errored (different from "didn't pass verification" which is exit 0 with status `max_iterations`).

### Agent-driven (loop in your code)

```python
from reng.lib.engine import run

def my_patch_fn(iteration_result):
    # inspect iteration_result.issues and edit files in the project dir
    # before the engine re-renders
    for issue in iteration_result.issues:
        print("fix needed:", issue)
        # ... your agent decides what to change here

result = run(
    "./renders/my-scene",
    intent="spinning progress bar from 0 to 100%",
    max_iterations=3,
    patch_fn=my_patch_fn,
)
print(result.status, result.final_video)
```

### Voiceover Generation (Gemini TTS 3.1 Flash)

```bash
# Simple text to speech
reng voiceover "Welcome to our product demo" -o intro.mp3

# From file
reng voiceover --file script.txt -o narration.mp3

# Custom voice and rate
reng voiceover "Hello world" -o hello.mp3 --voice en-GB-Neural2-B --rate 0.9

# SSML for fine control
reng voiceover '<speak>Hello <break time="1s"/> World</speak>' -o ssml.mp3
```

### Standalone vision check (no rendering)

```bash
# Default Gemma via OpenRouter
reng vision screenshot.png "What error is shown here?"

# Specific provider
reng vision screenshot.png "What do you see?" --provider gemini

# Specific model
reng vision screenshot.png "Describe the layout" --model google/gemma-3-27b-it
```

### Provider management

```bash
# Test all configured providers
reng provider test

# List recommended models
reng provider list-models

# Show environment setup
reng provider env
```

## When to use

- Any animation / motion graphic / video explainer request
- Multi-act videos with narration and structured flow
- UI screen-recording verification (did the hover state actually animate?)
- Chart or diagram rendering (did the labels land where they should?)
- Any task where the output is visual and "looks right" matters more than the code

## When NOT to use

- One-off still images (just call `reng vision` directly)
- Text-only deliverables (no visual output to verify)
- Purely data output (numbers, JSON, CSV)

## Progress monitoring

Keep a second terminal open with:

```bash
reng watch
```

It tails the event log and shows live status: render start/done, each keyframe check, each iteration's verdict, and the final result. Useful when runs take minutes and you want to confirm the engine is still making forward progress (not stuck).

Filter to one run:

```bash
reng watch --follow-run <run_id>
```

Replay recent history before tailing:

```bash
reng watch --since 1h
```

## Multi-Provider LLM Support

The engine supports multiple LLM providers for vision and text generation:

### OpenRouter (default)
Unified API for 100+ models. Default vision model: `google/gemma-3-27b-it`

```bash
export OPENROUTER_API_KEY='your-key'
export RENG_LLM_PROVIDER=openrouter
export RENG_VISION_MODEL=google/gemma-3-27b-it
```

### Google Gemini API
Native Gemini models with competitive pricing.

```bash
export GEMINI_API_KEY='your-key'
export RENG_LLM_PROVIDER=gemini
export RENG_VISION_MODEL=gemini-2.0-flash
```

### Fireworks AI
Fast inference optimized for production.

```bash
export FIREWORKS_API_KEY='your-key'
export RENG_LLM_PROVIDER=fireworks
export RENG_VISION_MODEL=google/gemma-3-27b-it
```

### Provider Selection

You can mix providers for different tasks:

```bash
# Use Gemini for vision, native Claude Code for text
export RENG_VISION_PROVIDER=gemini
export RENG_TEXT_PROVIDER=native

# Use OpenRouter for both
export RENG_LLM_PROVIDER=openrouter
```

## Gemini TTS 3.1 Flash

Generate high-quality voiceovers with Google's latest TTS model:

```python
from reng.lib.providers import GeminiTTSProvider

tts = GeminiTTSProvider()
audio_path = tts.generate_voiceover(
    text="Welcome to our presentation",
    voice_name="en-US-Neural2-D",  # or en-GB-Neural2-B, etc.
    speaking_rate=1.0,
    pitch=0.0,
    output_path=Path("welcome.mp3")
)
```

SSML support for fine-grained control:

```python
ssml = '''<speak>
    <emphasis level="strong">Welcome!</emphasis>
    <break time="500ms"/>
    <prosody rate="slow" pitch="-1st">Let me show you around.</prosody>
</speak>'''

audio_path = tts.generate_voiceover_ssml(
    ssml=ssml,
    voice_name="en-US-Neural2-D",
    output_path=Path("ssml_demo.mp3")
)
```

## Outputs

The engine writes:

- `<project_dir>/out.mp4` — the final rendered video
- `<project_dir>/out_frame01.png`, `out_frame02.png`, `out_frame03.png` — extracted keyframes from the last iteration (kept for debugging)
- `<project_dir>/actN_voiceover.mp3` — per-act voiceover (if generated)
- `<base_dir>/final.mp4` — combined video of all acts
- `<base_dir>/final_voiceover.mp3` — combined narration of all acts
- `<base_dir>/final_with_audio.mp4` — video with mixed voiceover
- `~/.recursive-animation-engine/events.jsonl` — append-only event log for `reng watch`

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENROUTER_API_KEY` | yes* | — | OpenRouter API key |
| `GEMINI_API_KEY` | yes* | — | Google Gemini API key (for TTS and vision) |
| `FIREWORKS_API_KEY` | yes* | — | Fireworks AI API key |
| `RENG_LLM_PROVIDER` | no | `openrouter` | Default provider: openrouter, gemini, fireworks, native |
| `RENG_VISION_PROVIDER` | no | `openrouter` | Vision-specific provider |
| `RENG_TEXT_PROVIDER` | no | `native` | Text generation provider (native uses Claude Code context) |
| `RENG_VISION_MODEL` | no | `google/gemma-3-27b-it` | Vision model (Gemma series recommended) |
| `RENG_TEXT_MODEL` | no | `claude-code-native` | Text model (or fallback to Gemma) |
| `HYPERFRAMES_CLI` | no | `~/hyperframes/packages/cli/dist/cli.js` | Path to built Hyperframes CLI |
| `RENG_EVENT_LOG` | no | `~/.recursive-animation-engine/events.jsonl` | Event log path |

*At least one provider key is required depending on which providers you use.

## Recommended Models

### Vision (default to Gemma series)

| Model | Provider | Strengths |
|-------|----------|-----------|
| `google/gemma-3-27b-it` | OpenRouter | Default, great vision + text |
| `google/gemma-3-12b-it` | OpenRouter | Faster, still capable |
| `gemini-2.0-flash` | Gemini API | Native Google, good pricing |

### Text

| Provider | Model | Use case |
|----------|-------|----------|
| `native` | Claude Code | Default, uses your existing context |
| OpenRouter | `anthropic/claude-sonnet-4` | High-quality reasoning |
| OpenRouter | `google/gemma-3-27b-it` | Fallback, unified model |

## When environment errors block you

If `reng render` or `reng build` fails with "not found" or a path error after **2 different attempts**:

1. **STOP** the fix loop.
2. Run `which reng ffmpeg node chromium bun` and `ls $HYPERFRAMES_CLI` to gather evidence.
3. **Report to the user** with the exact command, the exact error, and the file paths you can see.
4. Do not silently retry — a broken shell is not a coding bug.

## Available themes (Hyperframes compositions)

### 1. Soft Enterprise (default)
- Professional, clean, modern
- Warm cream backgrounds, rose-coral accents, muted text
- IBM Plex Mono or similar functional sans-serif
- Smooth 60fps transitions

### 2. Digital Craft (lo-fi tech)
- Blends digital precision with a hand-crafted, analog feel
- Tactile backgrounds (paper, linen, canvas)
- Hand-drawn strokes (sketches, arrows, scribbles) in ink/charcoal/graphite
- "On twos/threes" step-framing (8–12 fps) for stop-motion quality
- "Boil" effect — subtle constant movement in static lines
- Sketch-to-render transitions (wireframe morphs to polished UI)

## Python API

```python
from reng import (
    run,
    VideoPlan, VideoAct, VideoConcept,
    build_all_acts,
    get_provider, get_tts_provider,
    analyze
)

# Run basic recursive render
result = run("./scene", intent="loading spinner", max_iterations=3)

# Plan and build full video
from reng.lib.plan import reason_over_acts
from reng.lib.build import build_all_acts

answers = {
    "purpose": "product demo",
    "topic": "New feature walkthrough",
    "duration": "medium",
}
plan = reason_over_acts(answers)

result = build_all_acts(plan, Path("./build_output"))
print(f"Final video: {result.final_video}")
```

## Version

reng 0.2.0
