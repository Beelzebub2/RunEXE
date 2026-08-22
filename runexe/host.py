import platform
import shutil
import subprocess
import tempfile
import os
from pathlib import Path

from .models import HostInfo, ExecutableInfo


def _wine_supports_32bit_prefix(wine_binary: str) -> bool:
    """Test whether the installed Wine can create a 32-bit prefix.

    A temporary prefix is used so this test does not modify any
    existing Wine prefix or RunEXE prefix.
    """

    with tempfile.TemporaryDirectory(
        prefix="runexe-wine32-"
    ) as temp_dir:

        env = os.environ.copy()

        env["WINEPREFIX"] = temp_dir
        env["WINEARCH"] = "win32"

        try:
            result = subprocess.run(
                [
                    wine_binary,
                    "wineboot",
                    "--init",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )

        except (
            subprocess.TimeoutExpired,
            OSError,
        ):
            return False

        return result.returncode == 0


def _wine_supports_wow64(wine_binary: str) -> bool:
    """Detect whether the installed Wine provides WoW64 support.

    This performs no Wine prefix initialization and does not launch
    a Windows application.
    """

    wine_path = Path(wine_binary).resolve()

    # Typical Wine installations have wine and wine64 loaders.
    wine64_candidates = [
        wine_path.parent / "wine64",
        wine_path.parent.parent / "bin" / "wine64",
    ]

    for candidate in wine64_candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return True

    # Some modern Wine installations use a unified loader and don't
    # expose a separate wine64 executable. In that case, inspect the
    # Wine installation for the WoW64 loader directory.
    wine_root = wine_path.parent.parent

    wow64_directories = [
        wine_root / "lib" / "wine" / "x86_64-windows",
        wine_root / "lib64" / "wine" / "x86_64-windows",
    ]

    return any(
        directory.is_dir()
        for directory in wow64_directories
    )


def detect_host(executable: ExecutableInfo,) -> HostInfo:
    """Detect relevant Linux host capabilities."""

    architecture = platform.machine()

    wine_binary = shutil.which("wine")

    wine_installed = wine_binary is not None

    wine_version = None
    wine_32bit_prefix = False

    if wine_binary:

        try:
            result = subprocess.run(
                [
                    wine_binary,
                    "--version",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                wine_version = result.stdout.strip()

        except (
            subprocess.TimeoutExpired,
            OSError,
        ):
            pass
        
        if executable.architecture == "x86":

            wine_32bit_prefix = _wine_supports_32bit_prefix(
                wine_binary
            )

            wine_wow64 = _wine_supports_wow64(
                wine_binary
            )

    winetricks_installed = (
        shutil.which("winetricks") is not None
    )
 
    return HostInfo(
        architecture=architecture,
        wine_installed=wine_installed,
        wine_version=wine_version,
        wine_32bit_prefix=wine_32bit_prefix,
        wine_wow64=wine_wow64,
        winetricks_installed=winetricks_installed,
    )