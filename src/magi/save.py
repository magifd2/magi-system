"""Save discussion log and final report to a Markdown file."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from magi.models import DiscussionState, MessageRole
from magi.persona import ALL_PERSONAS


def _safe_filename(topic: str) -> str:
    """Convert a topic string to a safe filename fragment (max 40 chars)."""
    cleaned = re.sub(r"[^\w\u3040-\u9FFF\u30A0-\u30FF]", "_", topic)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:40]


def build_markdown(state: DiscussionState, saved_at: datetime) -> str:
    """Render a DiscussionState as a Markdown document."""
    lines: list[str] = []

    # --- Header ---
    lines += [
        "# MAGI System 議論ログ",
        "",
        f"**トピック**: {state.topic}  ",
        f"**保存日時**: {saved_at.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**総ターン数**: {state.turn_count}  ",
        f"**収束**: {'はい' if state.is_converged else 'いいえ'}  ",
        "",
        "---",
        "",
    ]

    # --- Conversation log ---
    lines += ["## 議論ログ", ""]
    if state.messages:
        persona_turn = 0
        for msg in state.messages:
            ts = msg.timestamp.strftime("%H:%M:%S")
            if msg.role == MessageRole.ASSISTANT and msg.speaker:
                # Persona statement: sequential turn number
                persona_turn += 1
                lines += [
                    f"### ターン {persona_turn} — {msg.speaker}  `{ts}`",
                    "",
                    msg.content,
                    "",
                ]
            elif msg.speaker:
                # Facilitator or system injection: divider style
                lines += [
                    f"---",
                    f"**{msg.speaker}** `{ts}`",
                    "",
                    msg.content,
                    "",
                ]
    else:
        lines += ["（発言なし）", ""]

    lines += ["---", ""]

    # --- Persona final states ---
    lines += ["## 各ペルソナの最終状態", ""]
    for name in ALL_PERSONAS:
        ps = state.persona_states.get(name)
        if ps is None:
            continue
        lines += [f"### {name}", ""]
        if ps.current_stance:
            lines += [f"**最終立場**  ", ps.current_stance, ""]
        vote_label = "はい" if ps.convergence_vote else ("いいえ" if ps.convergence_vote is False else "未決")
        lines += [f"**収束判断**: {vote_label}  "]
        if ps.convergence_reason:
            lines += [f"**収束理由**: {ps.convergence_reason}  "]
        lines += ["", "**他ペルソナへの感情**  ", ""]
        other_names = [n for n in ALL_PERSONAS if n != name]
        for other in other_names:
            emotion = ps.emotions.get(other)
            if emotion:
                sent_val = emotion.sentiment.value if hasattr(emotion.sentiment, "value") else str(emotion.sentiment)
                symbol = {"positive": "▲ 好意的", "neutral": "● 中立", "negative": "▼ 否定的"}.get(sent_val, "● 中立")
                note_part = f" — {emotion.notes}" if emotion.notes else ""
                lines += [f"- **{other}**: {symbol} (強度 {emotion.intensity:.1f}){note_part}"]
        lines += [""]

    lines += ["---", ""]

    # --- Final report ---
    lines += ["## 最終レポート", ""]
    if state.final_report:
        lines += [state.final_report, ""]
    else:
        lines += ["（レポートなし）", ""]

    return "\n".join(lines)


def save_discussion(state: DiscussionState, output_dir: Path | None = None) -> Path:
    """
    Save the discussion log and final report to a Markdown file.

    Args:
        state: The final DiscussionState to save.
        output_dir: Directory to save into. Defaults to current working directory.

    Returns:
        The Path of the saved file.
    """
    if output_dir is None:
        output_dir = Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    topic_slug = _safe_filename(state.topic)
    filename = f"magi_{timestamp}_{topic_slug}.md"
    filepath = output_dir / filename

    content = build_markdown(state, saved_at=now)
    filepath.write_text(content, encoding="utf-8")

    return filepath
