"""Rich-based display for the MAGI System discussion."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from magi.models import DiscussionState, PersonaState, Sentiment
from magi.persona import ALL_PERSONAS, PERSONA_COLORS


# Colour scheme
PERSONA_STYLE: dict[str, str] = {
    "MELCHIOR": "bold blue",
    "BALTHASAR": "bold yellow",
    "CASPER": "bold green",
    "ファシリテーター": "bold white on dark_red",
}

SENTIMENT_SYMBOL: dict[str, str] = {
    "positive": "[green]▲[/green]",
    "neutral": "[dim]●[/dim]",
    "negative": "[red]▼[/red]",
}

CONVERGENCE_SYMBOL = {
    True: "[green]✔ 収束[/green]",
    False: "[red]✘ 継続[/red]",
    None: "[dim]？ 未決[/dim]",
}

_HEADER_SIZE = 4  # panel border (2) + content (1) + margin (1)


def _build_layout() -> Layout:
    """
    Screen layout:

        ┌─────────────────────────────────────────┐  header (fixed)
        ├───────────────────────┬─────────────────┤
        │                       │   MELCHIOR      │
        │   conversation log    ├─────────────────┤
        │      (flexible)       │   BALTHASAR     │
        │                       ├─────────────────┤
        │                       │   CASPER        │
        └───────────────────────┴─────────────────┘
    """
    root = Layout()
    root.split_column(
        Layout(name="header", size=_HEADER_SIZE),
        Layout(name="body"),
    )
    root["body"].split_row(
        Layout(name="conversation", ratio=3),
        Layout(name="personas", ratio=2),
    )
    root["personas"].split_column(
        Layout(name="persona_MELCHIOR"),
        Layout(name="persona_BALTHASAR"),
        Layout(name="persona_CASPER"),
    )
    return root


class DiscussionDisplay:
    """Manages the Rich live display for the MAGI System discussion."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self._console = console or Console()
        self._live: Optional[Live] = None
        self._layout: Optional[Layout] = None
        self._state: Optional[DiscussionState] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the live display."""
        self._layout = _build_layout()
        self._apply_state(None)
        self._live = Live(
            self._layout,
            console=self._console,
            refresh_per_second=4,
            screen=True,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def update(self, state: DiscussionState) -> None:
        """Update the display with a new state snapshot."""
        self._state = state
        if self._layout is None:
            return
        self._apply_state(state)

    def print_final_report(self, report: str) -> None:
        """Print the final report after the live display has stopped."""
        self._console.print()
        self._console.print(
            Panel(
                report,
                title="[bold white on dark_magenta] MAGI システム 最終レポート [/bold white on dark_magenta]",
                border_style="magenta",
                padding=(1, 2),
            )
        )

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _apply_state(self, state: Optional[DiscussionState]) -> None:
        """Push all rendered panels into the layout sections."""
        assert self._layout is not None
        self._layout["header"].update(self._render_header(state))
        self._layout["conversation"].update(self._render_conversation(state))
        for name in ALL_PERSONAS:
            ps = state.persona_states.get(name) if state else None
            self._layout[f"persona_{name}"].update(self._render_single_persona_panel(name, ps))

    def _render_header(self, state: Optional[DiscussionState]) -> Panel:
        if state is None:
            return Panel(
                Text("初期化中...", style="dim"),
                title="[bold white on dark_blue] ⚡ MAGI System ⚡ [/bold white on dark_blue]",
                border_style="bright_blue",
                padding=(0, 1),
            )

        t = Text()
        t.append("議論トピック: ", style="bold white")
        t.append(state.topic, style="bold cyan")
        t.append("   ターン数: ", style="dim")
        t.append(str(state.turn_count), style="bold white")

        votes = state.count_convergence_votes()
        t.append("   収束票: ", style="dim")
        t.append(str(votes), style="bold green" if votes >= 2 else "bold white")
        t.append("/3", style="dim")

        if state.is_converged:
            t.append_text(Text.from_markup("   [bold green]■ 議論収束[/bold green]"))

        return Panel(
            t,
            title="[bold white on dark_blue] ⚡ MAGI System ⚡ [/bold white on dark_blue]",
            border_style="bright_blue",
            padding=(0, 1),
        )

    def _render_conversation(self, state: Optional[DiscussionState]) -> Panel:
        if state is None or not state.messages:
            content = Text("（議論開始前）", style="dim italic")
            return Panel(content, title="[bold]議論ログ[/bold]", border_style="blue", padding=(0, 1))

        lines: list[Text] = []

        # Render newest-first so that Layout's top-crop never hides recent messages.
        speaker_msgs = [m for m in state.messages if m.speaker]
        for msg in reversed(speaker_msgs):
            ts = msg.timestamp.strftime("%H:%M:%S")
            line = Text()
            line.append(f"[{ts}] ", style="dim")
            line.append(msg.speaker, style=PERSONA_STYLE.get(msg.speaker, "white"))
            line.append(": ", style="dim")
            line.append(msg.content, style="white")
            lines.append(line)
            lines.append(Text(""))

        content = Text("\n").join(lines)
        return Panel(
            content,
            title=f"[bold]議論ログ[/bold] [dim](最新が上 / 全{len(speaker_msgs)}件)[/dim]",
            border_style="blue",
            padding=(0, 1),
        )

    def _render_single_persona_panel(self, name: str, ps: Optional[PersonaState]) -> Panel:
        color = PERSONA_COLORS.get(name, "white")
        style = PERSONA_STYLE.get(name, "white")
        parts: list[Text] = []

        if ps is None:
            parts.append(Text("（データなし）", style="dim"))
        else:
            # Initial role badge
            if ps.initial_role:
                role_colors = {"推進派": "green", "懐疑派": "red", "代替案提案派": "magenta"}
                rc = role_colors.get(ps.initial_role, "white")
                parts.append(Text.from_markup(f"[bold {rc}]【{ps.initial_role}】[/bold {rc}]"))
                parts.append(Text(""))

            # Stance — keep to 2 lines max
            parts.append(Text("■ 現在の立場", style="bold"))
            if ps.current_stance:
                snippet = ps.current_stance[:80] + ("..." if len(ps.current_stance) > 80 else "")
                parts.append(Text(snippet, style="white"))
            else:
                parts.append(Text("（未発言）", style="dim italic"))
            parts.append(Text(""))

            # Emotions
            parts.append(Text("■ 他者への感情", style="bold"))
            for other in [n for n in ALL_PERSONAS if n != name]:
                emotion = ps.emotions.get(other)
                if emotion:
                    sent_val = (
                        emotion.sentiment.value
                        if hasattr(emotion.sentiment, "value")
                        else str(emotion.sentiment)
                    )
                    sym = SENTIMENT_SYMBOL.get(sent_val, "●")
                    line = Text()
                    line.append(f"  {other}: ", style=PERSONA_STYLE.get(other, "white"))
                    line.append_text(Text.from_markup(sym))
                    line.append(f" {emotion.intensity:.1f}", style="dim")
                    parts.append(line)
            parts.append(Text(""))

            # Convergence vote
            vote_line = Text()
            vote_line.append("■ 収束: ", style="bold")
            vote_line.append_text(Text.from_markup(CONVERGENCE_SYMBOL.get(ps.convergence_vote, "？")))
            parts.append(vote_line)
            if ps.convergence_reason:
                short = ps.convergence_reason[:50] + ("..." if len(ps.convergence_reason) > 50 else "")
                parts.append(Text(f"  {short}", style="dim italic"))

        return Panel(
            Text("\n").join(parts),
            title=f"[{style}] {name} [/{style}]",
            border_style=color,
            padding=(0, 1),
        )
