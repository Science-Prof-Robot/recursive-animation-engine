"""Recursive Animation Engine."""

__version__ = "0.2.1"

# Core engine
from .lib.engine import run

# Planning
from .lib.plan import (
    VideoAct,
    VideoConcept,
    VideoPlan,
    get_planning_questions,
    reason_over_acts,
)

# Building
from .lib.build import (
    ActBuildResult,
    FinalBuildResult,
    build_act,
    build_all_acts,
    mix_audio_with_video,
)

# Providers
from .lib.providers import (
    DEFAULT_TEXT_MODEL,
    DEFAULT_VISION_MODEL,
    GEMINI_TTS_MODEL,
    GeminiProvider,
    GeminiTTSProvider,
    ModelSpec,
    OpenRouterProvider,
    FireworksProvider,
    get_provider,
    get_text_model_spec,
    get_text_provider,
    get_tts_provider,
    get_vision_model_spec,
    get_vision_provider,
)

# Vision
from .lib.vision import analyze, is_approval

__all__ = [
    # Version
    "__version__",
    # Core engine
    "run",
    # Planning
    "VideoAct",
    "VideoConcept",
    "VideoPlan",
    "get_planning_questions",
    "reason_over_acts",
    # Building
    "ActBuildResult",
    "FinalBuildResult",
    "build_act",
    "build_all_acts",
    "mix_audio_with_video",
    # Providers
    "ModelSpec",
    "DEFAULT_VISION_MODEL",
    "DEFAULT_TEXT_MODEL",
    "GEMINI_TTS_MODEL",
    "OpenRouterProvider",
    "GeminiProvider",
    "FireworksProvider",
    "GeminiTTSProvider",
    "get_provider",
    "get_vision_provider",
    "get_text_provider",
    "get_tts_provider",
    "get_vision_model_spec",
    "get_text_model_spec",
    # Vision
    "analyze",
    "is_approval",
]
