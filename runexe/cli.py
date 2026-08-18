import typer

from runexe.analyzer import analyze_executable, rva_to_file_offset


app = typer.Typer(
    name="runexe",
    help="Analyze and run Windows executables on Linux.",
    no_args_is_help=True,
)


@app.command()
def analyze(file: str):
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

            for imported in result.imports:
                typer.echo(f"  {imported.name}")
                for function in imported.functions:
                    typer.echo(f"    {function}")
    except FileNotFoundError as error:
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