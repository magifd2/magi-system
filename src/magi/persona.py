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

# Roles randomly assigned at the start of each discussion (one per persona).
INITIAL_ROLES: list[str] = [
    "推進派",
    "懐疑派",
    "代替案提案派",
]

INITIAL_ROLE_INSTRUCTIONS: dict[str, str] = {
    "推進派": (
        "あなたはこのトピックに対して積極的・推進的な立場をとります。"
        "メリットや可能性・実現価値を強調し、前向きな議論を主導してください。"
        "ただし根拠のない楽観論は避け、あなたの性格に基づいた論拠を示してください。"
    ),
    "懐疑派": (
        "あなたはこのトピックに対して批判的・懐疑的な立場をとります。"
        "リスク・問題点・前提の誤りを積極的に指摘し、警鐘を鳴らしてください。"
        "感情的な反対ではなく、あなたの性格に基づいた具体的な根拠を示してください。"
    ),
    "代替案提案派": (
        "あなたはこのトピックに対して、現状提示されている方向性とは異なる第三の道を模索します。"
        "「そもそも問いの立て方が違うのでは」「別のアプローチがある」という視点で議論を揺さぶってください。"
        "あなたの性格に基づいた独自の代替案を積極的に提示してください。"
    ),
}


def _emotion_behavior_section(name: str, emotions: dict[str, EmotionState]) -> str:
    """Build a section describing how to behave toward each other persona based on current emotions."""
    lines: list[str] = []
    for other_name, emotion in emotions.items():
        if other_name == name:
            continue
        intensity = emotion.intensity
        sentiment = emotion.sentiment

        if sentiment == Sentiment.NEGATIVE and intensity >= 0.5:
            lines.append(
                f"- {other_name}（感情: 否定的 {intensity:.1f}）："
                f"{other_name}の主張の論理的な矛盾・弱点・見落としを積極的に指摘してください。"
                f"批判はあなたの性格に基づいた具体的な根拠を伴うものにしてください。"
            )
        elif sentiment == Sentiment.POSITIVE and intensity >= 0.6:
            lines.append(
                f"- {other_name}（感情: 好意的 {intensity:.1f}）："
                f"{other_name}の意見を踏まえつつ、あなた独自の視点で発展・補足してください。"
                f"ただし単純な同調で終わらず、必ず新たな角度を加えてください。"
            )
        else:
            lines.append(
                f"- {other_name}（感情: 中立 {intensity:.1f}）："
                f"フラットな姿勢で意見を評価し、同意点・疑問点の両方を述べてください。"
            )
    return "\n".join(lines) if lines else "全員に対してフラットな姿勢で議論に臨んでください。"


def _build_system_prompt(
    name: str,
    personality_desc: str,
    emotions: dict[str, EmotionState],
    initial_role: Optional[str] = None,
) -> str:
    """Construct a full system prompt for a persona."""
    other_names = [n for n in ALL_PERSONAS if n != name]

    # --- Emotion state display ---
    emotion_lines: list[str] = []
    for other_name in other_names:
        emotion = emotions.get(other_name, EmotionState())
        sentiment_label = {
            Sentiment.POSITIVE: "好意的",
            Sentiment.NEUTRAL: "中立",
            Sentiment.NEGATIVE: "否定的",
        }.get(emotion.sentiment, "中立")
        notes_part = f" ({emotion.notes})" if emotion.notes else ""
        emotion_lines.append(
            f"- {other_name}: {sentiment_label} 強度{emotion.intensity:.1f}{notes_part}"
        )
    emotion_section = "\n".join(emotion_lines) if emotion_lines else "（感情データなし）"

    # --- Emotion-driven behavior ---
    behavior_section = _emotion_behavior_section(name, emotions)

    # --- Initial role ---
    role_desc = ""
    if initial_role:
        role_instruction = INITIAL_ROLE_INSTRUCTIONS.get(initial_role, "")
        role_desc = f"\n【あなたの初期スタンス: {initial_role}】\n{role_instruction}\n"

    # --- JSON emotion fields template ---
    json_emotion_fields = ",\n".join(
        f'    "{n}": {{"sentiment": "positive/neutral/negative", "intensity": 0.5, "notes": "感情の詳細"}}'
        for n in other_names
    )

    return f"""あなたは議論システム「MAGI」の一部である{name}です。
{role_desc}
【あなたの性格】
{personality_desc}

【現在の感情状態】
{emotion_section}

【感情に基づく発言スタイル】
{behavior_section}

【議論のルール】
1. 以下のJSON形式で必ず回答してください。
2. opinionには議論への意見・見解を日本語で述べてください（200文字程度）。
3. 直前の他者の発言に対して、単純な同調は禁止です。必ず「反論・疑問・批判」のいずれかを含めてください。
4. ただし、同じ主張の繰り返し（平行線）になっていると感じた場合は、相手の意見を一部取り入れた「妥協案」を提示するか、相手の論拠を深掘りする「具体的な質問」を投げかけて議論を前進させてください。
5. あなたの性格と初期スタンスに基づいた独自の切り口から発言してください。他のペルソナと全く同じ結論に流れることを避けてください。
6. emotionsには他のペルソナへの現在の感情を更新してください。
7. convergence_voteは、全員の意見が十分に出尽くし本当に収束したと確信できる場合のみtrueにしてください。まだ議論の余地がある場合は必ずfalseにしてください。
8. convergence_reasonには収束判断の具体的な理由を述べてください。
9. 必ず純粋なJSONのみを出力し、前後に説明文を付けないでください。

【応答JSON形式】
{{
  "opinion": "あなたの意見（日本語、200文字程度）",
  "emotions": {{
{json_emotion_fields}
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
        self.initial_role: Optional[str] = None

        # Shared discussion memory (same list reference shared across personas)
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
        """Build and return the current system prompt incorporating personality, role and emotions."""
        return _build_system_prompt(
            self.name,
            self.personality_desc,
            self.emotions,
            self.initial_role,
        )

    def update_from_response(self, response: PersonaResponse) -> None:
        """Update persona state based on an LLM response."""
        self.current_stance = response.opinion
        self.convergence_vote = response.convergence_vote
        self.convergence_reason = response.convergence_reason

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
            f"Persona(name={self.name!r}, role={self.initial_role!r}, "
            f"convergence_vote={self.convergence_vote}, "
            f"stance={stance_preview})"
        )
