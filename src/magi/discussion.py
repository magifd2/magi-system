"""Discussion engine for the MAGI System."""

from __future__ import annotations

import random
from datetime import datetime
from typing import Callable, Optional

from magi.llm import LLMClient
from magi.models import DiscussionState, Message, MessageRole, PersonaState
from magi.persona import ALL_PERSONAS, INITIAL_ROLES, Persona


MAX_TURNS = 20
CONVERGENCE_THRESHOLD = 2  # How many personas must vote True to converge
MIN_TURNS_BEFORE_CONVERGENCE = 6  # Require at least 2 full rounds before convergence can trigger


def _persona_state_snapshot(persona: Persona) -> PersonaState:
    """Create a PersonaState snapshot from a Persona object."""
    return PersonaState(
        name=persona.name,
        initial_role=persona.initial_role,
        current_stance=persona.current_stance,
        emotions=dict(persona.emotions),
        convergence_vote=persona.convergence_vote,
        convergence_reason=persona.convergence_reason,
    )


class DiscussionEngine:
    """Orchestrates a multi-persona discussion using the MAGI personas."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        on_state_update: Optional[Callable[[DiscussionState], None]] = None,
    ) -> None:
        """
        Args:
            llm_client: LLM client to use. Creates a default one if not provided.
            on_state_update: Callback invoked after each turn with the updated DiscussionState.
        """
        self._llm = llm_client or LLMClient()
        self._on_state_update = on_state_update

        # Create the three personas
        self._personas: dict[str, Persona] = {name: Persona(name) for name in ALL_PERSONAS}

        # Shared message history (same list reference given to all personas)
        self._shared_memory: list[Message] = []
        for persona in self._personas.values():
            persona.memory = self._shared_memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, topic: str) -> DiscussionState:
        """
        Run the full discussion on the given topic.

        Returns the final DiscussionState including the report.
        """
        # Assign initial roles (推進派 / 懐疑派 / 代替案提案派) randomly
        self._assign_initial_roles()

        state = self._build_state(topic)
        self._notify(state)

        last_speaker: Optional[str] = None
        turn = 0

        while turn < MAX_TURNS:
            # Pick next speaker (avoid repeating same persona consecutively)
            speaker_name = self._pick_next_speaker(last_speaker)
            persona = self._personas[speaker_name]

            # --- LLM call ---
            response = self._llm.chat_with_persona(
                persona_name=speaker_name,
                system_prompt=persona.system_prompt,
                messages=self._shared_memory,
                topic=topic,
                other_personas=ALL_PERSONAS,
                turn=turn,
            )

            # Update persona state
            persona.update_from_response(response)

            # Add the opinion to shared memory
            msg = Message(
                role=MessageRole.ASSISTANT,
                content=response.opinion,
                speaker=speaker_name,
                timestamp=datetime.now(),
            )
            self._shared_memory.append(msg)

            turn += 1
            last_speaker = speaker_name

            # Refresh state snapshot and notify display
            state = self._build_state(topic)
            state.turn_count = turn
            self._notify(state)

            # Check convergence: 2+ personas voted True, after minimum turns
            convergence_count = self._count_convergence_votes()
            if convergence_count >= CONVERGENCE_THRESHOLD and turn >= MIN_TURNS_BEFORE_CONVERGENCE:
                state.is_converged = True
                break

        # --- Closing statements phase ---
        self._run_closing_phase(topic)
        state = self._build_state(topic)
        state.is_converged = True
        self._notify(state)

        # Generate final report
        report = self._generate_report(topic, state)
        state.final_report = report
        self._notify(state)

        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assign_initial_roles(self) -> None:
        """Randomly assign one of the three initial roles to each persona."""
        roles = list(INITIAL_ROLES)
        random.shuffle(roles)
        for persona, role in zip(self._personas.values(), roles):
            persona.initial_role = role

    def _run_closing_phase(self, topic: str) -> None:
        """
        After convergence, ask every persona for a closing statement in fixed order.
        A separator message is injected first so all personas see the phase transition.
        """
        separator = Message(
            role=MessageRole.USER,
            content="【議論収束】2名以上が意見の収束を確認しました。各ペルソナは締めくくりのコメントをお願いします。",
            speaker=None,
            timestamp=datetime.now(),
        )
        self._shared_memory.append(separator)

        closing_instruction = (
            "議論が収束しました。あなたの視点から、この議論全体を振り返り、"
            "最終的な見解と今後への言及を含む締めくくりのコメントをJSON形式で述べてください。"
        )

        for name in ALL_PERSONAS:
            persona = self._personas[name]
            response = self._llm.chat_with_persona(
                persona_name=name,
                system_prompt=persona.system_prompt,
                messages=self._shared_memory,
                topic=topic,
                other_personas=ALL_PERSONAS,
                extra_instruction=closing_instruction,
            )
            persona.update_from_response(response)

            msg = Message(
                role=MessageRole.ASSISTANT,
                content=f"【締めくくり】{response.opinion}",
                speaker=name,
                timestamp=datetime.now(),
            )
            self._shared_memory.append(msg)

            # Notify display after each closing statement
            state = self._build_state(topic)
            state.is_converged = True
            self._notify(state)

    def _pick_next_speaker(self, last_speaker: Optional[str]) -> str:
        """Pick the next speaker, avoiding repeating the same persona consecutively."""
        candidates = [n for n in ALL_PERSONAS if n != last_speaker]
        return random.choice(candidates)

    def _count_convergence_votes(self) -> int:
        """Count how many personas currently vote convergence=True."""
        return sum(
            1
            for p in self._personas.values()
            if p.convergence_vote is True
        )

    def _build_state(self, topic: str) -> DiscussionState:
        """Build a DiscussionState snapshot from current engine state."""
        persona_states = {
            name: _persona_state_snapshot(p)
            for name, p in self._personas.items()
        }
        return DiscussionState(
            topic=topic,
            messages=list(self._shared_memory),
            persona_states=persona_states,
            turn_count=len(self._shared_memory),
            is_converged=False,
        )

    def _notify(self, state: DiscussionState) -> None:
        """Call the on_state_update callback if registered."""
        if self._on_state_update:
            self._on_state_update(state)

    def _generate_report(self, topic: str, state: DiscussionState) -> str:
        """
        Generate a final report summarising the discussion using the LLM.

        Falls back to a structured text report if the LLM call fails.
        """
        # Build a summary prompt
        discussion_text_parts: list[str] = []
        for msg in self._shared_memory:
            if msg.speaker:
                discussion_text_parts.append(f"{msg.speaker}: {msg.content}")

        discussion_text = "\n\n".join(discussion_text_parts)

        system_prompt = (
            "あなたは議論の総括を行うアナリストです。"
            "以下の議論を分析し、日本語で総括レポートを作成してください。\n\n"
            "レポートには以下を含めてください：\n"
            "1. 各ペルソナの最終的な立場の要約\n"
            "2. 合意点と相違点\n"
            "3. 議論から得られた結論または洞察\n"
            "4. 今後の検討事項（あれば）\n\n"
            "レポートは構造化された形式（見出しと箇条書き）で記述してください。"
        )

        user_prompt = (
            f"【議論トピック】{topic}\n\n"
            f"【議論記録】\n{discussion_text}\n\n"
            "上記の議論についての総括レポートを作成してください。"
        )

        try:
            report_response = self._llm._client.chat.completions.create(
                model=self._llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                max_tokens=1500,
            )
            report_text = report_response.choices[0].message.content or ""
            if report_text.strip():
                return report_text.strip()
        except Exception as e:
            pass  # Fall through to manual report

        # Fallback: generate a structured report from state data
        return self._build_fallback_report(topic, state)

    def _build_fallback_report(self, topic: str, state: DiscussionState) -> str:
        """Build a plain-text fallback report from the DiscussionState."""
        lines: list[str] = [
            "=" * 60,
            f"MAGI システム 議論総括レポート",
            f"トピック: {topic}",
            f"総ターン数: {state.turn_count}",
            "=" * 60,
            "",
            "■ 各ペルソナの最終立場",
            "",
        ]

        for name in ALL_PERSONAS:
            ps = state.persona_states.get(name)
            if ps and ps.current_stance:
                lines.append(f"【{name}】")
                lines.append(ps.current_stance)
                lines.append("")

        convergence_voters = [
            name
            for name, ps in state.persona_states.items()
            if ps.convergence_vote is True
        ]
        lines.append("■ 収束判断")
        lines.append(f"収束に同意したペルソナ: {', '.join(convergence_voters) or 'なし'}")
        lines.append("")

        lines.append("■ 収束理由")
        for name in ALL_PERSONAS:
            ps = state.persona_states.get(name)
            if ps and ps.convergence_reason:
                lines.append(f"  {name}: {ps.convergence_reason}")
        lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
