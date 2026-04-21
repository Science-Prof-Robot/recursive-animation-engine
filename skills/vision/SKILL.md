---
name: vision
description: Analyze images and screenshots using a vision-capable LLM. Use this whenever you need to "see" an image file (PNG, JPG, GIF, WebP), screenshot, video frame, or any visual content. Text-only models cannot process pixels — always use this skill instead of read_file for image analysis.
---

# Vision Analysis

Lets a text-only agent "see" by routing a single image + question to a vision-capable LLM on OpenRouter (GPT-4o, Claude, Gemini, etc.). Returns a plain-text description you can reason over.

## Usage

```bash
python skills/vision/vision_analyze.py <image_path> "<question>"
```

- `<image_path>` — absolute or relative path to a local image file
- `<question>` — what you want to know about the image

## When to use

- Verifying that a UI or animation rendered correctly (layout, spacing, timing)
- Reading text from a screenshot
- Analyzing a chart, graph, or diagram
- Checking video frames extracted via ffmpeg (pairs with `hyperframes-render`)
- Comparing before/after screenshots
- Any task where you need to see the visual output of code you wrote

## Examples

**Verify an animation frame:**
```bash
python skills/vision/vision_analyze.py /tmp/frame_001.png \
  "Is the spinning circle centered? Describe any visible artifacts."
```

**Read text from a screenshot:**
```bash
python skills/vision/vision_analyze.py ~/screenshots/error.png \
  "What does this error message say?"
```

**Compare layouts:**
```bash
python skills/vision/vision_analyze.py ./before.png "Describe the layout, spacing, and color scheme."
python skills/vision/vision_analyze.py ./after.png  "Describe the layout, spacing, and color scheme."
```

## Configuration

Set these environment variables:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENROUTER_API_KEY` | yes | — | Your OpenRouter API key |
| `VISION_MODEL` | no | `openai/gpt-4o-mini` | Any OpenRouter vision-capable model |

### Recommended vision models

| Model | Best for |
|-------|----------|
| `openai/gpt-4o-mini` | Cheap, fast, good general quality |
| `openai/gpt-4o` | Higher quality, more detail |
| `anthropic/claude-sonnet-4-6` | Best for detailed analysis, long reasoning |
| `google/gemini-2.0-flash` | Fast, cheap, large context |

## Limitations

- Max image size: 20 MB
- Supported formats: PNG, JPG, JPEG, GIF, WebP
- Returns plain text; chain multiple calls for complex multi-image reasoning
