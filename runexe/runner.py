"""Provision isolated Wine or Proton environments and launch Windows software."""

import hashlib
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import CompatibilityReport, ExecutableInfo
from .pe_utils import run_with_progress
from .proton import (
    ProtonError,
    ProtonInstallation,
    compat_data_path_for,
    proton_environment,
    proton_winetricks_environment,
    select_proton,
)

RUNEXE_DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "runexe"
PREFIXES_DIR = RUNEXE_DATA_DIR / "prefixes"

# Winetricks / wineboot can hang waiting on a dialog that will never
# be answered in a headless run; bound both steps rather than blocking
# forever.
PREFIX_INIT_TIMEOUT = 120
WINETRICKS_TIMEOUT = 600
PROTON_INIT_TIMEOUT = 180


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
            "winetricks": (
                "sudo apt install winetricks (Ubuntu/Debian) or "
                "sudo dnf install winetricks (Fedora)"
            ),
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
    slug = re.sub(r"[^a-z0-9._-]+", "_", executable.path.stem.lower()).strip("._-") or "app"

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


def _wine_tool_command(name: str) -> list[str]:
    """Prefer Wine's native helper, with a loader fallback."""

    helper = shutil.which(name)
    if helper:
        return [helper]
    return [_require_binary("wine"), name]


def _existing_prefix_arch(prefix: Path) -> str | None:
    marker = prefix / ".runexe-winearch"
    if marker.is_file():
        return marker.read_text(encoding="utf-8", errors="replace").strip() or None
    system_reg = prefix / "system.reg"
    if system_reg.is_file():
        try:
            with system_reg.open(encoding="utf-8", errors="replace") as file:
                first_line = file.readline()
        except OSError:
            return None
        match = re.search(r"#arch=(win32|win64)", first_line)
        return match.group(1) if match else None
    return None


def ensure_prefix(
    prefix: Path,
    wine_arch: str,
    verbose: bool = False,
) -> None:
    """Create and initialize the Wine prefix if needed."""

    prefix_ready = (prefix / "drive_c").is_dir()

    if prefix_ready:
        existing_arch = _existing_prefix_arch(prefix)
        if existing_arch and existing_arch != wine_arch:
            raise RunnerError(
                f"Existing prefix at {prefix} uses {existing_arch}, but this "
                f"executable requires {wine_arch}."
            )
        _verbose(verbose, f"Reusing Wine prefix: {prefix}")
        return

    prefix.mkdir(parents=True, exist_ok=True)

    command = [*_wine_tool_command("wineboot"), "--init"]

    try:
        result = run_with_progress(
            command,
            env=_wine_env(prefix, wine_arch),
            description="Creating Wine prefix",
            timeout=PREFIX_INIT_TIMEOUT,
            verbose=verbose,
        )

    except subprocess.TimeoutExpired as error:
        raise RunnerError(f"Timed out initializing the Wine prefix at {prefix}.") from error

    if result.returncode != 0:
        raise RunnerError(f"Wine prefix initialization failed with exit code {result.returncode}.")

    if not (prefix / "drive_c").is_dir():
        raise RunnerError(
            f"Wine prefix initialization completed, but the prefix appears incomplete: {prefix}"
        )

    (prefix / ".runexe-winearch").write_text(wine_arch + "\n", encoding="utf-8")


def set_windows_version(
    prefix: Path,
    wine_arch: str,
    winver: str,
    verbose: bool = False,
) -> None:
    """Set the Windows version reported by Wine for this prefix."""

    supported_versions = {
        "7": "win7",
        "8": "win8",
        "8.1": "win81",
        "10": "win10",
        "11": "win11",
    }

    normalized = winver.lower().removeprefix("win")
    wine_version = supported_versions.get(normalized)

    if wine_version is None:
        raise RunnerError(
            f"Unsupported Windows version '{winver}'. "
            f"Supported versions: 7, 8, 8.1, 10, 11 (or win10-style names)"
        )

    command = [
        *_wine_tool_command("winecfg"),
        "-v",
        wine_version,
    ]

    _verbose(
        verbose,
        f"Setting Wine Windows version: Windows {winver}",
    )

    try:
        result = run_with_progress(
            command,
            env=_wine_env(prefix, wine_arch),
            description=f"Configuring Wine for Windows {winver}",
            timeout=60,
            verbose=verbose,
        )
    except subprocess.TimeoutExpired as error:
        raise RunnerError(f"Timed out configuring Wine Windows version to {winver}.") from error

    if result.returncode != 0:
        raise RunnerError(
            f"Failed to configure Wine Windows version to {winver} (exit code {result.returncode})."
        )


def install_verbs(
    prefix: Path,
    verbs: list[str],
    verbose: bool = False,
    wine_arch: str | None = None,
    env_override: dict[str, str] | None = None,
) -> set[str]:
    """Install the given winetricks verbs into prefix.

    Skips verbs already recorded as installed.
    Returns the full set of installed verbs.
    """

    marker = _installed_verbs_marker(prefix)

    already_installed = (
        set(marker.read_text(encoding="utf-8").split()) if marker.exists() else set()
    )

    to_install = [verb for verb in verbs if verb not in already_installed]

    if not to_install:
        if verbose:
            print("[runexe] Required dependencies are already installed.")

        return already_installed

    winetricks_binary = _require_binary("winetricks")

    env = env_override.copy() if env_override is not None else os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    if wine_arch and env_override is None:
        env["WINEARCH"] = wine_arch
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
            description=(f"Installing dependencies: {', '.join(to_install)}"),
            timeout=WINETRICKS_TIMEOUT,
            verbose=verbose,
        )

    except subprocess.TimeoutExpired as error:
        raise RunnerError(
            f"Timed out installing winetricks verbs: {', '.join(to_install)}."
        ) from error

    if result.returncode != 0:
        raise RunnerError(f"Winetricks failed with exit code {result.returncode}.")

    updated = already_installed | set(to_install)

    temporary_marker = marker.with_suffix(".tmp")
    temporary_marker.write_text(" ".join(sorted(updated)) + "\n", encoding="utf-8")
    temporary_marker.replace(marker)

    return updated


def ensure_proton_prefix(
    installation: ProtonInstallation,
    compat_data: Path,
    executable: Path,
    verbose: bool = False,
) -> None:
    """Initialize an isolated Proton compat-data directory once."""

    prefix = compat_data / "pfx"
    if (prefix / "drive_c").is_dir():
        _verbose(verbose, f"Reusing Proton compat data: {compat_data}")
        return

    compat_data.mkdir(parents=True, exist_ok=True)
    command = [str(installation.script), "run", "cmd.exe", "/c", "exit"]
    try:
        result = run_with_progress(
            command,
            env=proton_environment(installation, compat_data, executable),
            description=f"Initializing {installation.name}",
            timeout=PROTON_INIT_TIMEOUT,
            verbose=verbose,
        )
    except subprocess.TimeoutExpired as error:
        raise RunnerError(f"Timed out initializing Proton compat data at {compat_data}.") from error

    if result.returncode != 0 or not (prefix / "drive_c").is_dir():
        raise RunnerError(
            f"{installation.name} could not initialize compat data at {compat_data} "
            f"(exit code {result.returncode})."
        )
    (compat_data / ".runexe-proton").write_text(
        f"{installation.script}\n{installation.version or installation.name}\n",
        encoding="utf-8",
    )


def set_proton_windows_version(
    installation: ProtonInstallation,
    compat_data: Path,
    executable: Path,
    winver: str,
    verbose: bool = False,
) -> None:
    supported = {"7": "win7", "8": "win8", "8.1": "win81", "10": "win10", "11": "win11"}
    normalized = winver.lower().removeprefix("win")
    selected = supported.get(normalized)
    if selected is None:
        raise RunnerError(
            f"Unsupported Windows version '{winver}'. Supported versions: 7, 8, 8.1, 10, 11."
        )
    command = [str(installation.script), "runinprefix", "winecfg", "-v", selected]
    try:
        result = run_with_progress(
            command,
            env=proton_environment(installation, compat_data, executable),
            description=f"Configuring Proton for Windows {normalized}",
            timeout=60,
            verbose=verbose,
        )
    except subprocess.TimeoutExpired as error:
        raise RunnerError(f"Timed out configuring Proton for Windows {normalized}.") from error
    if result.returncode != 0:
        raise RunnerError(f"Could not configure Proton for Windows {normalized}.")


def _execute_launch(
    command: list[str],
    executable_path: Path,
    env: dict[str, str],
    timeout: int | None,
    verbose: bool,
) -> LaunchResult:
    _verbose(verbose, f"Command: {shlex.join(command)}")
    try:
        completed = subprocess.run(
            command,
            cwd=executable_path.parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return LaunchResult(
            exit_code=None,
            stdout=(error.stdout or "").decode(errors="replace")
            if isinstance(error.stdout, bytes)
            else (error.stdout or ""),
            stderr=(error.stderr or "").decode(errors="replace")
            if isinstance(error.stderr, bytes)
            else (error.stderr or ""),
            timed_out=True,
        )
    except OSError as error:
        raise RunnerError(f"Could not start compatibility runtime: {error}") from error
    return LaunchResult(completed.returncode, completed.stdout, completed.stderr)


def _launch_proton(
    executable: ExecutableInfo,
    compatibility: CompatibilityReport,
    *,
    selector: str | Path | None,
    extra_args: list[str] | None,
    timeout: int | None,
    verbose: bool,
    winver: str | None,
    compat_data: Path | None,
    install_dependencies: bool,
) -> LaunchResult:
    try:
        installation = select_proton(selector)
    except ProtonError as error:
        raise RunnerError(str(error)) from error

    executable_path = executable.path.resolve()
    data_path = (
        compat_data.expanduser().resolve()
        if compat_data is not None
        else compat_data_path_for(executable_path)
    )
    if install_dependencies and compatibility.required_verbs:
        _require_binary("winetricks")

    _verbose(verbose, f"Backend: Proton ({installation.name})")
    _verbose(verbose, f"Proton script: {installation.script}")
    _verbose(verbose, f"Compat data: {data_path}")
    ensure_proton_prefix(installation, data_path, executable_path, verbose)

    if install_dependencies and compatibility.required_verbs:
        try:
            proton_wine_env = proton_winetricks_environment(installation, data_path)
        except ProtonError as error:
            raise RunnerError(str(error)) from error
        install_verbs(
            data_path / "pfx",
            compatibility.required_verbs,
            verbose=verbose,
            env_override=proton_wine_env,
        )
    if winver is not None:
        set_proton_windows_version(installation, data_path, executable_path, winver, verbose)

    command = [str(installation.script), "run", str(executable_path), *(extra_args or [])]
    return _execute_launch(
        command,
        executable_path,
        proton_environment(installation, data_path, executable_path),
        timeout,
        verbose,
    )


def launch(
    executable: ExecutableInfo,
    compatibility: CompatibilityReport,
    extra_args: list[str] | None = None,
    timeout: int | None = None,
    verbose: bool = False,
    winver: str | None = None,
    prefix: Path | None = None,
    install_dependencies: bool = True,
    proton: str | Path | None = None,
) -> LaunchResult:
    """Provision an isolated Wine/Proton environment and launch the executable."""

    if compatibility.backend == "unsupported":
        raise RunnerError(f"{compatibility.architecture} is not supported by Wine/Proton.")

    if compatibility.blocking_issues:
        raise RunnerError("Refusing to auto-launch: " + "; ".join(compatibility.blocking_issues))

    if not executable.path.exists():
        raise RunnerError(f"Executable not found: {executable.path}")

    if timeout is not None and timeout <= 0:
        raise RunnerError("Timeout must be greater than zero seconds.")

    if compatibility.backend == "proton":
        return _launch_proton(
            executable,
            compatibility,
            selector=proton,
            extra_args=extra_args,
            timeout=timeout,
            verbose=verbose,
            winver=winver,
            compat_data=prefix,
            install_dependencies=install_dependencies,
        )

    wine_arch = compatibility.wine_arch
    if wine_arch is None:
        raise RunnerError("No compatible Wine prefix architecture was found.")
    prefix = prefix.expanduser().resolve() if prefix is not None else prefix_path_for(executable)

    # Fail before making a prefix if required tools are missing.
    wine_binary = _require_binary("wine")
    if install_dependencies and compatibility.required_verbs:
        _require_binary("winetricks")

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

    if install_dependencies and compatibility.required_verbs:
        install_verbs(
            prefix,
            compatibility.required_verbs,
            verbose=verbose,
            wine_arch=wine_arch,
        )

    # Some Winetricks verbs temporarily change the reported Windows
    # version, so apply the explicit user override after provisioning.
    if winver is not None:
        set_windows_version(prefix, wine_arch, winver, verbose=verbose)

    executable_path = executable.path.resolve()
    command = [
        wine_binary,
        str(executable_path),
        *(extra_args or []),
    ]

    _verbose(verbose, f"Wine binary: {wine_binary}")

    if timeout is not None:
        _verbose(
            verbose,
            f"Launch timeout: {timeout} seconds",
        )
    else:
        _verbose(verbose, "Launch timeout: none")

    return _execute_launch(command, executable_path, _wine_env(prefix, wine_arch), timeout, verbose)
