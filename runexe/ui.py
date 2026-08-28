"""Consistent Rich presentation primitives for the RunEXE CLI."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from . import __version__

THEME = Theme(
    {
        "brand.cyan": "bold #16d9ff",
        "brand.blue": "bold #3478ff",
        "brand.amber": "bold #ffb21a",
        "label": "bold #7ddfff",
        "muted": "#7e8ca8",
        "ok": "bold #41d98a",
        "warn": "bold #ffc857",
        "danger": "bold #ff6577",
    }
)
console = Console(theme=THEME, highlight=False)
error_console = Console(theme=THEME, highlight=False, stderr=True)

# ASCII framing is intentional. RunEXE is commonly invoked from Windows shells
# whose active code page cannot encode Unicode box-drawing or status glyphs.
UI_BOX = box.ASCII


def brand_mark() -> Text:
    """A terminal-sized sibling of the README logo: prompt, bridge, launch."""

    mark = Text()
    mark.append(">", style="brand.cyan")
    mark.append("==", style="brand.blue")
    mark.append(">", style="brand.amber")
    return mark


def print_banner(context: str | None = None, *, compact: bool = False) -> None:
    mark = brand_mark()
    mark.append("  RunEXE", style="bold white")
    mark.append(f"  {__version__}", style="muted")
    if compact:
        console.print(mark)
        return

    subtitle = Text("Inspect safely | choose intelligently | launch cleanly", style="muted")
    content: list[object] = [mark, subtitle]
    if context:
        content.extend([Text(), Text(context, style="brand.amber")])
    console.print(
        Panel(
            Group(*content),
            box=UI_BOX,
            border_style="#245bd6",
            padding=(0, 2),
        )
    )


def print_summary(title: str, rows: Iterable[tuple[str, object]]) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="label", no_wrap=True)
    table.add_column(style="white", overflow="fold")
    for label, value in rows:
        table.add_row(label, value if isinstance(value, Text) else Text(str(value)))
    console.print(
        Panel(table, title=f"[bold]{escape(title)}[/bold]", border_style="#334a72", box=UI_BOX)
    )


def print_table(
    title: str,
    columns: Sequence[tuple[str, str]],
    rows: Iterable[Sequence[object]],
) -> None:
    table = Table(
        title=title,
        box=UI_BOX,
        header_style="label",
        border_style="#334a72",
        row_styles=("", "dim"),
    )
    for heading, justify in columns:
        table.add_column(heading, justify=justify, overflow="fold")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


def print_section(title: str) -> None:
    console.rule(
        f"[bold #58a6ff]{escape(title)}[/bold #58a6ff]",
        characters="-",
        style="#273858",
    )


def print_warning(message: str) -> None:
    console.print(f"[warn]! Warning[/warn]  {escape(message)}")


def print_error(message: str) -> None:
    error_console.print(f"[danger]x Error[/danger]  {escape(message)}")


def print_success(message: str) -> None:
    console.print(f"[ok]OK[/ok]  {escape(message)}")


def print_hint(message: str) -> None:
    console.print(f"[muted]Tip  {escape(message)}[/muted]")


def status_text(value: bool, yes: str = "Ready", no: str = "Unavailable") -> Text:
    return Text(f"[+] {yes}" if value else f"[-] {no}", style="ok" if value else "danger")
