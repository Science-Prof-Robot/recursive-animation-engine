#!/usr/bin/env python3
"""
Vision analyzer — sends an image + question to an OpenRouter vision model
and prints the model's response. Used by the agent's vision skill when it
needs to "see" something the primary text model can't process.

Usage:
    python vision_analyze.py <image_path> "<question>"

Env vars:
    OPENROUTER_API_KEY  required
    VISION_MODEL        defaults to openai/gpt-4o-mini
"""

import base64
import mimetypes
import os
import sys
from pathlib import Path

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
SUPPORTED_MIME_PREFIXES = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")


def fail(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def encode_image(path: Path) -> tuple[str, str]:
    """Return (mime_type, base64_data) or fail."""
    if not path.exists():
        fail(f"image not found: {path}")
    if not path.is_file():
        fail(f"not a regular file: {path}")

    size = path.stat().st_size
    if size > MAX_BYTES:
        fail(f"image too large ({size} bytes, max {MAX_BYTES})")

    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not any(mime.startswith(p) for p in SUPPORTED_MIME_PREFIXES):
        fail(f"unsupported image type: {mime or 'unknown'} (need PNG/JPG/GIF/WebP)")

    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return mime, data


def analyze(image_path: str, question: str) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        fail("OPENROUTER_API_KEY env var is not set")

    model = os.environ.get("VISION_MODEL", "").strip() or DEFAULT_MODEL

    mime, b64 = encode_image(Path(image_path))
    data_url = f"data:{mime};base64,{b64}"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 2048,
    }

    try:
        # Long timeout — vision models can be slow on large images
        resp = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # Optional but recommended by OpenRouter for analytics
                "HTTP-Referer": "https://github.com/HKUDS/nanobot",
                "X-Title": "nanobot vision",
            },
            json=payload,
            timeout=120,
        )
    except httpx.RequestError as e:
        fail(f"network error: {e}")

    if resp.status_code >= 400:
        fail(f"OpenRouter returned {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        fail(f"unexpected response shape: {data} ({e})")


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    image_path, question = sys.argv[1], sys.argv[2]
    answer = analyze(image_path, question)
    print(answer)


if __name__ == "__main__":
    main()
