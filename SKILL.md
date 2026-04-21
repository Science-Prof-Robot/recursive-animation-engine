---
name: recursive-animation-engine
description: Render HTML/CSS/JS animations to MP4 and verify them visually in a recursive self-correction loop. Use when the user asks for animations, motion graphics, video explainers, or any rendered visual output where correctness matters. The engine handles render → extract keyframes → vision-check → iterate automatically, so you only need to write good HTML and let the loop correct it.
---

# Recursive Animation Engine

A single pipeline that renders HTML compositions to MP4 and uses a vision model to verify the output is correct. Runs up to N iterations, so minor rendering issues get caught and corrected without human review.

## How it works

```
1. you write HTML/CSS/JS
2. engine renders it to MP4                       (chromium + bun + ffmpeg)
3. engine extracts 3 keyframes from the MP4       (ffmpeg)
4. engine asks a vision model: "is this correct?" (OpenRouter)
5. if any frame fails → you patch the HTML → loop back to step 2
6. max 3 iterations, then ship the best version
```

All progress is streamed to `~/.recursive-animation-engine/events.jsonl` — run `reng watch` in a separate terminal to see what's happening in real time.

## Using it from an agent

### Fully-automated (one-shot)

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

### Standalone vision check (no rendering)

```bash
reng vision screenshot.png "What error is shown here?"
```

## When to use

- Any animation / motion graphic / video explainer request
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

## Outputs

The engine writes:

- `<project_dir>/out.mp4` — the final rendered video
- `<project_dir>/out_frame01.png`, `out_frame02.png`, `out_frame03.png` — extracted keyframes from the last iteration (kept for debugging)
- `~/.recursive-animation-engine/events.jsonl` — append-only event log for `reng watch`

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENROUTER_API_KEY` | yes | — | Your OpenRouter API key |
| `VISION_MODEL` | no | `openai/gpt-4o-mini` | Any OpenRouter vision-capable model |
| `HYPERFRAMES_CLI` | no | `~/hyperframes/packages/cli/dist/cli.js` | Path to built Hyperframes CLI |
| `RENG_EVENT_LOG` | no | `~/.recursive-animation-engine/events.jsonl` | Event log path |

## When environment errors block you

If `reng render` fails with "not found" or a path error after **2 different attempts**:

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
