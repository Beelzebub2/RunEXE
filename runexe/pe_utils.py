import sys
import subprocess

from .models import PESection


def rva_to_file_offset(
    rva: int,
    sections: list[PESection],
) -> int | None:
    """Convert a PE relative virtual address to a file offset."""

    for section in sections:
        section_start = section.virtual_address
        section_end = section_start + max(
            section.virtual_size,
            section.raw_size,
        )

        if section_start <= rva < section_end:
            offset_inside_section = rva - section_start
            return section.raw_offset + offset_inside_section

    return None


def run_with_progress(
    command: list[str],
    *,
    env: dict[str, str] | None,
    description: str,
    timeout: int | None,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command with a simple status indicator."""

    if verbose:
        print(f"[runexe] {description}")
        print(f"[runexe] Command: {' '.join(command)}")
    else:
        sys.stdout.write(f"{description}... ")
        sys.stdout.flush()

    try:
        result = subprocess.run(
            command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired:
        if not verbose:
            sys.stdout.write("timeout\n")
            sys.stdout.flush()

        raise

    if verbose:
        if result.returncode == 0:
            print("[runexe] Completed successfully.")
        else:
            print(
                f"[runexe] Failed with exit code "
                f"{result.returncode}."
            )
    else:
        if result.returncode == 0:
            sys.stdout.write("✓\n")
        else:
            sys.stdout.write("✗\n")

        sys.stdout.flush()

    return result