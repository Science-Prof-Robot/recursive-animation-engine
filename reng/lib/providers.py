"""
Multi-provider LLM and TTS support for the animation engine.

Supports:
- OpenRouter (unified API for many models)
- Google Gemini API (native)
- Fireworks AI (fast inference)
- Google Gemini TTS 3.1 Flash for voiceover generation

Vision defaults to Gemma (latest available version).
Text model defaults to native Claude Code context or Gemma as fallback.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    pass


class ProviderError(RuntimeError):
    """Base error for provider failures."""

    pass


# Backward compatibility alias
VisionError = ProviderError


class ModelType(Enum):
    """Types of model capabilities needed."""

    VISION = "vision"
    TEXT = "text"
    TTS = "tts"


@dataclass(frozen=True)
class ModelSpec:
    """Specification for a model."""

    provider: str
    model_id: str
    supports_vision: bool = False
    supports_tts: bool = False
    max_tokens: int = 4096
    default_timeout: float = 120.0


# Predefined model specifications
DEFAULT_VISION_MODEL = ModelSpec(
    provider="openrouter",
    model_id="google/gemma-3-27b-it",  # Latest Gemma with vision support
    supports_vision=True,
    max_tokens=4096,
    default_timeout=120.0,
)

DEFAULT_TEXT_MODEL = ModelSpec(
    provider="native",  # Uses Claude Code's native context
    model_id="claude-code-native",
    supports_vision=False,
    max_tokens=8192,
    default_timeout=60.0,
)

FALLBACK_TEXT_MODEL = ModelSpec(
    provider="openrouter",
    model_id="google/gemma-3-27b-it",  # Gemma as text fallback
    supports_vision=True,
    max_tokens=4096,
    default_timeout=120.0,
)

GEMINI_TTS_MODEL = ModelSpec(
    provider="gemini",
    model_id="gemini-3.1-flash-tts",  # Gemini TTS 3.1 Flash
    supports_tts=True,
    max_tokens=4096,
    default_timeout=60.0,
)

# Provider API endpoints
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
GEMINI_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
SUPPORTED_MIME_PREFIXES = (
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
)


def _encode_image(path: Path) -> tuple[str, str]:
    """Return (mime_type, base64_data). Raises ProviderError on failure."""
    if not path.exists():
        raise ProviderError(f"image not found: {path}")
    if not path.is_file():
        raise ProviderError(f"not a regular file: {path}")

    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ProviderError(f"image too large ({size} bytes, max {MAX_IMAGE_BYTES})")

    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not any(mime.startswith(p) for p in SUPPORTED_MIME_PREFIXES):
        raise ProviderError(
            f"unsupported image type: {mime or 'unknown'} (need PNG/JPG/GIF/WebP)"
        )

    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return mime, data


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = api_key
        self.timeout = timeout or 120.0

    @abstractmethod
    def analyze(
        self,
        question: str,
        image_path: Path | None = None,
        model_spec: ModelSpec | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a question (optionally with image) and return text response."""
        pass

    def _get_headers(self) -> dict[str, str]:
        """Get default headers for API requests."""
        return {
            "Content-Type": "application/json",
        }


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider - unified API for many models."""

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        super().__init__(
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", "").strip(),
            timeout=timeout,
        )
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY env var is not set")

    def _get_headers(self) -> dict[str, str]:
        return {
            **super()._get_headers(),
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/Science-Prof-Robot/recursive-animation-engine",
            "X-Title": "recursive-animation-engine",
        }

    def analyze(
        self,
        question: str,
        image_path: Path | None = None,
        model_spec: ModelSpec | None = None,
        max_tokens: int | None = None,
    ) -> str:
        model_spec = model_spec or DEFAULT_VISION_MODEL
        max_tokens = max_tokens or model_spec.max_tokens

        messages: list[dict] = []

        if image_path:
            mime, b64 = _encode_image(Path(image_path))
            data_url = f"data:{mime};base64,{b64}"
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            })
        else:
            messages.append({"role": "user", "content": question})

        payload = {
            "model": model_spec.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        try:
            resp = httpx.post(
                OPENROUTER_URL,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise ProviderError(f"network error: {e}")

        if resp.status_code >= 400:
            raise ProviderError(f"OpenRouter returned {resp.status_code}: {resp.text}")

        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"unexpected response shape: {e}")


class GeminiProvider(BaseProvider):
    """Native Google Gemini API provider."""

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        super().__init__(
            api_key=api_key or os.environ.get("GEMINI_API_KEY", "").strip(),
            timeout=timeout,
        )
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY env var is not set")

    def _get_headers(self) -> dict[str, str]:
        return {
            **super()._get_headers(),
            "x-goog-api-key": self.api_key,
        }

    def analyze(
        self,
        question: str,
        image_path: Path | None = None,
        model_spec: ModelSpec | None = None,
        max_tokens: int | None = None,
    ) -> str:
        model_spec = model_spec or DEFAULT_VISION_MODEL
        max_tokens = max_tokens or model_spec.max_tokens

        # Map OpenRouter model IDs to Gemini model IDs
        model_id = model_spec.model_id
        if model_id.startswith("google/"):
            model_id = model_id.replace("google/", "")
        if not model_id.startswith("gemini") and not model_id.startswith("gemma"):
            model_id = "gemini-2.0-flash"  # Default Gemini vision model

        contents: list[dict] = []

        if image_path:
            mime, b64 = _encode_image(Path(image_path))
            contents.append({
                "role": "user",
                "parts": [
                    {"text": question},
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": b64,
                        }
                    },
                ],
            })
        else:
            contents.append({"role": "user", "parts": [{"text": question}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.4,
            },
        }

        url = f"{GEMINI_API_URL}/{model_id}:generateContent?key={self.api_key}"

        try:
            resp = httpx.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise ProviderError(f"network error: {e}")

        if resp.status_code >= 400:
            raise ProviderError(f"Gemini API returned {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"unexpected response shape: {e}")


class FireworksProvider(BaseProvider):
    """Fireworks AI provider for fast inference."""

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        super().__init__(
            api_key=api_key or os.environ.get("FIREWORKS_API_KEY", "").strip(),
            timeout=timeout,
        )
        if not self.api_key:
            raise ProviderError("FIREWORKS_API_KEY env var is not set")

    def _get_headers(self) -> dict[str, str]:
        return {
            **super()._get_headers(),
            "Authorization": f"Bearer {self.api_key}",
        }

    def analyze(
        self,
        question: str,
        image_path: Path | None = None,
        model_spec: ModelSpec | None = None,
        max_tokens: int | None = None,
    ) -> str:
        model_spec = model_spec or DEFAULT_VISION_MODEL
        max_tokens = max_tokens or model_spec.max_tokens

        # Fireworks uses accounts/{account}/models/{model} format
        model_id = model_spec.model_id
        if "/" in model_id and not model_id.startswith("accounts/"):
            # Convert provider/model format to Fireworks format if needed
            pass  # Fireworks can handle some standard formats

        messages: list[dict] = []

        if image_path:
            mime, b64 = _encode_image(Path(image_path))
            data_url = f"data:{mime};base64,{b64}"
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            })
        else:
            messages.append({"role": "user", "content": question})

        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        try:
            resp = httpx.post(
                FIREWORKS_URL,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise ProviderError(f"network error: {e}")

        if resp.status_code >= 400:
            raise ProviderError(f"Fireworks returned {resp.status_code}: {resp.text}")

        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"unexpected response shape: {e}")


class GeminiTTSProvider:
    """Google Gemini TTS 3.1 Flash provider for voiceover generation."""

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self.timeout = timeout or 60.0
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY env var is not set for TTS")

    def generate_voiceover(
        self,
        text: str,
        voice_name: str = "en-US-Neural2-D",
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        output_path: Path | None = None,
    ) -> Path:
        """
        Generate voiceover audio from text using Gemini TTS 3.1 Flash.

        Args:
            text: The script/text to speak
            voice_name: Voice to use (e.g., "en-US-Neural2-D", "en-GB-Neural2-B")
            speaking_rate: Speed (0.25 to 4.0, default 1.0)
            pitch: Pitch adjustment (-20.0 to 20.0, default 0.0)
            output_path: Where to save the MP3 (auto-generated if None)

        Returns:
            Path to the generated audio file
        """
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": voice_name.split("-")[0] + "-" + voice_name.split("-")[1],
                "name": voice_name,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": speaking_rate,
                "pitch": pitch,
            },
        }

        url = f"{GEMINI_TTS_URL}?key={self.api_key}"

        try:
            resp = httpx.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise ProviderError(f"TTS network error: {e}")

        if resp.status_code >= 400:
            raise ProviderError(f"TTS API returned {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
            audio_content = base64.b64decode(data["audioContent"])
        except (KeyError, ValueError) as e:
            raise ProviderError(f"unexpected TTS response: {e}")

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)

        output_path = Path(output_path)
        output_path.write_bytes(audio_content)

        return output_path

    def generate_voiceover_ssml(
        self,
        ssml: str,
        voice_name: str = "en-US-Neural2-D",
        output_path: Path | None = None,
    ) -> Path:
        """
        Generate voiceover from SSML for fine-grained control.

        SSML supports:
        - <break time="1s"/>
        - <emphasis level="strong">words</emphasis>
        - <prosody rate="slow" pitch="-2st">words</prosody>
        - <speak><mark name="act1"/>Hello</speak>
        """
        payload = {
            "input": {"ssml": ssml},
            "voice": {
                "languageCode": voice_name.split("-")[0] + "-" + voice_name.split("-")[1],
                "name": voice_name,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
            },
        }

        url = f"{GEMINI_TTS_URL}?key={self.api_key}"

        try:
            resp = httpx.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise ProviderError(f"TTS network error: {e}")

        if resp.status_code >= 400:
            raise ProviderError(f"TTS API returned {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
            audio_content = base64.b64decode(data["audioContent"])
        except (KeyError, ValueError) as e:
            raise ProviderError(f"unexpected TTS response: {e}")

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)

        output_path = Path(output_path)
        output_path.write_bytes(audio_content)

        return output_path


class NativeClaudeProvider:
    """
    Marker class for native Claude Code context.

    This provider doesn't make API calls - it indicates the orchestrator
    should use the native Claude Code context for text generation.
    Vision calls still go through configured vision provider.
    """

    def __init__(self):
        self.model_id = "claude-code-native"

    def analyze(self, question: str, **kwargs) -> str:
        """
        This is a marker - actual text generation happens in the
        agent loop using native Claude Code context.
        """
        raise ProviderError(
            "NativeClaudeProvider is a marker - use agent's native text generation"
        )


def get_provider(provider_name: str | None = None) -> BaseProvider:
    """
    Factory function to get the appropriate provider.

    Args:
        provider_name: One of 'openrouter', 'gemini', 'fireworks', 'native', or None for auto

    Returns:
        Configured provider instance
    """
    provider = (provider_name or os.environ.get("RENG_LLM_PROVIDER", "openrouter")).lower()

    if provider == "openrouter":
        return OpenRouterProvider()
    elif provider == "gemini":
        return GeminiProvider()
    elif provider == "fireworks":
        return FireworksProvider()
    elif provider == "native":
        return NativeClaudeProvider()
    else:
        raise ProviderError(f"Unknown provider: {provider}")


def get_vision_provider() -> BaseProvider:
    """Get the configured vision provider (defaults to OpenRouter with Gemma)."""
    provider_name = os.environ.get("RENG_VISION_PROVIDER", "openrouter")
    return get_provider(provider_name)


def get_text_provider() -> BaseProvider | NativeClaudeProvider:
    """
    Get the configured text provider.

    Defaults to 'native' (use Claude Code's context) but can be overridden.
    """
    provider_name = os.environ.get("RENG_TEXT_PROVIDER", "native")
    return get_provider(provider_name)


def get_tts_provider() -> GeminiTTSProvider:
    """Get the TTS provider (Gemini TTS 3.1 Flash)."""
    return GeminiTTSProvider()


def get_model_spec(model_env_var: str, default_spec: ModelSpec) -> ModelSpec:
    """Get model spec from environment or default."""
    model_id = os.environ.get(model_env_var, "").strip()
    if model_id:
        provider = os.environ.get(f"{model_env_var}_PROVIDER", default_spec.provider)
        return ModelSpec(
            provider=provider,
            model_id=model_id,
            supports_vision=default_spec.supports_vision,
            supports_tts=default_spec.supports_tts,
            max_tokens=default_spec.max_tokens,
        )
    return default_spec


def get_vision_model_spec() -> ModelSpec:
    """Get the configured vision model (defaults to latest Gemma)."""
    return get_model_spec("RENG_VISION_MODEL", DEFAULT_VISION_MODEL)


def get_text_model_spec() -> ModelSpec:
    """Get the configured text model."""
    return get_model_spec("RENG_TEXT_MODEL", DEFAULT_TEXT_MODEL)
