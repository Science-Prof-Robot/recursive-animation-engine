"""
Plan phase for the animation engine.

Asks users specific questions about their video, reasons over what the acts
should be, and produces a structured plan that the build phase will execute.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .providers import BaseProvider, ModelSpec

from .providers import (
    ProviderError,
    get_text_model_spec,
    get_text_provider,
    get_vision_model_spec,
    get_vision_provider,
)


class PlanError(RuntimeError):
    """Error in planning phase."""

    pass


@dataclass
class VideoConcept:
    """A high-level concept for the video."""

    title: str
    description: str
    target_duration_seconds: float
    target_audience: str | None = None
    mood_tone: str | None = None
    visual_style: str = "modern-minimal"
    audio_style: str = "voiceover-music"


@dataclass
class VideoAct:
    """One act/scene in the video plan."""

    act_number: int
    title: str
    description: str
    duration_seconds: float
    key_visual_elements: list[str] = field(default_factory=list)
    narration_text: str = ""
    transition_in: str = "fade"
    transition_out: str = "fade"
    requires_3d: bool = False
    requires_custom_animation: bool = False
    voiceover_script: str = ""
    reference_images: list[Path] = field(default_factory=list)

    def estimate_html_complexity(self) -> str:
        """Estimate complexity based on requirements."""
        if self.requires_3d:
            return "high"
        if self.requires_custom_animation:
            return "medium-high"
        if len(self.key_visual_elements) > 5:
            return "medium"
        return "low"


@dataclass
class VideoPlan:
    """Complete plan for a video production."""

    plan_id: str
    concept: VideoConcept
    acts: list[VideoAct]
    total_duration: float
    global_assets: dict[str, str] = field(default_factory=dict)
    audio_plan: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert plan to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "concept": {
                "title": self.concept.title,
                "description": self.concept.description,
                "target_duration_seconds": self.concept.target_duration_seconds,
                "target_audience": self.concept.target_audience,
                "mood_tone": self.concept.mood_tone,
                "visual_style": self.concept.visual_style,
                "audio_style": self.concept.audio_style,
            },
            "acts": [
                {
                    "act_number": act.act_number,
                    "title": act.title,
                    "description": act.description,
                    "duration_seconds": act.duration_seconds,
                    "key_visual_elements": act.key_visual_elements,
                    "narration_text": act.narration_text,
                    "transition_in": act.transition_in,
                    "transition_out": act.transition_out,
                    "requires_3d": act.requires_3d,
                    "requires_custom_animation": act.requires_custom_animation,
                    "voiceover_script": act.voiceover_script,
                    "complexity": act.estimate_html_complexity(),
                }
                for act in self.acts
            ],
            "total_duration": self.total_duration,
            "global_assets": self.global_assets,
            "audio_plan": self.audio_plan,
        }

    def save(self, path: Path) -> None:
        """Save plan to JSON file."""
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "VideoPlan":
        """Load plan from JSON file."""
        data = json.loads(path.read_text())
        concept = VideoConcept(**data["concept"])
        acts = [VideoAct(**act_data) for act_data in data["acts"]]
        return cls(
            plan_id=data["plan_id"],
            concept=concept,
            acts=acts,
            total_duration=data["total_duration"],
            global_assets=data.get("global_assets", {}),
            audio_plan=data.get("audio_plan", {}),
        )


# Planning questions to ask the user
PLANNING_QUESTIONS = [
    {
        "id": "purpose",
        "question": "What is the purpose of this video? (educational, promotional, storytelling, product demo, etc.)",
        "required": True,
        "reasoning_impact": "high",
    },
    {
        "id": "topic",
        "question": "What specific topic or content should the video cover?",
        "required": True,
        "reasoning_impact": "high",
    },
    {
        "id": "duration",
        "question": "What is your target duration? (short: 15-30s, medium: 1-2min, long: 3-5min)",
        "required": True,
        "reasoning_impact": "high",
    },
    {
        "id": "audience",
        "question": "Who is your target audience? (technical, general public, executives, developers, etc.)",
        "required": False,
        "reasoning_impact": "medium",
    },
    {
        "id": "style",
        "question": "What visual style do you prefer? (minimal/clean, vibrant/bold, professional/corporate, hand-drawn/organic, retro, futuristic)",
        "required": False,
        "reasoning_impact": "medium",
    },
    {
        "id": "assets",
        "question": "Do you have any existing assets? (brand colors, logos, reference images, screenshots, data)",
        "required": False,
        "reasoning_impact": "medium",
    },
    {
        "id": "voiceover",
        "question": "Do you want voiceover narration? (yes/no, and if yes, formal or casual tone?)",
        "required": False,
        "reasoning_impact": "high",
    },
    {
        "id": "music",
        "question": "Should there be background music? (yes/no, and if yes, what mood?)",
        "required": False,
        "reasoning_impact": "low",
    },
    {
        "id": "examples",
        "question": "Are there any example videos you want to reference for style or approach?",
        "required": False,
        "reasoning_impact": "medium",
    },
]


def get_planning_questions() -> list[dict]:
    """Get the list of planning questions to ask users."""
    return PLANNING_QUESTIONS.copy()


def reason_over_acts(
    user_answers: dict[str, str],
    provider_name: str | None = None,
) -> VideoPlan:
    """
    Given user answers to planning questions, reason over what the acts should be.

    This uses the configured text provider to structure the video into logical
    acts/scenes with appropriate timing and transitions.

    Args:
        user_answers: Dict mapping question_id to user answer
        provider_name: Override provider ('openrouter', 'gemini', 'fireworks', 'native')

    Returns:
        A VideoPlan with structured acts
    """
    # Build the reasoning prompt
    prompt = _build_reasoning_prompt(user_answers)

    try:
        # For native provider, this is a marker - the agent should handle it
        if provider_name == "native" or (
            not provider_name
            and _is_native_provider()
        ):
            # Return a template that the agent fills using native context
            return _build_plan_from_native_reasoning(user_answers)

        # Use configured provider for reasoning
        provider = get_text_provider()
        if provider_name:
            from .providers import get_provider

            provider = get_provider(provider_name)

        model_spec = get_text_model_spec()

        response = provider.analyze(
            question=prompt,
            model_spec=model_spec,
            max_tokens=4096,
        )

        return _parse_plan_from_response(response, user_answers)

    except ProviderError as e:
        raise PlanError(f"Failed to reason over acts: {e}")


def _is_native_provider() -> bool:
    """Check if the configured text provider is native."""
    import os

    return os.environ.get("RENG_TEXT_PROVIDER", "native").lower() == "native"


def _build_reasoning_prompt(user_answers: dict[str, str]) -> str:
    """Build the prompt for act reasoning."""
    purpose = user_answers.get("purpose", "")
    topic = user_answers.get("topic", "")
    duration_str = user_answers.get("duration", "medium")
    audience = user_answers.get("audience", "general")
    style = user_answers.get("style", "modern-minimal")
    voiceover = user_answers.get("voiceover", "no")

    # Parse duration
    if duration_str.lower() in ("short", "15-30s"):
        target_duration = 30
    elif duration_str.lower() in ("medium", "1-2min", "1-2 min"):
        target_duration = 90
    elif duration_str.lower() in ("long", "3-5min", "3-5 min"):
        target_duration = 240
    else:
        target_duration = 90  # default

    prompt = f"""You are an expert video producer and motion designer. Structure the following video concept into a detailed plan.

## User Requirements
- Purpose: {purpose}
- Topic/Content: {topic}
- Target Duration: {duration_str} (~{target_duration} seconds)
- Target Audience: {audience}
- Visual Style: {style}
- Voiceover: {voiceover}

## Your Task
Create a structured video plan broken into logical acts/scenes. For each act, provide:
1. Act number and title
2. Detailed description of what happens visually
3. Duration in seconds
4. Key visual elements (animations, graphics, text overlays)
5. Narration/voiceover script (if voiceover is yes)
6. Transition recommendations
7. Any special requirements (3D, complex animation)

The acts should:
- Flow logically from one to the next
- Have appropriate durations that sum to approximately {target_duration} seconds
- Match the visual style requested
- Include a compelling intro (hook) and clear outro (CTI/call-to-action)
- Use transitions that fit the mood and pacing

## Output Format
Return ONLY a JSON object with this exact structure:
{{
  "concept": {{
    "title": "Video Title",
    "description": "Brief overall description",
    "target_duration_seconds": {target_duration},
    "target_audience": "{audience}",
    "mood_tone": "descriptive mood",
    "visual_style": "{style}",
    "audio_style": "voiceover-music or music-only"
  }},
  "acts": [
    {{
      "act_number": 1,
      "title": "Act Title",
      "description": "What happens in this act",
      "duration_seconds": 15,
      "key_visual_elements": ["element1", "element2"],
      "narration_text": "Voiceover script or empty if none",
      "transition_in": "fade|slide|wipe|none",
      "transition_out": "fade|slide|wipe|none",
      "requires_3d": false,
      "requires_custom_animation": false
    }}
  ],
  "total_duration": {target_duration},
  "audio_plan": {{
    "has_voiceover": {str(voiceover.lower().startswith("y")).lower()},
    "voiceover_tone": "formal|casual|energetic|calm",
    "music_mood": "upbeat|ambient|dramatic|minimal",
    "sound_effects": ["swoosh", "ding"]
  }}
}}
"""

    return prompt


def _build_plan_from_native_reasoning(user_answers: dict[str, str]) -> VideoPlan:
    """
    When using native provider, return a skeleton plan for the agent to fill.

    The agent running in native Claude Code context should use its own
    reasoning to populate this based on the user answers.
    """
    duration_str = user_answers.get("duration", "medium")
    if duration_str.lower() in ("short", "15-30s"):
        target_duration = 30
        num_acts = 3
    elif duration_str.lower() in ("long", "3-5min", "3-5 min"):
        target_duration = 240
        num_acts = 5
    else:
        target_duration = 90
        num_acts = 4

    topic = user_answers.get("topic", "Video")
    purpose = user_answers.get("purpose", "Presentation")

    # Create skeleton acts - agent should populate with actual content
    acts = []
    act_duration = target_duration / num_acts

    for i in range(num_acts):
        is_first = i == 0
        is_last = i == num_acts - 1

        if is_first:
            title = "Hook / Introduction"
            description = "Capture attention and introduce the topic"
        elif is_last:
            title = "Conclusion / Call to Action"
            description = "Summarize key points and provide next steps"
        else:
            title = f"Act {i + 1}: Key Content"
            description = f"Present important information about {topic}"

        act = VideoAct(
            act_number=i + 1,
            title=title,
            description=description,
            duration_seconds=act_duration,
            key_visual_elements=[],
            narration_text="",
            transition_in="fade" if i > 0 else "none",
            transition_out="fade" if not is_last else "fade-to-black",
        )
        acts.append(act)

    concept = VideoConcept(
        title=f"{purpose}: {topic}",
        description=user_answers.get("topic", ""),
        target_duration_seconds=target_duration,
        target_audience=user_answers.get("audience"),
        mood_tone=user_answers.get("style", "modern-minimal"),
        visual_style=user_answers.get("style", "modern-minimal"),
    )

    voiceover = user_answers.get("voiceover", "no").lower().startswith("y")

    return VideoPlan(
        plan_id=uuid.uuid4().hex[:12],
        concept=concept,
        acts=acts,
        total_duration=target_duration,
        audio_plan={
            "has_voiceover": voiceover,
            "voiceover_tone": "casual",
            "music_mood": "ambient",
            "sound_effects": [],
        },
    )


def _parse_plan_from_response(response: str, user_answers: dict[str, str]) -> VideoPlan:
    """Parse the model response into a VideoPlan."""
    try:
        # Try to extract JSON from response
        text = response.strip()

        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)

        concept_data = data.get("concept", {})
        concept = VideoConcept(
            title=concept_data.get("title", "Untitled"),
            description=concept_data.get("description", ""),
            target_duration_seconds=concept_data.get("target_duration_seconds", 90),
            target_audience=concept_data.get("target_audience"),
            mood_tone=concept_data.get("mood_tone"),
            visual_style=concept_data.get("visual_style", "modern-minimal"),
            audio_style=concept_data.get("audio_style", "voiceover-music"),
        )

        acts_data = data.get("acts", [])
        acts = []
        for act_data in acts_data:
            act = VideoAct(
                act_number=act_data.get("act_number", len(acts) + 1),
                title=act_data.get("title", f"Act {len(acts) + 1}"),
                description=act_data.get("description", ""),
                duration_seconds=act_data.get("duration_seconds", 15),
                key_visual_elements=act_data.get("key_visual_elements", []),
                narration_text=act_data.get("narration_text", ""),
                transition_in=act_data.get("transition_in", "fade"),
                transition_out=act_data.get("transition_out", "fade"),
                requires_3d=act_data.get("requires_3d", False),
                requires_custom_animation=act_data.get("requires_custom_animation", False),
                voiceover_script=act_data.get("voiceover_script", "")
                or act_data.get("narration_text", ""),
            )
            acts.append(act)

        return VideoPlan(
            plan_id=uuid.uuid4().hex[:12],
            concept=concept,
            acts=acts,
            total_duration=data.get("total_duration", sum(a.duration_seconds for a in acts)),
            audio_plan=data.get("audio_plan", {}),
        )

    except json.JSONDecodeError as e:
        raise PlanError(f"Failed to parse plan JSON: {e}")
    except (KeyError, TypeError) as e:
        raise PlanError(f"Invalid plan structure: {e}")


def refine_act_with_vision_references(
    act: VideoAct,
    reference_images: list[Path],
    feedback: str,
    provider_name: str | None = None,
) -> VideoAct:
    """
    Refine an act based on reference images and user feedback.

    Uses vision capabilities to analyze reference images and update
    the act description and visual elements accordingly.
    """
    # This is a placeholder for vision-based act refinement
    # In practice, the agent would use vision analysis on reference images
    # and update the act with specific visual requirements

    # For now, just add the reference images to the act
    act.reference_images.extend(reference_images)

    if feedback:
        act.description += f"\n\nUser feedback: {feedback}"

    return act
