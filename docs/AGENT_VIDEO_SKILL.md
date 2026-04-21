# Agent checklist: recursive video (Hyperframes + reng)

Use this with [SKILL.md](../SKILL.md) in the repo root. Full install and env vars: [README.md](../README.md).

## Preflight (before any QnA)

- [ ] **Node.js 22+** (`node -v`)
- [ ] **ffmpeg** on PATH (`ffmpeg -version`)
- [ ] **Chromium/Chrome** available for Hyperframes (set `PUPPETEER_EXECUTABLE_PATH` if needed)
- [ ] **`reng` installed** (`pip install -e .` in this repo or `pip install recursive-animation-engine`)
- [ ] **Hyperframes CLI**: from this repo root, `npm install` completed; verify `node_modules/.bin/hyperframes` exists **or** `HYPERFRAMES_CLI` points to that binary or a legacy `cli.js`
- [ ] **Vision API key** set (e.g. `OPENROUTER_API_KEY`) — required for `reng render`, `reng build`, `reng vision`, plan reasoning when not using native text
- [ ] Optional: `npm test` at repo root (hyperframes + ffmpeg + unit smoke)

## Phase 1 — Discover (QnA)

Capture at least:

- [ ] Goal (explainer, promo, tutorial, social clip, etc.)
- [ ] Audience and tone
- [ ] Target length (seconds or short/medium/long)
- [ ] Visual style (minimal, bold, corporate, etc.)
- [ ] Voiceover yes/no and tone
- [ ] Brand assets (colors, logo, fonts) if any
- [ ] **Explicit:** user does **not** want a separate web app, dashboard, or deployable site (default = video only)
- [ ] **Explicit:** user does **not** want `hyperframes preview` or other long-running dev servers unless they ask

Write a short **brief** (e.g. `video-workspaces/<slug>/brief.md`) before scaffolding.

## Phase 2 — Plan

- [ ] User **confirmed** the brief (or said **autopilot** / “go ahead” — then you may skip re-confirmation for render)
- [ ] Run plan with LLM when keys allow:
  - `export RENG_TEXT_PROVIDER=openrouter` and `OPENROUTER_API_KEY` set
  - `reng plan --llm --provider openrouter -o video-workspaces/<slug>/plan.json`
- [ ] Else: `reng plan -o video-workspaces/<slug>/plan.json` (interactive stdin)
- [ ] User reviewed plan summary (acts, duration, voiceover flags)

## Phase 3 — Scaffold

Under `video-workspaces/<slug>/` (or agreed root):

- [ ] `plan.json` present (from plan phase)
- [ ] **Single-scene path:** e.g. `mkdir -p acts && cd acts && npx hyperframes init act01` — pass `acts/act01` to `reng render`
- [ ] **Multi-act path:** `reng build` expects act dirs; create `act01`, `act02`, … each with a Hyperframes project as required by your build pipeline
- [ ] Do **not** add unrelated React/Next apps unless the user explicitly asked

## Phase 4 — Author

- [ ] Edit `index.html` (and assets) per Hyperframes composition rules
- [ ] Keep scope aligned with brief and plan acts

## Phase 5 — Verify loop

- [ ] **Only after user confirmation** (or autopilot): run `reng render <project_dir> --intent "..."` per act or full `reng build plan.json ./build_output`
- [ ] Optional second terminal: `reng watch`
- [ ] On vision failures: patch HTML/CSS/JS from `iteration_result.issues`, re-run render (max iterations default 3)
- [ ] Read `~/.recursive-animation-engine/events.jsonl` if `reng watch` is not used

## Phase 6 — Deliver

- [ ] **MP4 exists** (`out.mp4` in project dir, or `final*.mp4` under build output for multi-act)
- [ ] **Keyframe PNGs** present for last iteration if debugging
- [ ] Duration roughly matches plan order-of-magnitude
- [ ] **User sign-off:** show path to final video and one-line summary of passes vs issues

## If blocked after two different fixes

1. Stop the blind retry loop.
2. Run `reng provider env`, `which reng ffmpeg node`, `ls node_modules/.bin/hyperframes` (from engine repo root).
3. Report exact command, stderr, and paths to the user.

## Legacy Hyperframes (optional)

Only if npm path is not used: build [Hyperframes monorepo](https://github.com/heygen-com/hyperframes) with Bun and set `HYPERFRAMES_CLI` to `packages/cli/dist/cli.js`. Not the default path.
