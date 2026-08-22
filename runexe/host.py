import platform
import shutil
import subprocess

from .models import HostInfo


def detect_host() -> HostInfo:
    architecture = platform.machine().lower()

    wine_path = shutil.which("wine")
    winetricks_path = shutil.which("winetricks")

    wine_version = None

    if wine_path:
        try:
            result = subprocess.run(
                [wine_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                wine_version = result.stdout.strip()

        except (subprocess.SubprocessError, OSError):
            pass

    return HostInfo(
        architecture=architecture,
        wine_installed=wine_path is not None,
        wine_path=wine_path,
        wine_version=wine_version,
        winetricks_installed=winetricks_path is not None,
    )