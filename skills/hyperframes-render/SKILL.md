---
name: hyperframes-render
description: Render HTML/CSS/JS animations to MP4 video using the Hyperframes CLI, then visually verify the output frame-by-frame using the vision skill. Use when the user asks for animations, motion graphics, video explainers, or rendered visualizations.
---

# Hyperframes Render (with Visual Self-Correction)

Renders HTML compositions to `.mp4` and verifies the output is correct by extracting keyframes and analyzing them with the `vision` skill. Pairs a fast, cheap primary text model with a vision model that only runs when verification is needed.

## Prerequisites

| Tool | Purpose |
|------|---------|
| `bun` | Build + script runner for Hyperframes workspace |
| `node` | Runs the compiled CLI (`dist/cli.js`) |
| `ffmpeg` | Keyframe extraction |
| `chromium` (or Chrome) | Headless rendering via puppeteer |
| Hyperframes monorepo | Cloned and built into `packages/cli/dist/` |
| `vision` skill | Installed and configured with `OPENROUTER_API_KEY` |

Install the Hyperframes monorepo (once):

```bash
git clone https://github.com/heygen-com/hyperframes
cd hyperframes
bun install
bun run build
```

Install the `hyperframes-render` wrapper so it is globally callable:

```bash
sudo ln -sf "$(pwd)/packages/cli/dist/cli.js" /usr/local/bin/hyperframes
# then copy the wrapper from this skill:
sudo cp skills/hyperframes-render/hyperframes-render /usr/local/bin/
sudo chmod +x /usr/local/bin/hyperframes-render
```

## Available themes

### 1. Soft Enterprise (Default)
- **Aesthetic**: Professional, clean, modern.
- **Palette**: Warm cream backgrounds, rose-coral accents, muted text.
- **Typography**: IBM Plex Mono or similar functional sans-serif.
- **Motion**: Smooth, high-fidelity transitions (60fps).

### 2. Digital Craft (Lo-fi Tech)
- **Aesthetic**: Blends digital precision with an analog, hand-crafted feel.
- **Visual language**:
  - **Tactile textures** — paper, linen, canvas backgrounds instead of flat hex colors.
  - **Human stroke** — hand-drawn elements (sketches, arrows, scribbles) in ink, charcoal, or graphite.
  - **Modern minimalism** — high-contrast professional typography offsetting organic textures.
- **Animation nuances**:
  - **Step-framing** — hand-drawn elements animated "on twos" or "on threes" (8–12 fps) for a jittery, stop-motion quality.
  - **Write-on effects** — trim paths or masks to simulate pen drawing.
  - **The "boil" effect** — slight, constant movement in static hand-drawn lines to simulate life.
- **Transitions**:
  - **Sketch-to-render** — moving from loose scribbled wireframes to high-fidelity UI.
  - **Analog annotations** — hand-drawn circles or underlines pointing at digital elements.
- **Pacing**: Intentional stillness and negative space; reserve smooth motion only for functional software elements (scrolling, clicking).

## Commands

The CLI is wrapped on PATH after installation:

| Command | What it does |
|---------|--------------|
| `hyperframes-render <project_dir>` | Render a project's composition to `out.mp4` |
| `hyperframes <subcommand>` | Full CLI surface: `init`, `render`, `dev`, etc. |

Fallback if the wrapper is missing:

```bash
node /path/to/hyperframes/packages/cli/dist/cli.js render <project_dir>
```

## Self-correction loop (MANDATORY)

For every animation request, the agent follows this loop:

1. **Draft** — write or update the HTML/CSS/JS composition under `renders/<name>/`.
2. **Render** — `hyperframes-render renders/<name>` produces `renders/<name>/out.mp4`.
3. **Extract keyframes** — `python skills/hyperframes-render/visual_verify.py renders/<name>/out.mp4`
4. **Vision check** — for each extracted PNG:
   ```bash
   python skills/vision/vision_analyze.py <png_path> \
     "Describe what you see. Is the layout, timing, color, and text correct per the user's request? List any issues."
   ```
5. **Iterate** — if any frame fails the check, fix the HTML/CSS and go back to step 2.
6. **Stop conditions:**
   - All keyframes (start, middle, end) approved → ship the MP4.
   - 3 iterations completed → ship the best version and report what's still off.

## Reporting

End every animation delivery with:

> Animation complete (Iteration N/3). Visual verification: `<pass|partial>`. `<one-line summary>`.

## When environment errors block you

If a command fails with "not found" or a path error after **2 different tactical attempts**:

1. **STOP** the fix loop.
2. Run `which <command>` and `ls <expected_path>` to gather evidence.
3. **Report to the user** with: the exact command you tried, the exact error, and the file paths visible via `list_dir`.
4. Do not silently retry the same shell command — it wastes tokens and creates the illusion of progress.

## Why this design

- **Cheap primary model** writes the HTML/CSS and drives the loop (text-only is enough).
- **Vision model only runs during verification** (3 calls per iteration, max 9 total).
- **ffmpeg-based keyframe sampling** keeps verification fast and deterministic (start/middle/end slices).
- **Hard iteration cap** (3) prevents runaway loops when output is close-enough but not perfect.
