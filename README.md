# nanobot-skills

A pair of composable skills for [nanobot](https://github.com/HKUDS/nanobot) that let a cheap text-only agent render animations and *verify them visually* through a vision-capable LLM.

Built and battle-tested in production on Railway. Works with any nanobot deployment.

```
 your-agent (Kimi / GLM / whatever)
        │
        ├── writes HTML/CSS/JS composition
        │
        ├── hyperframes-render   ──► out.mp4          (chromium + bun + ffmpeg)
        │
        ├── visual_verify.py     ──► 3 keyframes      (ffmpeg)
        │
        └── vision_analyze.py    ──► text description (OpenRouter vision model)
                                      │
                                      └── if issues, agent iterates
```

## What's inside

| Skill | What it does |
|-------|--------------|
| [`vision`](./skills/vision) | Gives a text-only agent the ability to "see" images. One-shot call to an OpenRouter vision model (GPT-4o, Claude, Gemini, etc.) and returns plain-text analysis. |
| [`hyperframes-render`](./skills/hyperframes-render) | HTML → MP4 rendering pipeline with a mandatory self-correction loop: render, extract keyframes, vision-verify each frame, iterate up to 3× until visually correct. |

The two skills are designed to work together — `hyperframes-render` calls `vision` after each render to check its own output and self-correct.

## Why this exists

Most cheap fast models (Kimi K2.5, GLM, Llama, etc.) are **text-only**. They can write HTML and CSS, but they can't *see* the rendered output to know if it looks right. You either:

1. Pay for a vision model on every message (expensive), or
2. Blindly ship whatever the text model produces (buggy output), or
3. **Route vision calls only when needed** ← this repo

The `vision` skill is a surgical escape hatch: the primary model stays cheap, and vision only runs during verification loops. The `hyperframes-render` skill turns that into a concrete workflow for animated video rendering.

## Install

Drop the skills into your nanobot workspace:

```bash
cd ~/.nanobot/workspace
git clone https://github.com/Science-Prof-Robot/nanobot-skills /tmp/nanobot-skills
cp -r /tmp/nanobot-skills/skills/* ./skills/
```

nanobot auto-discovers anything under `workspace/skills/`, so the next message will see both skills.

### Environment variables

| Variable | Required by | Purpose |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | `vision` | OpenRouter API key ([get one](https://openrouter.ai/keys)) |
| `VISION_MODEL` | `vision` (optional) | Defaults to `openai/gpt-4o-mini` |
| `HYPERFRAMES_CLI` | `hyperframes-render` (optional) | Path to built `dist/cli.js`; defaults to `~/hyperframes/packages/cli/dist/cli.js` |

### System dependencies (for `hyperframes-render`)

| Tool | Install |
|------|---------|
| [`bun`](https://bun.sh) | `curl -fsSL https://bun.sh/install \| bash` |
| `ffmpeg` | `apt-get install ffmpeg` or `brew install ffmpeg` |
| `chromium` | `apt-get install chromium` (point puppeteer at it with `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`) |
| `node` | `apt-get install nodejs` or use nvm |
| [Hyperframes](https://github.com/heygen-com/hyperframes) | `git clone && bun install && bun run build` |

## Quick start

### Just vision (no rendering)

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python skills/vision/vision_analyze.py ./screenshot.png "What text is in this image?"
```

### Full rendering + verification loop

From inside your nanobot chat, just ask:

> Create a 10-second animation showing a progress bar filling up from 0% to 100% with a smooth ease-out curve.

The agent will:

1. Write the HTML/CSS/JS composition under `renders/progress-bar/`
2. Call `hyperframes-render renders/progress-bar` → `out.mp4`
3. Extract 3 keyframes via `visual_verify.py` (10%, 50%, 90% of duration)
4. Run `vision_analyze.py` on each keyframe to confirm the progress bar is rendering correctly
5. Iterate if anything looks off, up to 3 times
6. Deliver the final MP4 with an iteration count

## Design principles

### Cheap primary, expensive verification

The text model does 99% of the work. Vision only runs 3 times per iteration (one per keyframe), which is ~$0.001 with `gpt-4o-mini`. A 3-iteration render costs about $0.01 in vision calls.

### Explicit failure modes

If a CLI command fails twice with "not found", the skill tells the agent to **stop and report** instead of brute-forcing. This prevents the "silent spinning" failure mode where an agent burns tokens on a broken environment.

### Deterministic keyframe sampling

`visual_verify.py` samples evenly across the 10%–90% duration window, avoiding black first/last frames. Three samples catches most visual bugs (wrong start state, missing middle transition, early cutoff).

### Iteration cap

Hard-coded max of 3 loops per render. Prevents runaway cost when output is "close enough but not perfect" — the skill ships the best version and tells the user what's still off.

## Recommended vision models

| Model | Best for |
|-------|----------|
| `openai/gpt-4o-mini` | Cheap and fast; good default |
| `openai/gpt-4o` | Higher detail, more nuance |
| `anthropic/claude-sonnet-4-6` | Best for complex scenes and long reasoning |
| `google/gemini-2.0-flash` | Fastest, huge context, good for batch verification |

Switch by setting `VISION_MODEL=<any-openrouter-model-id>`.

## Tested with

- [nanobot](https://github.com/HKUDS/nanobot) v0.1.5
- Deployed on Railway behind a Telegram + AgentMail gateway
- Primary model: Kimi K2.5 Turbo (via Fireworks) and GLM (via OpenRouter)
- Vision model: `openai/gpt-4o-mini`
- Hyperframes: latest `main` from `heygen-com/hyperframes`

## License

MIT — see [LICENSE](./LICENSE).

## Contributing

PRs welcome. Ideas:

- `vision-diff` skill (compare two screenshots and describe differences)
- More render themes in `hyperframes-render` (retro pixel, motion graphics, etc.)
- Benchmarks: vision accuracy vs. cost across different models
- Support for other rendering engines (Remotion, Manim)
