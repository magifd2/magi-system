"""Entry point for the MAGI System."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from magi.discussion import DiscussionEngine
from magi.display import DiscussionDisplay
from magi.llm import LLMClient
from magi.models import DiscussionState
from magi.save import save_discussion


_console = Console()


def _ask(prompt_markup: str, default: str = "") -> str:
    """Print a Rich-formatted prompt, then read input via built-in input().
    Using input() instead of rich.Prompt avoids multi-byte cursor-position bugs."""
    _console.print(prompt_markup + (" " if default else ""), end="", markup=True)
    if default:
        _console.print(f"[dim]({default})[/dim] ", end="")
    try:
        value = input()
    except EOFError:
        return default
    return value.strip() or default


def _confirm(prompt_markup: str, default: bool = True) -> bool:
    """Print a Rich-formatted yes/no prompt and return the boolean answer."""
    hint = "[Y/n]" if default else "[y/N]"
    _console.print(f"{prompt_markup} [dim]{hint}[/dim] ", end="", markup=True)
    try:
        answer = input().strip().lower()
    except EOFError:
        return default
    if answer in ("y", "yes", "はい"):
        return True
    if answer in ("n", "no", "いいえ"):
        return False
    return default


def _print_banner() -> None:
    """Print the MAGI System startup banner."""
    banner = Text(justify="center")
    banner.append("\n")
    banner.append("███╗   ███╗ █████╗  ██████╗ ██╗\n", style="bold blue")
    banner.append("████╗ ████║██╔══██╗██╔════╝ ██║\n", style="bold blue")
    banner.append("██╔████╔██║███████║██║  ███╗██║\n", style="bold cyan")
    banner.append("██║╚██╔╝██║██╔══██║██║   ██║██║\n", style="bold cyan")
    banner.append("██║ ╚═╝ ██║██║  ██║╚██████╔╝██║\n", style="bold bright_cyan")
    banner.append("╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝\n", style="bold bright_cyan")
    banner.append("\n")
    banner.append("Multi-persona AI Thought Experiment System\n", style="dim italic")
    banner.append("MELCHIOR  •  BALTHASAR  •  CASPER\n", style="dim")
    banner.append("\n")

    _console.print(
        Panel(
            banner,
            border_style="bright_blue",
            padding=(0, 4),
        )
    )


def _on_state_update(display: DiscussionDisplay, state: DiscussionState) -> None:
    """Callback to refresh the display when state changes."""
    display.update(state)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="magi",
        description="MAGI System — Multi-persona AI thought experiment tool",
    )
    parser.add_argument(
        "-t", "--topic",
        metavar="TOPIC",
        help="議論のトピックを指定（省略時は対話入力）",
    )
    parser.add_argument(
        "-s", "--save",
        action="store_true",
        default=False,
        help="議論終了後に確認なしで自動保存する",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        default=None,
        help="保存先ディレクトリ（デフォルト: カレントディレクトリ）。--save と併用",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for the MAGI System CLI."""
    args = _parse_args()

    _print_banner()

    _console.print(
        Panel(
            "[dim]MELCHIOR[/dim]: 冷静・論理・データ重視\n"
            "[dim]BALTHASAR[/dim]: 人間的・感情・倫理重視\n"
            "[dim]CASPER[/dim]: 実利・現実主義・リスク重視",
            title="[bold]ペルソナ紹介[/bold]",
            border_style="dim",
            padding=(0, 2),
        )
    )
    _console.print()

    # Resolve topic: CLI arg > interactive prompt
    if args.topic:
        topic = args.topic.strip()
        _console.print(f"[dim]トピック (引数):[/dim] [bold cyan]{topic}[/bold cyan]\n")
    else:
        try:
            topic = _ask("[bold cyan]議論トピックを入力してください[/bold cyan]:")
        except KeyboardInterrupt:
            _console.print("\n[dim]中断しました。[/dim]")
            sys.exit(0)

    if not topic:
        _console.print("[red]トピックが入力されていません。終了します。[/red]")
        sys.exit(1)

    _console.print()
    _console.print(Rule("[bold blue]MAGI システム 起動[/bold blue]"))
    _console.print()

    # Set up display
    display = DiscussionDisplay(console=_console)

    # Set up LLM client
    llm_client = LLMClient()

    # Set up discussion engine with display callback
    engine = DiscussionEngine(
        llm_client=llm_client,
        on_state_update=lambda state: _on_state_update(display, state),
    )

    # Start the live display
    display.start()

    try:
        final_state = engine.run(topic=topic)
    except KeyboardInterrupt:
        _console.print("\n[yellow]議論を中断しました。[/yellow]")
        display.stop()
        sys.exit(0)
    except Exception as e:
        display.stop()
        _console.print(f"\n[red]エラーが発生しました: {e}[/red]")
        raise
    finally:
        display.stop()

    # Print final report
    if final_state.final_report:
        display.print_final_report(final_state.final_report)
    else:
        _console.print(
            Panel(
                "[dim]最終レポートを生成できませんでした。[/dim]",
                title="レポート",
                border_style="red",
            )
        )

    # --- Save: auto (--save) or interactive ---
    _console.print()
    save_dir = Path(args.output) if args.output else Path.cwd()

    if args.save:
        do_save = True
    else:
        try:
            do_save = _confirm("[bold cyan]議論ログと最終レポートをファイルに保存しますか？[/bold cyan]", default=True)
        except KeyboardInterrupt:
            do_save = False

    if do_save:
        if not args.save:
            # Interactive: allow overriding the directory
            save_dir = Path(_ask("[cyan]保存先ディレクトリ[/cyan]:", default=str(save_dir)))
        try:
            save_path = save_discussion(final_state, output_dir=save_dir)
            _console.print(
                Panel(
                    f"[green]保存完了:[/green] {save_path}",
                    border_style="green",
                    padding=(0, 1),
                )
            )
        except Exception as e:
            _console.print(f"[red]保存に失敗しました: {e}[/red]")

    _console.print()
    _console.print(Rule("[dim]MAGI システム 終了[/dim]"))


if __name__ == "__main__":
    main()
