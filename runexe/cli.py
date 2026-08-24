import typer

from runexe.analyzer import analyze_executable
from runexe.compatibility import analyze_compatibility
from runexe.resources import extract_requested_execution_level
from runexe.runner import LaunchResult, RunnerError, launch
from runexe.host import detect_host


app = typer.Typer(
    name="runexe",
    help="Analyze and run Windows executables on Linux.",
    no_args_is_help=True,
)


@app.command()
def analyze(
    file: str,
    imports: bool = typer.Option(
        False,
        "--imports",
        "-i",
        help="Show every imported function for each DLL, not just counts.",
    ),
):
    """Analyze a Windows executable."""

    try:
        result = analyze_executable(file)

        typer.echo(f"File: {result.path}")

        if not result.valid:
            typer.echo("Format: Invalid")
            typer.echo(f"Reason: {result.reason}")
            raise typer.Exit(code=1)

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

            if result.version_info.product_version:
                typer.echo(
                    f"Version: {result.version_info.product_version}"
                )

        if result.manifest:
            execution_level = extract_requested_execution_level(
                result.manifest
            )

            manifest_line = "Manifest: Present"

            if execution_level:
                manifest_line += f" (execution level: {execution_level})"

            typer.echo(manifest_line)

        if result.sections:
            typer.echo("")
            typer.echo("Sections:")

            for section in result.sections:
                typer.echo(
                    f"  {section.name:<8} "
                    f"RVA=0x{section.virtual_address:08X} "
                    f"Size=0x{section.virtual_size:X} "
                    f"Raw=0x{section.raw_offset:X}"
                )

        if result.imports:
            typer.echo("")
            typer.echo("Imports:")

            if imports:
                for imported in result.imports:
                    typer.echo(f"  {imported.name}")
                    for function in imported.functions:
                        typer.echo(f"    {function}")
            else:
                for imported in result.imports:
                    function_count = len(imported.functions)
                    unit = "function" if function_count == 1 else "functions"
                    typer.echo(
                        f"  {imported.name:<24} "
                        f"({function_count} {unit})"
                    )

                typer.echo("")
                typer.echo(
                    "(use --imports/-i to list every imported function)"
                )

        # Analyze compatibility.

        host = detect_host(result)

        compatibility = analyze_compatibility(result, host)

        typer.echo("")
        typer.echo("Compatibility:")

        typer.echo(
            f"  Application type: "
            f"{compatibility.application_type}"
        )

        typer.echo(
            f"  Category: "
            f"{compatibility.category}"
        )

        typer.echo(
            f"  Recommended runtime: "
            f"{compatibility.recommended_runtime}"
        )

        typer.echo(
            f"  Architecture: "
            f"{compatibility.architecture}"
        )

        typer.echo(
            f"  WINEARCH: "
            f"{compatibility.wine_arch or 'N/A'}"
        )

        typer.echo(
            f"  Supported: "
            f"{'Yes' if compatibility.supported else 'No'}"
        )

        if compatibility.blocking_issues:
            typer.echo("")
            typer.echo("⚠ Blocking issues:")

            for issue in compatibility.blocking_issues:
                typer.echo(f"  - {issue}")

        if compatibility.required_verbs:
            typer.echo("")
            typer.echo("Recommended fixes:")
            typer.echo(
                "  winetricks " + " ".join(compatibility.required_verbs)
            )

        if compatibility.notes:
            typer.echo("")
            typer.echo("Notes:")

            for note in compatibility.notes:
                typer.echo(f"  - {note}")

        if compatibility.dependencies:
            typer.echo("")
            typer.echo("Dependencies:")

            for dependency in compatibility.dependencies:
                typer.echo(
                    f"  {dependency.name}"
                    f" ({dependency.category}, "
                    f"{dependency.confidence} confidence)"
                )

    except FileNotFoundError as error:
        typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)

    except ValueError as error:
        typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)


@app.command()
def run(
    file: str,
    timeout: int = typer.Option(
        None,
        "--timeout",
        help="Seconds to wait before giving up on the launched process.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show more information about the launch process.",
    ),
    winver: str | None = typer.Option(
        None,
        "--winver",
        help="Force a specific Windows version for the Wine prefix (e.g. 'win10').",
    ),
):
    """Analyze, provision a prefix, and run a Windows executable."""

    try:
        result = analyze_executable(file)

        if not result.valid:
            typer.echo(f"Error: {result.reason}")
            raise typer.Exit(code=1)

        host = detect_host(result)

        compatibility = analyze_compatibility(result, host)

        typer.echo(
            f"Launching {result.path.name} "
            f"({compatibility.recommended_runtime})..."
        )

        if verbose:
            typer.echo("")
            typer.echo("Launch details:")
            typer.echo(f"  Executable architecture: {result.architecture}")
            typer.echo(
                f"  Recommended runtime: "
                f"{compatibility.recommended_runtime}"
            )
            typer.echo(
                f"  WINEARCH: "
                f"{compatibility.wine_arch or 'N/A'}"
            )

        if compatibility.required_verbs:
            typer.echo(
                "Installing dependencies: "
                + ", ".join(compatibility.required_verbs)
            )

        launch_result: LaunchResult = launch(
            result,
            compatibility,
            timeout=timeout,
            verbose=verbose,
            winver=winver,
        )

        if launch_result.timed_out:
            typer.echo(
                f"Timed out after {timeout}s; the process may still "
                f"be running."
            )
            raise typer.Exit(code=1)

        if launch_result.exit_code != 0:
            typer.echo(f"Exited with code {launch_result.exit_code}.")

            if launch_result.stderr.strip():
                typer.echo("")
                typer.echo("stderr:")
                typer.echo(launch_result.stderr.strip())

            raise typer.Exit(
                code=launch_result.exit_code or 1
            )

        typer.echo("Exited normally.")

    except FileNotFoundError as error:
        typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)

    except RunnerError as error:
        typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)

    except NotImplementedError as error:
        typer.echo(f"Not yet supported: {error}")
        raise typer.Exit(code=1)

    except ValueError as error:
        typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)


@app.command()
def version():
    """Show the RunEXE version."""
    typer.echo("RunEXE 0.1.0")


def main():
    app()


if __name__ == "__main__":
    main()