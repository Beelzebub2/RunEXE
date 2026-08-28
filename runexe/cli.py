"""Command-line interface for RunEXE."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from runexe import __version__
from runexe.analyzer import analyze_executable
from runexe.compatibility import analyze_compatibility
from runexe.host import detect_host
from runexe.resources import extract_requested_execution_level
from runexe.runner import LaunchResult, RunnerError, launch
from runexe.ui import (
    console,
    print_banner,
    print_error,
    print_section,
    print_success,
    print_summary,
    print_warning,
)

app = typer.Typer(
    name="runexe",
    help="Safely inspect Windows executables and run them on Linux with Wine.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _error(message: str) -> None:
    print_error(message)


def _analysis_as_dict(result, compatibility, host) -> dict:
    data = asdict(result)
    data["path"] = str(result.path)
    data["compatibility"] = asdict(compatibility) if compatibility is not None else None
    data["host"] = asdict(host) if host is not None else None
    return data


@app.command()
def analyze(
    file: Annotated[
        Path, typer.Argument(help="PE executable, AppX/MSIX package, or package directory.")
    ],
    imports: Annotated[
        bool, typer.Option("--imports", "-i", help="List imported functions, not only DLL counts.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit a machine-readable JSON report.")
    ] = False,
    check_host: Annotated[
        bool, typer.Option("--host/--no-host", help="Include installed Wine and host capabilities.")
    ] = True,
) -> None:
    """Analyze a PE executable without running it."""

    try:
        result = analyze_executable(file)
        if not result.valid:
            if json_output:
                typer.echo(json.dumps(_analysis_as_dict(result, None, None), indent=2, default=str))
            else:
                typer.echo(f"File: {result.path}")
                typer.echo("Format: Invalid")
                typer.echo(f"Reason: {result.reason}")
            raise typer.Exit(code=1)

        host = detect_host() if check_host else None
        compatibility = analyze_compatibility(result, host)

        if json_output:
            typer.echo(
                json.dumps(_analysis_as_dict(result, compatibility, host), indent=2, default=str)
            )
            return

        print_banner("Static analysis - no Wine changes")
        summary_rows = [
            ("File", result.path),
            ("Format", result.format),
            ("Architecture", result.architecture),
        ]
        if result.subsystem:
            summary_rows.append(("Subsystem", result.subsystem))
        if result.package:
            summary_rows.extend(
                [
                    ("Package", result.package.display_name or result.package.identity_name),
                    ("Package version", result.package.version or "unknown"),
                    ("Package app", result.package.application_id or "default"),
                ]
            )
        print_summary("Executable", summary_rows)

        if result.version_info:
            product_name = result.version_info.strings.get("ProductName")
            company_name = result.version_info.strings.get("CompanyName")
            if product_name:
                typer.echo(f"Product: {product_name}")
            if company_name:
                typer.echo(f"Publisher: {company_name}")
            version_value = result.version_info.product_version or result.version_info.file_version
            if version_value:
                typer.echo(f"Version: {version_value}")

        if result.manifest:
            execution_level = extract_requested_execution_level(result.manifest)
            suffix = f" (execution level: {execution_level})" if execution_level else ""
            typer.echo(f"Manifest: Present{suffix}")

        if result.sections:
            print_section("Sections")
            for section in result.sections:
                typer.echo(
                    f"  {section.name:<8} RVA=0x{section.virtual_address:08X} "
                    f"Virtual=0x{section.virtual_size:X} RawSize=0x{section.raw_size:X} "
                    f"RawOffset=0x{section.raw_offset:X}"
                )

        if result.imports:
            print_section("Imports")
            for imported in result.imports:
                if imports:
                    typer.echo(f"  {imported.name}")
                    for function in imported.functions:
                        typer.echo(f"    {function}")
                else:
                    count = len(imported.functions)
                    unit = "function" if count == 1 else "functions"
                    typer.echo(f"  {imported.name:<24} ({count} {unit})")
            if not imports:
                console.print("\n[dim](use --imports/-i to list every imported function)[/dim]")

        print_summary(
            "Compatibility",
            [
                ("Application type", compatibility.application_type),
                ("Category", compatibility.category),
                ("Recommended runtime", compatibility.recommended_runtime),
                ("Architecture", compatibility.architecture),
                ("WINEARCH", compatibility.wine_arch or "N/A"),
                ("Supported", "Yes" if compatibility.supported else "No"),
            ],
        )

        if compatibility.blocking_issues:
            print_section("Blocking issues")
            for issue in compatibility.blocking_issues:
                console.print(f"  [bright_red]-[/bright_red] {issue}")
        if compatibility.warnings:
            print_section("Compatibility warnings")
            for warning in compatibility.warnings:
                print_warning(warning)
        if compatibility.required_verbs:
            print_section("Suggested provisioning")
            command = " ".join(compatibility.required_verbs)
            console.print(f"  [bright_cyan]winetricks[/bright_cyan] {command}")
        if compatibility.notes:
            print_section("Notes")
            for note in compatibility.notes:
                console.print(f"  [bright_black]-[/bright_black] {note}")
        if compatibility.dependencies:
            print_section("Detected dependencies")
            for dependency in compatibility.dependencies:
                console.print(
                    f"  {dependency.name} ({dependency.category}, "
                    f"{dependency.confidence} confidence)"
                )

    except typer.Exit:
        raise
    except (OSError, ValueError) as error:
        _error(str(error))
        raise typer.Exit(code=1) from error


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    file: Annotated[
        Path, typer.Argument(help="PE executable, AppX/MSIX package, or package directory.")
    ],
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Maximum runtime in seconds.")
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show launch details.")] = False,
    winver: Annotated[
        str | None,
        typer.Option("--winver", help="Wine Windows version: 7, 8, 8.1, 10, 11 (or win10)."),
    ] = None,
    prefix: Annotated[
        Path | None,
        typer.Option("--prefix", help="Use a specific Wine prefix instead of the per-app default."),
    ] = None,
    dependencies: Annotated[
        bool,
        typer.Option(
            "--dependencies/--no-dependencies",
            help="Install detected Winetricks dependencies.",
        ),
    ] = True,
) -> None:
    """Analyze, provision, and launch an executable with Wine.

    Place application arguments after ``--`` so they are passed through
    unchanged, for example: ``runexe run app.exe -- --portable``.
    """

    try:
        result = analyze_executable(file)
        if not result.valid:
            raise RunnerError(result.reason or "Invalid Windows executable")
        compatibility = analyze_compatibility(result, detect_host())

        print_banner(f"Launch - {result.path.name}")
        print_summary(
            "Launch plan",
            [
                ("Runtime", compatibility.recommended_runtime),
                ("Architecture", compatibility.architecture),
                ("WINEARCH", compatibility.wine_arch or "N/A"),
                ("Dependencies", ", ".join(compatibility.required_verbs) or "none detected"),
            ],
        )
        for warning in compatibility.warnings:
            print_warning(warning)
        if verbose:
            print_summary(
                "Launch details",
                [
                    ("Executable architecture", result.architecture),
                    ("WINEARCH", compatibility.wine_arch or "N/A"),
                ],
            )
        if dependencies and compatibility.required_verbs:
            console.print("Installing dependencies: " + ", ".join(compatibility.required_verbs))
        elif not dependencies and compatibility.required_verbs:
            console.print("Skipping detected dependencies (--no-dependencies).")

        launch_result: LaunchResult = launch(
            result,
            compatibility,
            extra_args=list(ctx.args),
            timeout=timeout,
            verbose=verbose,
            winver=winver,
            prefix=prefix,
            install_dependencies=dependencies,
        )

        if launch_result.stdout:
            stdout_end = "" if launch_result.stdout.endswith("\n") else "\n"
            console.print(launch_result.stdout, end=stdout_end)
        if launch_result.stderr:
            console.print(
                launch_result.stderr,
                end="" if launch_result.stderr.endswith("\n") else "\n",
                stderr=True,
            )
        if launch_result.timed_out:
            _error(f"Process exceeded the {timeout}-second timeout.")
            raise typer.Exit(code=124)
        if launch_result.exit_code != 0:
            _error(f"Process exited with code {launch_result.exit_code}.")
            code = launch_result.exit_code or 1
            raise typer.Exit(code=code if 1 <= code <= 255 else 1)
        print_success("Exited normally.")

    except typer.Exit:
        raise
    except (OSError, ValueError, RunnerError) as error:
        _error(str(error))
        raise typer.Exit(code=1) from error


@app.command()
def version() -> None:
    """Show the installed RunEXE version."""

    typer.echo(f"RunEXE {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
