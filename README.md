# recursive-animation-engine

An HTML → MP4 rendering pipeline with built-in self-correction loops and multi-provider LLM support. Features structured video planning (plan → build → combine), Gemini TTS 3.1 Flash voiceover generation, and vision verification with multiple backends.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PLAN PHASE                                  │
│  User answers → LLM reasons over acts → Structured VideoPlan       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BUILD PHASE                                  │
│  For each act: Render → Verify keyframes → Vision check → Patch     │
│  + Generate voiceover with Gemini TTS 3.1 Flash                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        COMBINE PHASE                                │
│  Stitch acts → Mix audio → Deliver final MP4                        │
└─────────────────────────────────────────────────────────────────────┘
```

Always-on progress viewer:

```
$ reng watch
reng watch — tailing ~/.recursive-animation-engine/events.jsonl

14:02:01 a1b2c3 ▶ run start   ./build_output/act01  max=3
14:02:01 a1b2c3 ■ iteration 1
14:02:01 a1b2c3   render…
14:02:08 a1b2c3   ✓ rendered out.mp4 (7.2s)
14:02:08 a1b2c3   extracting 3 keyframe(s)…
14:02:10 a1b2c3     ✓ out_frame01.png OK
14:02:12 a1b2c3     ◦ out_frame02.png Bar exceeds container at 50% — text "100%" clips off right edge.
14:02:14 a1b2c3     ✓ out_frame03.png OK
14:02:14 a1b2c3 ◦ iteration 1 — 1 issue(s)
14:02:14 a1b2c3 ■ iteration 2
14:02:14 a1b2c3   render…
14:02:22 a1b2c3   ✓ rendered out.mp4 (7.8s)
14:02:22 a1b2c3     ✓ out_frame01.png OK
14:02:24 a1b2c3     ✓ out_frame02.png OK
14:02:26 a1b2c3     ✓ out_frame03.png OK
14:02:26 a1b2c3 ✓ iteration 2 passed
14:02:26 a1b2c3 ■ run passed (2 iter) → out.mp4
```

## Features

- **Multi-provider LLM support**: OpenRouter, Google Gemini API, Fireworks AI
- **Default vision model**: Gemma 3 (latest) for cost-effective verification
- **Structured planning**: Interactive plan phase with user questions → act-based reasoning
- **Act-by-act building**: Build complex videos scene by scene with vision verification per act
- **Gemini TTS 3.1 Flash**: Generate high-quality voiceovers with SSML support
- **Native Claude Code integration**: Text generation uses Claude Code context by default
- **Vision verification loops**: Render → extract keyframes → vision check → iterate

## Install

From [PyPI](https://pypi.org/project/recursive-animation-engine/) (recommended):

```bash
pip install recursive-animation-engine
```

Latest from GitHub (if you need unreleased changes):

```bash
pip install git+https://github.com/Science-Prof-Robot/recursive-animation-engine
```

Or from source:

```bash
git clone https://github.com/Science-Prof-Robot/recursive-animation-engine
cd recursive-animation-engine
pip install -e .
```

### System dependencies

| Tool | Install |
|------|---------|
| [`bun`](https://bun.sh) | `curl -fsSL https://bun.sh/install \| bash` |
| `ffmpeg` | `apt-get install ffmpeg` / `brew install ffmpeg` |
| `chromium` | `apt-get install chromium` (set `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`) |
| `node` | `apt-get install nodejs` / use nvm |
| [Hyperframes](https://github.com/heygen-com/hyperframes) | `git clone` → `bun install` → `bun run build` |

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | yes* | — | OpenRouter API key |
| `GEMINI_API_KEY` | yes* | — | Google Gemini API key (for TTS and native Gemini) |
| `FIREWORKS_API_KEY` | yes* | — | Fireworks AI API key |
| `RENG_LLM_PROVIDER` | no | `openrouter` | Default provider: `openrouter`, `gemini`, `fireworks`, `native` |
| `RENG_VISION_PROVIDER` | no | `openrouter` | Provider for vision tasks |
| `RENG_TEXT_PROVIDER` | no | `native` | Text generation provider (`native` = Claude Code context) |
| `RENG_VISION_MODEL` | no | `google/gemma-3-27b-it` | Vision model ID |
| `HYPERFRAMES_CLI` | no | `~/hyperframes/...` | Path to Hyperframes CLI |
| `RENG_EVENT_LOG` | no | `~/.recursive-animation-engine/events.jsonl` | Event log path |

*At least one provider key is required depending on your setup.

## Usage

### Full workflow: Plan → Build → Combine

#### 1. Plan Phase

Interactively create a structured video plan:

```bash
reng plan -o video_plan.json
```

This asks about:
- Purpose and topic
- Target duration (short/medium/long)
- Visual style preferences
- Voiceover requirements
- Target audience

Then reasons over your answers to produce acts with timing and scripts.

#### 2. Build Phase

Build each act with vision loop verification:

```bash
reng build video_plan.json ./build_output
```

This:
- Creates act subdirectories (`act01/`, `act02/`, etc.)
- Renders each act with recursive verification
- Generates voiceover per act (if scripted)
- Combines all acts into `final.mp4`
- Mixes voiceover with video

Options:
- `--max-iterations N` - Max render-verify cycles per act (default: 3)
- `--no-voiceover` - Skip TTS generation
- `--no-combine` - Don't concatenate acts
- `--no-mix-audio` - Don't mix voiceover with final video

#### 3. Voiceover Only

Generate voiceover with Gemini TTS 3.1 Flash:

```bash
# Simple text
reng voiceover "Welcome to our product demo" -o intro.mp3

# From script file
reng voiceover --file script.txt -o narration.mp3

# Custom voice and rate
reng voiceover "Hello world" -o hello.mp3 --voice en-GB-Neural2-B --rate 0.9

# SSML for fine-grained control
reng voiceover '<speak>Hello <break time="1s"/> World</speak>' -o ssml.mp3
```

### Legacy: One-shot render

For simple single-scene renders:

```bash
reng render ./renders/progress-bar --intent "progress bar fills 0% → 100% smoothly"
```

Exit code `0` = passed or hit max iterations (check `status` in output).
Exit code `1` = render or vision errored.

### Live progress viewer

```bash
# Watch all activity
reng watch

# Follow specific run
reng watch --follow-run a1b2c3d4

# Replay last hour
reng watch --since 1h
```

### Vision and verification

```bash
# Vision check with default Gemma
reng vision screenshot.png "What error is shown here?"

# Use specific provider
reng vision screenshot.png "What do you see?" --provider gemini

# Specific model
reng vision screenshot.png "Describe the layout" --model google/gemma-3-27b-it

# Extract keyframes
reng verify input.mp4 --frames 5
```

### Provider management

```bash
# Test all configured providers
reng provider test

# List recommended models
reng provider list-models

# Show environment setup help
reng provider env
```

## Python API

### Full workflow

```python
from reng.lib.plan import reason_over_acts, get_planning_questions
from reng.lib.build import build_all_acts

# Create plan from user answers
answers = {
    "purpose": "product demo",
    "topic": "New feature walkthrough",
    "duration": "medium",
    "voiceover": "yes, formal",
}
plan = reason_over_acts(answers)

# Build all acts with vision verification
result = build_all_acts(
    plan,
    Path("./build_output"),
    max_iterations=3,
    generate_voiceovers=True,
    combine_acts=True,
)

print(f"Status: {result.status}")
print(f"Final video: {result.final_video}")
print(f"Combined voiceover: {result.combined_voiceover}")
```

### Voiceover generation

```python
from reng.lib.providers import GeminiTTSProvider

tts = GeminiTTSProvider()

# Simple generation
audio = tts.generate_voiceover(
    text="Welcome to our presentation!",
    voice_name="en-US-Neural2-D",
    output_path=Path("welcome.mp3")
)

# SSML for control
ssml = '''<speak>
    <emphasis level="strong">Welcome!</emphasis>
    <break time="500ms"/>
    <prosody rate="slow" pitch="-1st">Let me show you around.</prosody>
</speak>'''

audio = tts.generate_voiceover_ssml(
    ssml=ssml,
    voice_name="en-US-Neural2-D",
    output_path=Path("ssml_demo.mp3")
)
```

### Custom provider usage

```python
from reng.lib.providers import get_provider, get_vision_model_spec

# Use Gemini for vision
provider = get_provider("gemini")
model_spec = get_vision_model_spec()

result = provider.analyze(
    question="What do you see in this image?",
    image_path=Path("frame.png"),
    model_spec=model_spec
)
```

## Multi-Provider Configuration

### OpenRouter (default)
Unified API for 100+ models.

```bash
export OPENROUTER_API_KEY='your-key'
export RENG_LLM_PROVIDER=openrouter
export RENG_VISION_MODEL=google/gemma-3-27b-it
```

### Google Gemini API
Native Gemini with competitive pricing.

```bash
export GEMINI_API_KEY='your-key'
export RENG_LLM_PROVIDER=gemini
export RENG_VISION_MODEL=gemini-2.0-flash
```

### Fireworks AI
Fast inference for production.

```bash
export FIREWORKS_API_KEY='your-key'
export RENG_LLM_PROVIDER=fireworks
```

### Mix and match

```bash
# Use Gemini for vision, native Claude Code for text
export RENG_VISION_PROVIDER=gemini
export RENG_TEXT_PROVIDER=native

# OpenRouter for both
export RENG_LLM_PROVIDER=openrouter
export RENG_VISION_MODEL=google/gemma-3-27b-it
```

## Recommended Models

### Vision

| Model | Provider | When |
|-------|----------|------|
| `google/gemma-3-27b-it` | OpenRouter | Default, excellent vision + text |
| `google/gemma-3-12b-it` | OpenRouter | Faster, still capable |
| `gemini-2.0-flash` | Gemini API | Native Google, good pricing |

### Text

| Provider | Model | Use case |
|----------|-------|----------|
| `native` | Claude Code | Default, uses existing context |
| OpenRouter | `anthropic/claude-sonnet-4` | High-quality reasoning |
| OpenRouter | `google/gemma-3-27b-it` | Unified vision+text |

## Design Principles

- **Flexible providers**: Use OpenRouter for unified access, Gemini for TTS/natives, Fireworks for speed
- **Cost-effective verification**: Gemma provides excellent vision at lower cost than alternatives
- **Native integration**: Text generation defaults to Claude Code context (no extra API calls)
- **Structured workflow**: Plan phase structures complexity, build phase executes with verification
- **Per-act verification**: Each scene verified independently before combination
- **Deterministic keyframe sampling**: Always samples 10%–90% of duration to avoid fade frames
- **Hard iteration caps**: Max 3 loops per act prevents runaway cost
- **File-based event bus**: Append-only NDJSON log enables any number of watchers

## Swapping the Renderer

The engine is renderer-agnostic. `reng/lib/render.py` is a ~60-line shim around the Hyperframes CLI. To use Remotion, Manim, Playwright recording, etc., replace that module's `render()` function — the rest of the pipeline (verify, vision, loop, events) stays the same.

## License

MIT — see [LICENSE](./LICENSE).
