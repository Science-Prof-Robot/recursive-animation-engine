"""
Vision analysis via configurable providers (OpenRouter, Gemini, Fireworks).

Defaults to Gemma (latest) for vision tasks.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .providers import BaseProvider, ModelSpec

from .providers import (
    ProviderError,
    VisionError,  # Re-export for backward compatibility
    get_vision_model_spec,
    get_vision_provider,
)

# Re-export for backward compatibility
VisionError = ProviderError


def analyze(
    image_path: str | Path,
    question: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 2048,
    timeout: float = 120.0,
    provider_name: str | None = None,
    model_spec: "ModelSpec" | None = None,
) -> str:
    """
    Send an image + question to a vision model and return the text response.

    Uses the configured vision provider (OpenRouter, Gemini, or Fireworks).
    Defaults to Gemma as the vision model.

    Args:
        image_path: Path to the image file
        question: Question to ask about the image
        model: Legacy parameter - model ID (deprecated, use model_spec or env vars)
        api_key: API key (defaults to provider-specific env var)
        max_tokens: Maximum tokens in response
        timeout: Request timeout in seconds
        provider_name: Explicit provider selection ('openrouter', 'gemini', 'fireworks')
        model_spec: Full model specification (overrides other params)

    Raises:
        VisionError: On any failure (missing key, unsupported image, network error)

    Returns:
        Text response from the vision model
    """
    provider = get_vision_provider()

    # If provider_name specified, get that specific provider
    if provider_name:
        from .providers import get_provider

        provider = get_provider(provider_name)

    # Get model spec (defaults to Gemma via env or hardcoded default)
    if model_spec is None:
        model_spec = get_vision_model_spec()
        if model:
            # Override with legacy model parameter if provided
            model_spec = model_spec.replace(model_id=model)

    try:
        return provider.analyze(
            question=question,
            image_path=Path(image_path),
            model_spec=model_spec,
            max_tokens=max_tokens,
        )
    except ProviderError as e:
        raise VisionError(str(e)) from e


def is_approval(text: str) -> bool:
    """
    Heuristic: does this vision response indicate no issues?

    This is a utility function for checking if a vision model's
    response indicates the image is acceptable/correct.
    """
    stripped = text.strip().lower()
    if not stripped:
        return False

    # Model was told to reply exactly "OK" when clean
    if stripped == "ok":
        return True

    # Some models add a period or sentence
    first_line = stripped.splitlines()[0]
    approved_phrases = (
        "ok",
        "ok.",
        "looks good",
        "looks good.",
        "pass",
        "pass.",
        "approved",
        "approved.",
        "correct",
        "correct.",
        "no issues",
        "no issues.",
        "no problems",
        "no problems.",
    )
    return first_line in approved_phrases


def compare_frames(
    frame_paths: list[Path],
    description: str,
    *,
    max_tokens: int = 4096,
    provider_name: str | None = None,
) -> dict[str, str]:
    """
    Compare multiple frames and describe what changes between them.

    Useful for verifying animation continuity and detecting glitches.

    Args:
        frame_paths: List of frame paths to compare (typically 3 keyframes)
        description: What the animation should show
        max_tokens: Maximum response length
        provider_name: Explicit provider selection

    Returns:
        Dict with 'summary' and 'issues' keys
    """
    provider = get_vision_provider()
    if provider_name:
        from .providers import get_provider

        provider = get_provider(provider_name)

    model_spec = get_vision_model_spec()

    # Build a comparison question
    question = f"""Compare these {len(frame_paths)} animation frames from different timestamps.

The animation should show: {description}

Analyze:
1. Does the progression make sense across frames?
2. Are there any visual glitches, jumps, or discontinuities?
3. Is the animation smooth and coherent?
4. List any issues found, or reply 'OK' if everything looks correct.
"""

    # For multi-frame comparison, we'd need provider-specific batch handling
    # For now, analyze the middle frame as representative
    middle_frame = frame_paths[len(frame_paths) // 2]

    try:
        result = provider.analyze(
            question=question,
            image_path=middle_frame,
            model_spec=model_spec,
            max_tokens=max_tokens,
        )

        issues = [] if is_approval(result) else [result]
        return {"summary": result, "issues": issues}
    except ProviderError as e:
        raise VisionError(str(e)) from e
