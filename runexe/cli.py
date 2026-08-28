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

app = typer.Typer(
    name="runexe",
    help="Safely inspect Windows executables and run them on Linux with Wine.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _error(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)


def _analysis_as_dict(result, compatibility, host) -> dict:
    data = asdict(result)
    data["path"] = str(result.path)
    data["compatibility"] = asdict(compatibility) if compatibility is not None else None
    data["host"] = asdict(host) if host is not None else None
    return data


@app.command()
def analyze(
    file: Annotated[
        Path, typer.Argument(help="Executable file, or a directory containing one .exe.")
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
                typer.echo(json.dumps(_analysis_as_dict(result, None, None), indent=2))
            else:
                typer.echo(f"File: {result.path}")
                typer.echo("Format: Invalid")
                typer.echo(f"Reason: {result.reason}")
            raise typer.Exit(code=1)

        host = detect_host() if check_host else None
        compatibility = analyze_compatibility(result, host)

        if json_output:
            typer.echo(json.dumps(_analysis_as_dict(result, compatibility, host), indent=2))
            return

        typer.echo(f"File: {result.path}")
        typer.echo(f"Format: {result.format}")
        typer.echo(f"Architecture: {result.architecture}")
        if result.subsystem:
            typer.echo(f"Subsystem: {result.subsystem}")

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
            typer.echo("\nSections:")
            for section in result.sections:
                typer.echo(
                    f"  {section.name:<8} RVA=0x{section.virtual_address:08X} "
                    f"Virtual=0x{section.virtual_size:X} RawSize=0x{section.raw_size:X} "
                    f"RawOffset=0x{section.raw_offset:X}"
                )

        if result.imports:
            typer.echo("\nImports:")
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
                typer.echo("\n(use --imports/-i to list every imported function)")

        typer.echo("\nCompatibility:")
        typer.echo(f"  Application type: {compatibility.application_type}")
        typer.echo(f"  Category: {compatibility.category}")
        typer.echo(f"  Recommended runtime: {compatibility.recommended_runtime}")
        typer.echo(f"  Architecture: {compatibility.architecture}")
        typer.echo(f"  WINEARCH: {compatibility.wine_arch or 'N/A'}")
        typer.echo(f"  Supported architecture: {'Yes' if compatibility.supported else 'No'}")

        if compatibility.blocking_issues:
            typer.echo("\nBlocking issues:")
            for issue in compatibility.blocking_issues:
                typer.echo(f"  - {issue}")
        if compatibility.warnings:
            typer.echo("\nCompatibility warnings:")
            for warning in compatibility.warnings:
                typer.echo(f"  - {warning}")
        if compatibility.required_verbs:
            typer.echo("\nSuggested provisioning:")
            typer.echo("  winetricks " + " ".join(compatibility.required_verbs))
        if compatibility.notes:
            typer.echo("\nNotes:")
            for note in compatibility.notes:
                typer.echo(f"  - {note}")
        if compatibility.dependencies:
            typer.echo("\nDetected dependencies:")
            for dependency in compatibility.dependencies:
                typer.echo(
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
        Path, typer.Argument(help="Executable file, or a directory containing one .exe.")
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

        typer.echo(f"Launching {result.path.name} ({compatibility.recommended_runtime})...")
        for warning in compatibility.warnings:
            typer.echo(f"Warning: {warning}", err=True)
        if verbose:
            typer.echo("\nLaunch details:")
            typer.echo(f"  Executable architecture: {result.architecture}")
            typer.echo(f"  WINEARCH: {compatibility.wine_arch or 'N/A'}")
        if dependencies and compatibility.required_verbs:
            typer.echo("Installing dependencies: " + ", ".join(compatibility.required_verbs))
        elif not dependencies and compatibility.required_verbs:
            typer.echo("Skipping detected dependencies (--no-dependencies).")

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
            typer.echo(launch_result.stdout, nl=not launch_result.stdout.endswith("\n"))
        if launch_result.stderr:
            typer.echo(launch_result.stderr, err=True, nl=not launch_result.stderr.endswith("\n"))
        if launch_result.timed_out:
            _error(f"Process exceeded the {timeout}-second timeout.")
            raise typer.Exit(code=124)
        if launch_result.exit_code != 0:
            _error(f"Process exited with code {launch_result.exit_code}.")
            code = launch_result.exit_code or 1
            raise typer.Exit(code=code if 1 <= code <= 255 else 1)
        typer.echo("Exited normally.")

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
