"""LLM client for the MAGI System."""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from rich.console import Console

from magi.models import EmotionState, Message, MessageRole, PersonaResponse, Sentiment

_console = Console(stderr=True)

BASE_URL = "http://localhost:1234/v1"
API_KEY = "lm-studio"
MODEL = "qwen/qwen3-30b-a3b-2507"

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds


def _extract_json_block(text: str) -> Optional[str]:
    """Extract a JSON object from a text that might contain markdown code fences."""
    # Try to find ```json ... ``` block
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Try to find a bare JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return None


def _build_fallback_response(persona_name: str, raw_text: str) -> PersonaResponse:
    """Build a fallback PersonaResponse when JSON parsing fails."""
    _console.print(
        f"[yellow]Warning: Could not parse JSON from {persona_name}'s response. Using fallback.[/yellow]"
    )
    # Strip JSON-looking blocks (including nested ones) iteratively
    opinion = raw_text.strip()
    prev = None
    while prev != opinion:
        prev = opinion
        opinion = re.sub(r'\{[^{}]*\}', '', opinion, flags=re.DOTALL).strip()
    # Also strip markdown code fences
    opinion = re.sub(r'```(?:json)?\s*', '', opinion).strip()
    # Collapse excess blank lines
    opinion = re.sub(r'\n{3,}', '\n\n', opinion).strip()
    if not opinion:
        opinion = raw_text.strip()[:500]

    return PersonaResponse(
        opinion=opinion or f"（{persona_name}からの応答の解析に失敗しました）",
        emotions={},
        convergence_vote=False,
        convergence_reason="応答の解析に失敗したため、収束判断を保留します。",
    )


def _parse_persona_response(
    persona_name: str,
    raw_text: str,
    other_personas: list[str],
) -> PersonaResponse:
    """Parse a PersonaResponse from LLM output with robust error handling."""
    json_str = _extract_json_block(raw_text)

    if json_str is None:
        return _build_fallback_response(persona_name, raw_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        _console.print(f"[yellow]JSON decode error for {persona_name}: {e}[/yellow]")
        # Attempt to clean up common issues
        # Remove trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return _build_fallback_response(persona_name, raw_text)

    # Validate and normalise required fields
    opinion = data.get("opinion", "")
    if not isinstance(opinion, str) or not opinion.strip():
        opinion = raw_text.strip()[:500]

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
                    temperature=0.8,
                    presence_penalty=0.8,
                    frequency_penalty=0.8,
                    max_tokens=1024,
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
