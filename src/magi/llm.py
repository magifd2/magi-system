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
MODEL = "openai/gpt-oss-20b"

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
    # Use the raw text as the opinion, stripping any JSON artifacts
    opinion = raw_text.strip()
    # Remove JSON-looking parts if any
    opinion = re.sub(r'\{.*\}', '', opinion, flags=re.DOTALL).strip()
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

        if messages:
            # Summarise the discussion context as a user prompt
            context_lines: list[str] = [f"【議論トピック】{topic}\n\n【これまでの議論】"]
            for msg in messages:
                if msg.role == MessageRole.ASSISTANT and msg.speaker:
                    context_lines.append(f"{msg.speaker}: {msg.content}")
                elif msg.role == MessageRole.USER:
                    context_lines.append(f"（進行）{msg.content}")
            instruction = extra_instruction or "上記の議論を受けて、あなたの見解をJSON形式で回答してください。"
            context_lines.append(f"\n{instruction}")
            user_content = "\n".join(context_lines)
        else:
            instruction = extra_instruction or "このトピックについて、あなたの最初の見解をJSON形式で回答してください。"
            user_content = f"【議論トピック】{topic}\n\n{instruction}"

        api_messages.append({"role": "user", "content": user_content})

        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,  # type: ignore[arg-type]
                    temperature=0.7,
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
