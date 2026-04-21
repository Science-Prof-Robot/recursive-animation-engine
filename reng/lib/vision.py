"""
Single-shot vision analysis via OpenRouter.

Sends one image + one question to a vision-capable LLM and returns
plain text. Used both as a standalone CLI and as a verification step
inside the recursive render loop.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
SUPPORTED_MIME_PREFIXES = (
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
)


class VisionError(RuntimeError):
    pass


def _encode_image(path: Path) -> tuple[str, str]:
    """Return (mime_type, base64_data). Raises VisionError on failure."""
    if not path.exists():
        raise VisionError(f"image not found: {path}")
    if not path.is_file():
        raise VisionError(f"not a regular file: {path}")

    size = path.stat().st_size
    if size > MAX_BYTES:
        raise VisionError(f"image too large ({size} bytes, max {MAX_BYTES})")

    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not any(mime.startswith(p) for p in SUPPORTED_MIME_PREFIXES):
        raise VisionError(
            f"unsupported image type: {mime or 'unknown'} (need PNG/JPG/GIF/WebP)"
        )

    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return mime, data


def analyze(
    image_path: str | Path,
    question: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 2048,
    timeout: float = 120.0,
) -> str:
    """
    Send an image + question to a vision model and return the text response.

    Raises VisionError on any failure (missing key, unsupported image,
    network error, bad response).
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise VisionError("OPENROUTER_API_KEY env var is not set")

    model = model or os.environ.get("VISION_MODEL", "").strip() or DEFAULT_MODEL
    mime, b64 = _encode_image(Path(image_path))
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
        "max_tokens": max_tokens,
    }

    try:
        resp = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Science-Prof-Robot/recursive-animation-engine",
                "X-Title": "recursive-animation-engine",
            },
            json=payload,
            timeout=timeout,
        )
    except httpx.RequestError as e:
        raise VisionError(f"network error: {e}")

    if resp.status_code >= 400:
        raise VisionError(f"OpenRouter returned {resp.status_code}: {resp.text}")

    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise VisionError(f"unexpected response shape: {e}")
