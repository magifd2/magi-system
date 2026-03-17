"""LLM client for the MAGI System."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from rich.console import Console

from magi.models import EmotionState, Message, MessageRole, PersonaResponse, Sentiment

_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Debug logger — activated by setting MAGI_DEBUG=1 in the environment.
# Writes raw LLM I/O to magi_debug.log in the current working directory.
# ---------------------------------------------------------------------------
_debug = os.environ.get("MAGI_DEBUG", "0") == "1"

_log = logging.getLogger("magi.llm")
if _debug:
    _handler = logging.FileHandler("magi_debug.log", encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.DEBUG)


def _dbg(label: str, text: str) -> None:
    """Write a labelled block to the debug log (no-op when MAGI_DEBUG != 1)."""
    if _debug:
        _log.debug("\n%s\n%s\n%s", f"=== {label} ===", text, "=" * 60)

BASE_URL = "http://localhost:1234/v1"
API_KEY = "lm-studio"
MODEL = "qwen/qwen3-30b-a3b-2507"

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds

PERSONA_TEMPERATURES: dict[str, float] = {
    "MELCHIOR": 0.2,   # 論理・分析重視 → 低温で確定的な推論
    "BALTHASAR": 0.7,  # 感情・共感重視 → 高温で多様な表現
    "CASPER": 0.4,     # 実利・現実重視 → 中温でバランス
}


def _strip_thinking_blocks(text: str) -> str:
    """Remove <think>/<thinking>/<reasoning> blocks emitted by some models."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def _find_json_with_opinion(text: str) -> Optional[str]:
    """
    Find the outermost JSON object that contains an "opinion" key.
    Uses depth-tracking brace matching to handle nested objects correctly.
    """
    for start in (m.start() for m in re.finditer(r"\{", text)):
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    if '"opinion"' in candidate:
                        return candidate
                    break
    return None


def _extract_json_block(text: str) -> Optional[str]:
    """Extract a JSON object from a text that might contain markdown code fences."""
    # Try to find ```json ... ``` block (greedy .* to capture the full object)
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
        if '"opinion"' in candidate:
            return candidate

    # Find the outermost JSON object containing "opinion" via brace tracking
    return _find_json_with_opinion(text)


def _build_fallback_response(persona_name: str, raw_text: str) -> PersonaResponse:
    """Build a fallback PersonaResponse when JSON parsing fails."""
    _console.print(
        f"[yellow]Warning: Could not parse JSON from {persona_name}'s response. Using fallback.[/yellow]"
    )
    text = _strip_thinking_blocks(raw_text)
    # Always try regex extraction of "opinion" value first (most reliable for pure-JSON responses)
    m = re.search(r'"opinion"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if m:
        opinion = m.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
    else:
        # Fall back to cleaning the whole text
        opinion = _clean_opinion(text)
    if not opinion:
        opinion = raw_text.strip()[:500]

    return PersonaResponse(
        opinion=opinion or f"（{persona_name}からの応答の解析に失敗しました）",
        emotions={},
        convergence_vote=False,
        convergence_reason="応答の解析に失敗したため、収束判断を保留します。",
    )


def _clean_opinion(text: str) -> str:
    """
    Strip non-opinion noise from an extracted opinion string.

    Handles:
    - <think>...</think> blocks (Gemini / QwQ thinking mode)
    - Nested JSON objects / arrays
    - Markdown code fences
    - Excess blank lines
    """
    # Remove thinking blocks
    text = _strip_thinking_blocks(text)
    # Remove JSON objects iteratively (handles nesting)
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\{[^{}]*\}", "", text, flags=re.DOTALL)
    # Remove JSON arrays iteratively
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\[[^\[\]]*\]", "", text, flags=re.DOTALL)
    # Remove markdown code fences
    text = re.sub(r"```[a-z]*\s*", "", text)
    # Collapse excess whitespace / blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_persona_response(
    persona_name: str,
    raw_text: str,
    other_personas: list[str],
) -> PersonaResponse:
    """Parse a PersonaResponse from LLM output with robust error handling."""
    _dbg(f"RAW [{persona_name}]", raw_text)

    # Strip thinking/reasoning blocks first — they can contain { } that confuse
    # the greedy JSON regex in _extract_json_block.
    clean_raw = _strip_thinking_blocks(raw_text)
    _dbg(f"CLEAN_RAW [{persona_name}]", clean_raw)

    json_str = _extract_json_block(clean_raw) or _extract_json_block(raw_text)
    _dbg(f"JSON_STR [{persona_name}]", json_str or "(none)")

    if json_str is None:
        _dbg(f"FALLBACK [{persona_name}]", "json_str is None")
        return _build_fallback_response(persona_name, raw_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        _console.print(f"[yellow]JSON decode error for {persona_name}: {e}[/yellow]")
        _dbg(f"JSON_DECODE_ERROR [{persona_name}]", str(e))
        # Attempt to clean up common issues
        # Remove trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            _dbg(f"FALLBACK [{persona_name}]", "json decode failed after cleanup")
            return _build_fallback_response(persona_name, raw_text)

    opinion_raw = data.get("opinion", "")
    _dbg(f"OPINION_RAW [{persona_name}]", repr(opinion_raw))

    # Validate and normalise required fields
    opinion = opinion_raw
    if not isinstance(opinion, str) or not opinion.strip():
        # JSON parsed but opinion is missing/empty — try regex extraction on raw
        m = re.search(r'"opinion"\s*:\s*"((?:[^"\\]|\\.)*)"', clean_raw, re.DOTALL)
        opinion = m.group(1).replace('\\"', '"').replace("\\n", "\n").strip() if m else ""
        _dbg(f"OPINION_REGEX_RESCUE [{persona_name}]", repr(opinion))
    if not opinion:
        _dbg(f"FALLBACK [{persona_name}]", "opinion empty after all attempts")
        return _build_fallback_response(persona_name, raw_text)

    # Strip JSON noise, thinking tags, code fences etc. that some models inject
    opinion_cleaned = _clean_opinion(opinion)
    _dbg(f"OPINION_CLEANED [{persona_name}]", repr(opinion_cleaned))
    if not opinion_cleaned:
        # opinion field itself was JSON — re-extract from raw
        m = re.search(r'"opinion"\s*:\s*"((?:[^"\\]|\\.)*)"', clean_raw, re.DOTALL)
        opinion_cleaned = m.group(1).replace('\\"', '"').replace("\\n", "\n").strip() if m else ""
        _dbg(f"OPINION_CLEANED_RESCUE [{persona_name}]", repr(opinion_cleaned))
    opinion = opinion_cleaned
    if not opinion:
        _dbg(f"FALLBACK [{persona_name}]", "opinion empty after clean")
        return _build_fallback_response(persona_name, raw_text)

    # Post-process: remove self-referencing address patterns (セルフエコー対策)
    # e.g. "MELCHIOR、あなたの…" or "MELCHIOR、私は…" where persona_name == "MELCHIOR"
    opinion = re.sub(
        rf"(?<!\w){re.escape(persona_name)}[、,，]\s*",
        "",
        opinion,
    ).strip()

    # Parse emotions
    raw_emotions: dict = data.get("emotions", {})
    emotions: dict[str, EmotionState] = {}
    for name in other_personas:
        if name == persona_name:
            continue
        raw_e = raw_emotions.get(name, {})
        if isinstance(raw_e, dict):
            try:
                emotions[name] = EmotionState(
                    sentiment=raw_e.get("sentiment", "neutral"),
                    intensity=raw_e.get("intensity", 0.5),
                    notes=raw_e.get("notes", ""),
                )
            except Exception:
                emotions[name] = EmotionState()
        else:
            emotions[name] = EmotionState()

    convergence_vote = bool(data.get("convergence_vote", False))
    convergence_reason = str(data.get("convergence_reason", ""))

    return PersonaResponse(
        opinion=opinion,
        emotions=emotions,
        convergence_vote=convergence_vote,
        convergence_reason=convergence_reason,
    )


class LLMClient:
    """Client for interacting with an OpenAI-compatible LLM endpoint."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        api_key: str = API_KEY,
        model: str = MODEL,
    ) -> None:
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def chat_with_persona(
        self,
        persona_name: str,
        system_prompt: str,
        messages: list[Message],
        topic: str,
        other_personas: list[str],
        extra_instruction: str = "",
        turn: int = 0,
        max_turns: int = 50,
    ) -> PersonaResponse:
        """
        Call the LLM as a specific persona and parse the structured response.

        Args:
            persona_name: The name of the persona (e.g. "MELCHIOR").
            system_prompt: The persona's system prompt.
            messages: The shared discussion history.
            topic: The discussion topic (used if messages is empty).
            other_personas: Names of all personas (including self, for emotion parsing).

        Returns:
            A parsed PersonaResponse.
        """
        # Build the message list for the API call
        api_messages: list[dict] = [{"role": "system", "content": system_prompt}]

        # Inject urgency when discussion is running long (beyond 60% of max turns)
        urgency = ""
        if turn > max_turns * 0.6:
            urgency = (
                "\n【警告】議論が長期化しています。"
                "自分の主張に固執せず、他者の意見との統合や落としどころの模索を始めてください。"
            )

        if messages:
            context_lines: list[str] = [f"【議論トピック】{topic}\n\n【これまでの議論】"]

            # Truncation: keep the first message (facilitator's opening) + last N turns.
            # The persona's own prior stance is already in the system prompt (long-term memory),
            # so the history only needs to convey recent flow and atmosphere.
            RECENT_TURNS_TO_KEEP = 16
            if len(messages) > RECENT_TURNS_TO_KEEP + 1:
                filtered = [messages[0]] + list(messages[-RECENT_TURNS_TO_KEEP:])
                context_lines.append("（...中盤の議論履歴は省略...）")
            else:
                filtered = list(messages)

            for msg in filtered:
                if msg.role == MessageRole.ASSISTANT and msg.speaker:
                    context_lines.append(f"{msg.speaker}: {msg.content}")
                elif msg.role == MessageRole.USER:
                    context_lines.append(f"（進行）{msg.content}")
            instruction = extra_instruction or "上記の議論を受けて、あなたの見解をJSON形式で回答してください。"
            context_lines.append(f"\n{instruction}{urgency}")
            user_content = "\n".join(context_lines)
        else:
            instruction = extra_instruction or "このトピックについて、あなたの最初の見解をJSON形式で回答してください。"
            user_content = f"【議論トピック】{topic}\n\n{instruction}{urgency}"

        api_messages.append({"role": "user", "content": user_content})

        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,  # type: ignore[arg-type]
                    temperature=PERSONA_TEMPERATURES.get(persona_name, 0.5),
                    presence_penalty=0.8,
                    frequency_penalty=0.8,
                    max_tokens=4096,
                )
                raw_text = response.choices[0].message.content or ""
                return _parse_persona_response(persona_name, raw_text, other_personas)

            except (APIConnectionError, APIError, RateLimitError) as e:
                last_error = e
                _console.print(
                    f"[red]API error on attempt {attempt}/{MAX_RETRIES} for {persona_name}: {e}[/red]"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        # All retries exhausted
        _console.print(
            f"[red]All retries failed for {persona_name}. Using fallback response.[/red]"
        )
        return PersonaResponse(
            opinion=f"（APIエラーにより{persona_name}からの応答を取得できませんでした: {last_error}）",
            emotions={},
            convergence_vote=False,
            convergence_reason="APIエラーのため収束判断を保留します。",
        )

    def check_topic_coverage(
        self,
        topic: str,
        messages: list[Message],
    ) -> tuple[bool, list[str]]:
        """
        Evaluate whether the recent discussion has adequately covered the original topic.

        Returns:
            (adequate, missing_points)
            adequate: True if no significant gaps remain.
            missing_points: List of uncovered points (empty when adequate=True).
            On any error, returns (True, []) to avoid blocking convergence.
        """
        persona_msgs = [
            m for m in messages
            if m.role == MessageRole.ASSISTANT and m.speaker
        ]
        recent_text = "\n".join(
            f"{m.speaker}: {m.content}" for m in persona_msgs[-10:]
        )

        if not recent_text:
            return True, []

        system_prompt = (
            "あなたは議論の品質評価者です。"
            "元の議題と直近の議論内容を照合し、JSON形式のみで回答してください。"
        )
        user_prompt = (
            f"【元の議題】\n{topic}\n\n"
            f"【直近の議論】\n{recent_text}\n\n"
            "手順：\n"
            "1. まず元の議題を読み、議論されるべき主要論点を"
            "テクニカル・プロセス・組織・リスクの区別なく列挙する\n"
            "2. 各論点について、直近の議論で「具体的な根拠と立場が示されたか」を判定する\n"
            "   （単に言及されただけでは「議論された」とみなさない）\n"
            "3. 特に「導入・採用・実施の是非（すべき／すべきでない）」という賛否判断が"
            "   明示されているかを必ず確認する。「こう実装すれば動く」という実装論だけでは"
            "   是非の判断とはみなさない。\n"
            "4. 未議論・不十分な論点をリストアップする\n\n"
            "JSON形式で回答してください（他のテキストは不要）：\n"
            '{"adequate": true または false, "missing_points": ["未カバーの論点1", "未カバーの論点2", ...]}\n'
            "adequate は missing_points が空の場合のみ true にしてください。"
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            raw = response.choices[0].message.content or ""
            json_str = _extract_json_block(raw)
            if json_str:
                data = json.loads(json_str)
                adequate = bool(data.get("adequate", False))
                missing = [str(p) for p in data.get("missing_points", [])]
                return adequate, missing
        except Exception:
            pass

        return True, []
