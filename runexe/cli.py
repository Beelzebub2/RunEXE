"""Command-line interface for RunEXE."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from runexe import __version__
from runexe.analyzer import analyze_executable
from runexe.compatibility import analyze_compatibility
from runexe.host import detect_host
from runexe.proton import ProtonError, discover_proton_installations, select_proton
from runexe.resources import extract_requested_execution_level
from runexe.runner import LaunchResult, RunnerError, launch
from runexe.ui import (
    console,
    error_console,
    print_banner,
    print_error,
    print_hint,
    print_section,
    print_success,
    print_summary,
    print_table,
    print_warning,
    status_text,
)


class BackendChoice(str, Enum):
    auto = "auto"
    wine = "wine"
    proton = "proton"


app = typer.Typer(
    name="runexe",
    help="Inspect Windows software and launch it through Wine or Proton.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)


def _analysis_as_dict(result, compatibility, host) -> dict:
    data = asdict(result)
    data["path"] = str(result.path)
    data["compatibility"] = asdict(compatibility) if compatibility is not None else None
    data["host"] = asdict(host) if host is not None else None
    return data


def _fail(message: str, code: int = 1) -> None:
    print_error(message)
    raise typer.Exit(code=code)


def _runtime_host_with_selector(host, selector: str | None):
    if selector is None:
        return host, None
    selected = select_proton(selector)
    return (
        replace(host, proton_installed=True, proton_versions=[selected.name]),
        selected,
    )


@app.command()
def analyze(
    file: Annotated[
        Path, typer.Argument(help="PE executable, AppX/MSIX package, or package directory.")
    ],
    imports: Annotated[
        bool, typer.Option("--imports", "-i", help="List functions under every imported DLL.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit only a machine-readable JSON report.")
    ] = False,
    check_host: Annotated[
        bool, typer.Option("--host/--no-host", help="Include local Wine and Proton availability.")
    ] = True,
    backend: Annotated[
        BackendChoice,
        typer.Option("--backend", help="Evaluate compatibility for a specific runtime."),
    ] = BackendChoice.auto,
) -> None:
    """Inspect software without executing it or modifying a prefix."""

    try:
        result = analyze_executable(file)
        if not result.valid:
            if json_output:
                typer.echo(json.dumps(_analysis_as_dict(result, None, None), indent=2, default=str))
                raise typer.Exit(code=1)
            _fail(result.reason or "Invalid Windows executable")

        host = detect_host() if check_host else None
        compatibility = analyze_compatibility(result, host, backend.value)
        if json_output:
            typer.echo(
                json.dumps(_analysis_as_dict(result, compatibility, host), indent=2, default=str)
            )
            return

        print_banner("Static analysis | no compatibility environment will be changed")
        summary_rows: list[tuple[str, object]] = [
            ("File", result.path),
            ("Format", result.format or "unknown"),
            ("Architecture", result.architecture or "unknown"),
            ("Subsystem", result.subsystem or "unknown"),
        ]
        if result.package:
            summary_rows.extend(
                [
                    ("Package", result.package.display_name or result.package.identity_name),
                    ("Package version", result.package.version or "unknown"),
                    ("Package app", result.package.application_id or "default"),
                ]
            )
        if result.version_info:
            summary_rows.extend(
                [
                    ("Product", result.version_info.strings.get("ProductName", "unknown")),
                    ("Publisher", result.version_info.strings.get("CompanyName", "unknown")),
                    (
                        "Version",
                        result.version_info.product_version
                        or result.version_info.file_version
                        or "unknown",
                    ),
                ]
            )
        if result.manifest:
            level = extract_requested_execution_level(result.manifest)
            summary_rows.append(("Manifest", level or "present"))
        print_summary("Executable", summary_rows)

        if result.sections:
            print_table(
                "PE sections",
                (("Name", "left"), ("RVA", "right"), ("Virtual", "right"), ("Raw", "right")),
                (
                    (
                        section.name,
                        f"0x{section.virtual_address:08X}",
                        f"0x{section.virtual_size:X}",
                        f"0x{section.raw_size:X} @ 0x{section.raw_offset:X}",
                    )
                    for section in result.sections
                ),
            )

        if result.imports:
            if imports:
                print_section("Imports")
                for imported in result.imports:
                    console.print(f"[label]{imported.name}[/label]")
                    console.print(
                        "  " + ", ".join(imported.functions)
                        if imported.functions
                        else "  [muted]none[/muted]"
                    )
            else:
                print_table(
                    "Imported libraries",
                    (("DLL", "left"), ("Functions", "right")),
                    ((item.name, len(item.functions)) for item in result.imports),
                )
                print_hint("Add --imports to show individual function names.")

        print_summary(
            "Compatibility",
            [
                ("Application", compatibility.application_type),
                ("Category", compatibility.category),
                ("Selected runtime", compatibility.recommended_runtime),
                ("Backend", compatibility.backend),
                ("Prefix architecture", compatibility.wine_arch or "N/A"),
                ("Status", status_text(not compatibility.blocking_issues)),
            ],
        )
        if compatibility.blocking_issues:
            print_section("Blocking issues")
            for issue in compatibility.blocking_issues:
                print_error(issue)
        for warning in compatibility.warnings:
            print_warning(warning)

        if compatibility.dependencies:
            print_table(
                "Detected dependencies",
                (
                    ("Component", "left"),
                    ("Category", "left"),
                    ("Confidence", "left"),
                    ("Verb", "left"),
                ),
                (
                    (
                        item.name,
                        item.category,
                        item.confidence,
                        item.winetricks_verb or "built in / manual",
                    )
                    for item in compatibility.dependencies
                ),
            )
        if compatibility.notes:
            print_section("Notes")
            for note in compatibility.notes:
                console.print(f"[muted]-[/muted] {note}")

    except typer.Exit:
        raise
    except (OSError, ValueError, ProtonError) as error:
        _fail(str(error))


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    file: Annotated[
        Path, typer.Argument(help="PE executable, AppX/MSIX package, or package directory.")
    ],
    backend: Annotated[
        BackendChoice,
        typer.Option("--backend", help="Runtime selection: auto, wine, or proton."),
    ] = BackendChoice.auto,
    proton: Annotated[
        str | None,
        typer.Option("--proton", help="Proton build name, installation directory, or script path."),
    ] = None,
    prefix: Annotated[
        Path | None,
        typer.Option(
            "--prefix",
            help="Custom Wine prefix, or Proton compat-data directory when using Proton.",
        ),
    ] = None,
    dependencies: Annotated[
        bool | None,
        typer.Option(
            "--deps/--no-deps",
            help="Force dependency provisioning on or off (auto: Wine on, Proton off).",
        ),
    ] = None,
    winver: Annotated[
        str | None,
        typer.Option("--winver", help="Reported Windows version: 7, 8, 8.1, 10, or 11."),
    ] = None,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Maximum runtime in seconds.")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show runtime commands.")
    ] = False,
) -> None:
    """Analyze, prepare, and launch software through Wine or Proton.

    Put application arguments after ``--``: ``runexe run app.exe -- --portable``.
    """

    try:
        if proton is not None and backend is BackendChoice.wine:
            raise RunnerError("--proton cannot be combined with --backend wine.")

        result = analyze_executable(file)
        if not result.valid:
            raise RunnerError(result.reason or "Invalid Windows executable")

        host = detect_host()
        host, selected_proton = _runtime_host_with_selector(host, proton)
        preference = BackendChoice.proton if proton and backend is BackendChoice.auto else backend
        compatibility = analyze_compatibility(result, host, preference.value)
        install_dependencies = (
            dependencies if dependencies is not None else compatibility.backend == "wine"
        )

        print_banner(f"Launch | {result.path.name}")
        plan_rows: list[tuple[str, object]] = [
            ("Backend", compatibility.backend.upper()),
            (
                "Runtime",
                selected_proton.name if selected_proton else compatibility.recommended_runtime,
            ),
            ("Architecture", compatibility.architecture),
            (
                "Environment",
                prefix
                or (
                    "isolated per-app compat data"
                    if compatibility.backend == "proton"
                    else "isolated per-app prefix"
                ),
            ),
            ("Dependencies", ", ".join(compatibility.required_verbs) or "none detected"),
            ("Provisioning", "enabled" if install_dependencies else "skipped"),
        ]
        print_summary("Launch plan", plan_rows)
        for warning in compatibility.warnings:
            print_warning(warning)
        if compatibility.blocking_issues:
            for issue in compatibility.blocking_issues:
                print_error(issue)
            raise typer.Exit(code=1)
        if (
            dependencies is None
            and compatibility.backend == "proton"
            and compatibility.required_verbs
        ):
            print_hint(
                "Proton dependency changes are skipped by default to protect its prefix; "
                "use --deps to opt in."
            )

        launch_result: LaunchResult = launch(
            result,
            compatibility,
            extra_args=list(ctx.args),
            timeout=timeout,
            verbose=verbose,
            winver=winver,
            prefix=prefix,
            install_dependencies=install_dependencies,
            proton=selected_proton.script if selected_proton else proton,
        )

        if launch_result.stdout:
            console.print(
                launch_result.stdout,
                end="" if launch_result.stdout.endswith("\n") else "\n",
                markup=False,
            )
        if launch_result.stderr:
            error_console.print(
                launch_result.stderr,
                end="" if launch_result.stderr.endswith("\n") else "\n",
                markup=False,
            )
        if launch_result.timed_out:
            _fail(f"Process exceeded the {timeout}-second timeout.", 124)
        if launch_result.exit_code != 0:
            code = launch_result.exit_code or 1
            _fail(
                f"Process exited with code {launch_result.exit_code}.",
                code if 1 <= code <= 255 else 1,
            )
        print_success("Process exited normally.")

    except typer.Exit:
        raise
    except (OSError, ValueError, ProtonError, RunnerError) as error:
        _fail(str(error))


@app.command(name="backends")
def list_backends() -> None:
    """Show the Wine and Proton runtimes RunEXE can use."""

    host = detect_host()
    installations = discover_proton_installations()
    print_banner("Runtime discovery")
    print_summary(
        "Host",
        [
            ("Architecture", host.architecture),
            ("Wine", status_text(host.wine_installed)),
            ("Wine version", host.wine_version or "not detected"),
            ("Winetricks", status_text(host.winetricks_installed)),
            ("Proton", status_text(bool(installations))),
        ],
    )
    if installations:
        print_table(
            "Installed Proton builds (selection order)",
            (("Name", "left"), ("Version", "left"), ("Launcher", "left")),
            ((item.name, item.version or "unknown", item.script) for item in installations),
        )
        print_hint("Choose one with --proton NAME or --proton /path/to/proton.")
    else:
        print_hint(
            "Install Proton through Steam, add a custom build to compatibilitytools.d, "
            "or set RUNEXE_PROTON_PATH."
        )


@app.command()
def version() -> None:
    """Show the installed RunEXE version."""

    typer.echo(f"RunEXE {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
