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
from .pe_utils import run_with_progress


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


def _verbose(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[runexe] {message}")


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        hints = {
            "wine": "sudo apt install wine (Ubuntu/Debian) or sudo dnf install wine (Fedora)",
            "winetricks": "sudo apt install winetricks (Ubuntu/Debian) or sudo dnf install winetricks (Fedora)",
        }
        hint = hints.get(name, f"Install {name} using your package manager")
        raise RunnerError(f"'{name}' not found. {hint}")
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


def ensure_prefix(
    prefix: Path,
    wine_arch: str,
    verbose: bool = False,
) -> None:
    """Create and initialize the Wine prefix if needed."""

    prefix_ready = (prefix / "drive_c").is_dir()

    if prefix_ready:
        _verbose(verbose, f"Reusing Wine prefix: {prefix}")
        return

    wine_binary = _require_binary("wine")

    prefix.mkdir(parents=True, exist_ok=True)

    command = [
        wine_binary,
        "wineboot",
        "--init",
    ]

    try:
        result = run_with_progress(
            command,
            env=_wine_env(prefix, wine_arch),
            description="Creating Wine prefix",
            timeout=PREFIX_INIT_TIMEOUT,
            verbose=verbose,
        )

    except subprocess.TimeoutExpired as error:
        raise RunnerError(
            f"Timed out initializing the Wine prefix at {prefix}."
        ) from error

    if result.returncode != 0:
        raise RunnerError(
            f"Wine prefix initialization failed with "
            f"exit code {result.returncode}."
        )

    if not (prefix / "drive_c").is_dir():
        raise RunnerError(
            f"Wine prefix initialization completed, but the prefix "
            f"appears incomplete: {prefix}"
        )


def install_verbs(
    prefix: Path,
    verbs: list[str],
    verbose: bool = False,
) -> set[str]:
    """Install the given winetricks verbs into prefix.

    Skips verbs already recorded as installed.
    Returns the full set of installed verbs.
    """

    marker = _installed_verbs_marker(prefix)

    already_installed = (
        set(marker.read_text().split())
        if marker.exists()
        else set()
    )

    to_install = [
        verb
        for verb in verbs
        if verb not in already_installed
    ]

    if not to_install:
        if verbose:
            print(
                "[runexe] Required dependencies are already installed."
            )

        return already_installed

    winetricks_binary = _require_binary("winetricks")

    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env.setdefault("WINEDEBUG", "-all")

    command = [
        winetricks_binary,
        "--unattended",
        *to_install,
    ]

    try:
        result = run_with_progress(
            command,
            env=env,
            description=(
                f"Installing dependencies: "
                f"{', '.join(to_install)}"
            ),
            timeout=WINETRICKS_TIMEOUT,
            verbose=verbose,
        )

    except subprocess.TimeoutExpired as error:
        raise RunnerError(
            f"Timed out installing winetricks verbs: "
            f"{', '.join(to_install)}."
        ) from error

    if result.returncode != 0:
        raise RunnerError(
            f"Winetricks failed with exit code "
            f"{result.returncode}."
        )

    updated = already_installed | set(to_install)

    marker.write_text(
        " ".join(sorted(updated))
    )

    return updated


def launch(
    executable: ExecutableInfo,
    compatibility: CompatibilityReport,
    extra_args: list[str] | None = None,
    timeout: int | None = None,
    verbose: bool = False,
) -> LaunchResult:
    """Provision the prefix and run the executable under Wine."""

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
        raise RunnerError(
            f"Executable not found: {executable.path}"
        )

    wine_arch = compatibility.wine_arch or "win64"
    prefix = prefix_path_for(executable)

    _verbose(verbose, "Preparing launch...")
    _verbose(
        verbose,
        f"Executable: {executable.path.resolve()}",
    )
    _verbose(
        verbose,
        f"Executable architecture: {compatibility.architecture}",
    )
    _verbose(
        verbose,
        f"Backend: {compatibility.backend}",
    )
    _verbose(
        verbose,
        f"Wine architecture: {wine_arch}",
    )
    _verbose(
        verbose,
        f"Wine prefix: {prefix}",
    )

    ensure_prefix(
        prefix,
        wine_arch,
        verbose=verbose,
    )

    if compatibility.required_verbs:
        install_verbs(
            prefix,
            compatibility.required_verbs,
            verbose=verbose,
        )

    wine_binary = _require_binary("wine")

    command = [
        wine_binary,
        str(executable.path),
        *(extra_args or []),
    ]

    _verbose(verbose, f"Wine binary: {wine_binary}")
    _verbose(verbose, f"Command: {' '.join(command)}")

    if timeout is not None:
        _verbose(
            verbose,
            f"Launch timeout: {timeout} seconds",
        )
    else:
        _verbose(verbose, "Launch timeout: none")

    try:
        completed = subprocess.run(
            command,
            env=_wine_env(prefix, wine_arch),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired as error:
        _verbose(verbose, "Process timed out.")

        return LaunchResult(
            exit_code=None,
            stdout=error.stdout or "",
            stderr=error.stderr or "",
            timed_out=True,
        )

    _verbose(
        verbose,
        f"Process exited with code {completed.returncode}",
    )

    return LaunchResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )