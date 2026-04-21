# recursive-animation-engine

An HTML → MP4 rendering pipeline with a built-in self-correction loop. Renders, extracts keyframes, asks a vision model "is this correct?", and iterates until it is — or reports what's still wrong.

```
HTML/CSS/JS  ─────►  MP4  ─────►  keyframes  ─────►  vision model
     ▲                                                     │
     └─────────  if anything is off, patch and retry  ─────┘
                          (up to 3 loops)
```

Always-on progress viewer lets you see exactly what the engine is doing in real time:

```
$ reng watch
reng watch — tailing ~/.recursive-animation-engine/events.jsonl

14:02:01 a1b2c3 ▶ run start   ./renders/progress-bar  max=3
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

## Why

Cheap text models (Kimi, GLM, Llama, open-source Gemini variants) write great HTML and CSS — but they're blind. They can't tell you if the progress bar actually animates, if text is clipping, if the chart labels landed in the right place. You end up either:

1. Paying for a multimodal model on every single message (expensive), or
2. Blindly shipping whatever was generated (buggy), or
3. **Routing vision calls only into the verification loop** ← this engine

Vision fires 3× per iteration (one per keyframe). A full successful run costs ~$0.003 with `gpt-4o-mini`. A 3-iteration worst-case is ~$0.01.

## How it works

Five components, one loop.

| Component | What it does |
|-----------|--------------|
| **Render** | Shells out to the Hyperframes CLI → produces an MP4 from an HTML project directory |
| **Verify** | `ffmpeg` extracts N keyframes from the interior 10%–90% of the video (avoids black fade frames) |
| **Vision** | One `POST /chat/completions` per frame to OpenRouter with the image + a verification prompt |
| **Engine** | Orchestrates render → verify → vision, emits events, decides when to stop |
| **Watch** | Tails the shared event log and pretty-prints in real time |

The loop terminates when:
- Every keyframe comes back with `OK` from the vision model, **or**
- `max_iterations` (default 3) is reached — ships the best version

Between failed iterations, an optional `patch_fn` callback runs so an agent can edit the HTML/CSS before the next render.

## Install

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

| Variable | Required | Default |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | yes | — |
| `VISION_MODEL` | no | `openai/gpt-4o-mini` |
| `HYPERFRAMES_CLI` | no | `~/hyperframes/packages/cli/dist/cli.js` |
| `RENG_EVENT_LOG` | no | `~/.recursive-animation-engine/events.jsonl` |

## Usage

### One-shot render

```bash
reng render ./renders/progress-bar --intent "progress bar fills 0% → 100% smoothly"
```

Exit code `0` = passed or hit max iterations (check `status` in output).
Exit code `1` = render or vision errored.

### Live progress viewer (always-on)

Run this in a second terminal and leave it open:

```bash
reng watch
```

Filter to one run by ID:

```bash
reng watch --follow-run a1b2c3d4
```

Replay the last hour of history, then tail forever:

```bash
reng watch --since 1h
```

### Standalone vision (no render)

```bash
reng vision screenshot.png "What error is shown here?"
```

### Standalone keyframe extraction

```bash
reng verify input.mp4 --frames 5
```

### Programmatic (Python)

```python
from reng.lib.engine import run

def patch(result):
    # result.issues contains vision's feedback per failed frame
    # edit HTML/CSS files in the project dir based on those issues
    for issue in result.issues:
        apply_my_fix(result.iteration, issue)

outcome = run(
    "./renders/progress-bar",
    intent="progress bar fills 0% → 100% smoothly",
    max_iterations=3,
    patch_fn=patch,
)

print(outcome.status)        # "passed" | "max_iterations" | "error"
print(outcome.final_video)   # Path to the final MP4
for it in outcome.iterations:
    print(it.iteration, it.passed, it.issues)
```

## Agent integration

If you're wiring this into an agent framework (nanobot, autogen, langgraph, custom), drop `SKILL.md` into your agent's skill/tool definitions. It describes the engine, when to use it, and the CLI surface. The engine emits events to a shared log so your agent can also `tail -f` the log for real-time updates — no special IPC needed.

## Swapping the renderer

The engine is renderer-agnostic. `reng/lib/render.py` is a ~60-line shim around the Hyperframes CLI. To use Remotion, Manim, Playwright recording, etc., replace that module's `render()` function — the rest of the pipeline (verify, vision, loop, events) stays the same.

## Recommended vision models

| Model | When |
|-------|------|
| `openai/gpt-4o-mini` | Default; cheapest that's still good at general UI checks |
| `openai/gpt-4o` | When verification quality matters more than $/run |
| `anthropic/claude-sonnet-4-6` | Complex scenes, multi-element reasoning |
| `google/gemini-2.0-flash` | Fastest; large context if you pass multiple frames later |

## Design principles

- **Cheap primary, expensive verification.** The engine doesn't care what wrote the HTML — use the cheapest model that's competent. Vision only pays off at verification time.
- **Deterministic keyframe sampling.** Always samples 10%–90% of duration so we never verify a fade-in black frame as "broken".
- **Hard iteration cap.** Max 3 loops. Prevents runaway cost when output is close-enough but never perfect.
- **Explicit failure modes.** If the render binary is missing or the vision API errors, the engine stops and reports. No silent retries, no "spinning" illusion.
- **File-based event bus.** Append-only NDJSON log means any number of watchers can observe without coupling to the engine. Works across processes, containers, SSH sessions.

## License

MIT — see [LICENSE](./LICENSE).
