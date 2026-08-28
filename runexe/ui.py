"""Small, terminal-friendly presentation helpers for the RunEXE CLI."""

from __future__ import annotations

from collections.abc import Iterable

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__

console = Console()


def print_banner(command: str | None = None) -> None:
    """Print the CLI mark and a short command context."""

    prompt = Text("  >_", style="bold bright_cyan")
    prompt.append("   [ ][ ]", style="bold bright_blue")
    prompt.append("\n  RunEXE", style="bold white")
    prompt.append(f"  v{__version__}", style="dim")
    prompt.append("\n  Windows apps on Linux", style="bright_black")
    if command:
        prompt.append(f"\n\n  {command}", style="bold bright_yellow")
    console.print(Panel(prompt, border_style="bright_blue", box=box.ASCII, padding=(0, 2)))


def print_summary(title: str, rows: Iterable[tuple[str, object]]) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAD, show_header=False, padding=(0, 1))
    table.add_column("Field", style="bright_cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for label, value in rows:
        table.add_row(label, Text(str(value)))
    console.print(table)


def print_section(title: str) -> None:
    console.print(f"\n[bold bright_blue]> {escape(title)}[/bold bright_blue]")


def print_warning(message: str) -> None:
    console.print(f"[bold bright_yellow]Warning[/bold bright_yellow]  {escape(message)}")


def print_error(message: str) -> None:
    console.print(
        f"[bold bright_red]Error[/bold bright_red]  {escape(message)}",
        stderr=True,
    )


def print_success(message: str) -> None:
    console.print(f"[bold bright_green][OK][/bold bright_green] {escape(message)}")
