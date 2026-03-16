"""Persona definitions and management for the MAGI System."""

from __future__ import annotations

from typing import Optional

from magi.models import EmotionState, Message, MessageRole, PersonaResponse, Sentiment


PERSONA_DESCRIPTIONS: dict[str, str] = {
    "MELCHIOR": (
        "冷静で論理的な思考者。データと合理性を最重視し、感情に流されず客観的な分析を行う。"
        "問題を構造化し、証拠に基づいた結論を導くことを好む。"
        "他者の意見を感情ではなく論理の質で評価する。"
    ),
    "BALTHASAR": (
        "人間的で感情を重視する思考者。倫理・共感・社会的影響を最重視する。"
        "数字や効率だけでなく、人々の気持ちや価値観、道徳的側面を常に考慮する。"
        "議論における人間的なつながりと相互理解を大切にする。"
    ),
    "CASPER": (
        "実利主義の現実主義者。リスク・コスト・実現可能性を最重視する。"
        "理想論よりも現実的な解決策を求め、具体的な行動計画と結果を重視する。"
        "潜在的な問題点や障壁を早期に特定し、実践的なアプローチを推進する。"
    ),
}

PERSONA_COLORS: dict[str, str] = {
    "MELCHIOR": "blue",
    "BALTHASAR": "yellow",
    "CASPER": "green",
}

ALL_PERSONAS = list(PERSONA_DESCRIPTIONS.keys())


def _build_system_prompt(
    name: str,
    personality_desc: str,
    emotions: dict[str, EmotionState],
) -> str:
    """Construct a full system prompt for a persona."""
    other_names = [n for n in ALL_PERSONAS if n != name]

    emotion_lines: list[str] = []
    for other_name in other_names:
        emotion = emotions.get(other_name, EmotionState())
        sentiment_label = {
            Sentiment.POSITIVE: "好意的",
            Sentiment.NEUTRAL: "中立",
            Sentiment.NEGATIVE: "否定的",
        }.get(emotion.sentiment, "中立")
        notes_part = f" - {emotion.notes}" if emotion.notes else ""
        emotion_lines.append(
            f"- {other_name} への感情: {sentiment_label} (強度: {emotion.intensity:.1f}){notes_part}"
        )

    emotion_section = "\n".join(emotion_lines) if emotion_lines else "（感情データなし）"

    # Build emotion fields for the JSON template
    json_emotion_fields: list[str] = []
    for other_name in other_names:
        json_emotion_fields.append(
            f'    "{other_name}": {{"sentiment": "positive/neutral/negative", "intensity": 0.5, "notes": "感情の詳細"}}'
        )
    json_emotions = ",\n".join(json_emotion_fields)

    return f"""あなたは議論システム「MAGI」の一部である{name}です。

【あなたの性格】
{personality_desc}

【現在の感情状態】
{emotion_section}

【議論のルール】
1. 以下のJSON形式で必ず回答してください
2. opinionには議論への意見・見解を日本語で述べてください（200文字程度）
3. emotionsには他のペルソナへの現在の感情を更新してください
4. convergence_voteには議論が収束したと思うかどうか（true/false）を示してください
5. convergence_reasonには収束判断の理由を述べてください
6. 必ず純粋なJSONのみを出力し、前後に説明文を付けないでください

【応答JSON形式】
{{
  "opinion": "あなたの意見（日本語、200文字程度）",
  "emotions": {{
{json_emotions}
  }},
  "convergence_vote": false,
  "convergence_reason": "収束判断の理由"
}}"""


class Persona:
    """Represents a single MAGI persona with memory, emotions, and state."""

    def __init__(self, name: str) -> None:
        if name not in PERSONA_DESCRIPTIONS:
            raise ValueError(f"Unknown persona: {name}. Must be one of {ALL_PERSONAS}")

        self.name = name
        self.personality_desc = PERSONA_DESCRIPTIONS[name]
        self.color = PERSONA_COLORS[name]

        # Shared discussion memory (list of Message objects — same reference shared across personas)
        self.memory: list[Message] = []

        # Emotions toward other personas (initialised neutral)
        self.emotions: dict[str, EmotionState] = {
            other: EmotionState(sentiment=Sentiment.NEUTRAL, intensity=0.3, notes="初期状態")
            for other in ALL_PERSONAS
            if other != name
        }

        self.current_stance: Optional[str] = None
        self.convergence_vote: Optional[bool] = None
        self.convergence_reason: str = ""

    @property
    def system_prompt(self) -> str:
        """Build and return the current system prompt incorporating personality and emotions."""
        return _build_system_prompt(self.name, self.personality_desc, self.emotions)

    def update_from_response(self, response: PersonaResponse) -> None:
        """Update persona state based on an LLM response."""
        self.current_stance = response.opinion
        self.convergence_vote = response.convergence_vote
        self.convergence_reason = response.convergence_reason

        # Update emotions for known other personas only
        for other_name, emotion_state in response.emotions.items():
            if other_name in self.emotions:
                self.emotions[other_name] = emotion_state

    def add_to_memory(self, message: Message) -> None:
        """Append a message to this persona's memory."""
        self.memory.append(message)

    def get_emotion_summary(self) -> str:
        """Return a short human-readable summary of current emotions."""
        parts: list[str] = []
        for other, emotion in self.emotions.items():
            symbol = {"positive": "+", "neutral": "=", "negative": "-"}.get(
                emotion.sentiment.value, "="
            )
            parts.append(f"{other}:{symbol}{emotion.intensity:.1f}")
        return "  ".join(parts)

    def __repr__(self) -> str:
        stance_preview = repr(self.current_stance[:40]) if self.current_stance else None
        return (
            f"Persona(name={self.name!r}, "
            f"convergence_vote={self.convergence_vote}, "
            f"stance={stance_preview})"
        )
