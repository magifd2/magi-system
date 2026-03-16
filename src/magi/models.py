"""Pydantic models for the MAGI System."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class EmotionState(BaseModel):
    """Represents an emotion toward another persona."""

    sentiment: Sentiment = Sentiment.NEUTRAL
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: str = Field(default="", description="Detailed notes about the emotion")

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: str) -> str:
        """Normalize sentiment string to valid enum value."""
        if isinstance(v, str):
            v_lower = v.lower().strip()
            valid = {s.value for s in Sentiment}
            if v_lower in valid:
                return v_lower
            # Attempt fuzzy mapping
            if any(pos in v_lower for pos in ["posit", "good", "like", "trust", "agree"]):
                return Sentiment.POSITIVE
            if any(neg in v_lower for neg in ["neg", "bad", "dislike", "distrust", "disagree"]):
                return Sentiment.NEGATIVE
            return Sentiment.NEUTRAL
        return v

    @field_validator("intensity", mode="before")
    @classmethod
    def clamp_intensity(cls, v: float) -> float:
        """Clamp intensity to [0.0, 1.0]."""
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, v))


class PersonaResponse(BaseModel):
    """Structured response from an LLM persona."""

    opinion: str = Field(..., description="The persona's opinion on the topic (in Japanese)")
    emotions: dict[str, EmotionState] = Field(
        default_factory=dict,
        description="Updated emotions toward each other persona",
    )
    convergence_vote: bool = Field(
        default=False,
        description="Whether this persona believes the discussion has converged",
    )
    convergence_reason: str = Field(
        default="",
        description="Reason for the convergence judgment",
    )


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A single message in the discussion."""

    role: MessageRole
    content: str
    speaker: Optional[str] = Field(default=None, description="Name of the persona speaking (if assistant)")
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_openai_dict(self) -> dict:
        """Convert to OpenAI API message format."""
        return {"role": self.role.value, "content": self.content}


class PersonaState(BaseModel):
    """Snapshot of a persona's current state."""

    name: str
    current_stance: Optional[str] = None
    emotions: dict[str, EmotionState] = Field(default_factory=dict)
    convergence_vote: Optional[bool] = None
    convergence_reason: str = ""


class DiscussionState(BaseModel):
    """The overall state of the discussion."""

    topic: str
    messages: list[Message] = Field(default_factory=list)
    persona_states: dict[str, PersonaState] = Field(default_factory=dict)
    turn_count: int = 0
    is_converged: bool = False
    final_report: Optional[str] = None

    def get_convergence_votes(self) -> dict[str, bool]:
        """Return each persona's current convergence vote."""
        return {
            name: state.convergence_vote
            for name, state in self.persona_states.items()
            if state.convergence_vote is not None
        }

    def count_convergence_votes(self) -> int:
        """Count how many personas voted convergence=True."""
        votes = self.get_convergence_votes()
        return sum(1 for v in votes.values() if v is True)
