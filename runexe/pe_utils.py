import subprocess
import sys

from .models import PESection


def rva_to_file_offset(
    rva: int,
    sections: list[PESection],
) -> int | None:
    """Convert a PE relative virtual address to a file offset."""

    for section in sections:
        section_start = section.virtual_address
        # Only bytes backed by the file can be parsed. VirtualSize can
        # include zero-filled memory beyond SizeOfRawData; mapping that
        # range would point into unrelated file data or past EOF.
        section_end = section_start + section.raw_size

        if section_start <= rva < section_end:
            offset_inside_section = rva - section_start
            return section.raw_offset + offset_inside_section

    return None


def rva_range_to_file_offset(
    rva: int,
    size: int,
    sections: list[PESection],
) -> int | None:
    """Map an RVA range only when every requested byte is file-backed."""

    if size < 0:
        return None
    for section in sections:
        offset_in_section = rva - section.virtual_address
        if (
            0 <= offset_in_section <= section.raw_size
            and size <= section.raw_size - offset_in_section
        ):
            return section.raw_offset + offset_in_section
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
            print(f"[runexe] Failed with exit code {result.returncode}.")
    else:
        if result.returncode == 0:
            sys.stdout.write("ok\n")
        else:
            sys.stdout.write("failed\n")

        sys.stdout.flush()

    return result
