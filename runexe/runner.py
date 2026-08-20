"""Executable launching: Wine prefix creation, winetricks dependency
installation, and running the target .exe with output capture.

Only the "wine" backend is implemented here. Proton launches work
differently -- a different binary, Steam runtime environment variables
(STEAM_COMPAT_DATA_PATH, STEAM_COMPAT_CLIENT_INSTALL_PATH) instead of
WINEPREFIX/WINEARCH -- and are intentionally left for a follow-up
rather than half-implemented alongside this.
"""

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import CompatibilityReport, ExecutableInfo


RUNEXE_DATA_DIR = Path.home() / ".local" / "share" / "runexe"
PREFIXES_DIR = RUNEXE_DATA_DIR / "prefixes"

# Winetricks / wineboot can hang waiting on a dialog that will never
# be answered in a headless run; bound both steps rather than blocking
# forever.
PREFIX_INIT_TIMEOUT = 120
WINETRICKS_TIMEOUT = 600


class RunnerError(Exception):
    """Setup failure: missing binaries, blocked launch, bad backend."""


@dataclass
class LaunchResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


def _require_binary(name: str) -> str:
    path = shutil.which(name)

    if path is None:
        raise RunnerError(
            f"'{name}' was not found on PATH. Install it and try again."
        )

    return path


def prefix_path_for(executable: ExecutableInfo) -> Path:
    """Return a stable, per-app prefix directory.

    Keyed on the executable's filename plus a short hash of its
    resolved path, so re-running the same file reuses its prefix while
    different files that happen to share a filename don't collide.
    """

    resolved = str(executable.path.resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:10]
    slug = executable.path.stem.lower().replace(" ", "_") or "app"

    return PREFIXES_DIR / f"{slug}-{digest}"


def _installed_verbs_marker(prefix: Path) -> Path:
    return prefix / ".runexe-installed-verbs"


def _wine_env(prefix: Path, wine_arch: str) -> dict:
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["WINEARCH"] = wine_arch
    # Quiet Wine's own logging; we care about the target app's stderr,
    # not Wine's internal debug channel noise.
    env.setdefault("WINEDEBUG", "-all")
    return env


def ensure_prefix(prefix: Path, wine_arch: str) -> None:
    """Create and boot the Wine prefix if it doesn't already exist.

    Safe to call on every launch -- it's a no-op once the prefix
    directory is already present.
    """

    if prefix.exists():
        return

    wine_binary = _require_binary("wine")

    prefix.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [wine_binary, "wineboot", "--init"],
            env=_wine_env(prefix, wine_arch),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PREFIX_INIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as error:
        raise RunnerError(
            f"Timed out initializing the Wine prefix at {prefix}."
        ) from error


def install_verbs(prefix: Path, verbs: list[str]) -> set[str]:
    """Install the given winetricks verbs into `prefix`, skipping any
    already recorded as installed for it.

    Returns the full set of verbs now installed (previously-installed
    plus newly-installed).
    """

    marker = _installed_verbs_marker(prefix)
    already_installed = (
        set(marker.read_text().split()) if marker.exists() else set()
    )

    to_install = [verb for verb in verbs if verb not in already_installed]

    if not to_install:
        return already_installed

    winetricks_binary = _require_binary("winetricks")

    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env.setdefault("WINEDEBUG", "-all")

    try:
        subprocess.run(
            [winetricks_binary, "--unattended", *to_install],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=WINETRICKS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as error:
        raise RunnerError(
            f"Timed out installing winetricks verbs: {', '.join(to_install)}."
        ) from error

    updated = already_installed | set(to_install)
    marker.write_text(" ".join(sorted(updated)))

    return updated


def launch(
    executable: ExecutableInfo,
    compatibility: CompatibilityReport,
    extra_args: list[str] | None = None,
    timeout: int | None = None,
) -> LaunchResult:
    """Provision the prefix (creating it and installing dependencies
    as needed) and run the executable under Wine, capturing output.

    Raises RunnerError for setup problems (unsupported architecture,
    a detected anti-cheat blocker, a missing `wine`/`winetricks`
    binary) rather than attempting a launch that can't succeed.
    """

    if compatibility.backend == "unsupported":
        raise RunnerError(
            f"{compatibility.architecture} is not supported by "
            f"Wine/Proton."
        )

    if compatibility.backend == "proton":
        raise NotImplementedError(
            "Proton launches aren't implemented yet -- this build "
            "only drives plain Wine."
        )

    if compatibility.blocking_issues:
        raise RunnerError(
            "Refusing to auto-launch: "
            + "; ".join(compatibility.blocking_issues)
        )

    if not executable.path.exists():
        raise RunnerError(f"Executable not found: {executable.path}")

    wine_arch = compatibility.wine_arch or "win64"
    prefix = prefix_path_for(executable)

    ensure_prefix(prefix, wine_arch)

    if compatibility.required_verbs:
        install_verbs(prefix, compatibility.required_verbs)

    wine_binary = _require_binary("wine")
    command = [wine_binary, str(executable.path), *(extra_args or [])]

    try:
        completed = subprocess.run(
            command,
            env=_wine_env(prefix, wine_arch),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return LaunchResult(
            exit_code=None,
            stdout=error.stdout or "",
            stderr=error.stderr or "",
            timed_out=True,
        )

    return LaunchResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )