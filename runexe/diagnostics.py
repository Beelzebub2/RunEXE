"""Distro-aware, read-only diagnostics for RunEXE installations."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .graphics import probe_vulkan
from .platform_support import (
    LinuxDistribution,
    detect_libc,
    detect_linux_distribution,
    detect_package_manager,
    find_executable,
    install_hint,
)
from .proton import discover_proton_installations


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    detail: str
    fix: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    system: str
    distribution: LinuxDistribution
    architecture: str
    libc: str
    package_manager: str | None
    checks: tuple[DiagnosticCheck, ...]

    @property
    def ready(self) -> bool:
        return not any(check.status == "error" for check in self.checks)

    def as_dict(self) -> dict:
        result = asdict(self)
        result["ready"] = self.ready
        return result


def _runtime_version(binary: str) -> str | None:
    try:
        result = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=8, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0] or None


def _qt_platform_plugins() -> tuple[Path | None, tuple[str, ...]]:
    try:
        spec = importlib.util.find_spec("PySide6")
    except (ImportError, ModuleNotFoundError, ValueError):
        return None, ()
    if spec is None or not spec.submodule_search_locations:
        return None, ()
    package = Path(next(iter(spec.submodule_search_locations)))
    plugin_dir = next(
        (
            candidate
            for candidate in (
                package / "plugins" / "platforms",
                package / "Qt" / "plugins" / "platforms",
            )
            if candidate.is_dir()
        ),
        package / "plugins" / "platforms",
    )
    if not plugin_dir.is_dir():
        return plugin_dir, ()
    names = tuple(sorted(path.name for path in plugin_dir.iterdir() if path.is_file()))
    return plugin_dir, names


def _missing_plugin_libraries(plugin_dir: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    if platform.system() != "Linux":
        return ()
    ldd = shutil.which("ldd")
    if not ldd:
        return ()
    candidates = [
        plugin_dir / name
        for name in names
        if name in {"libqxcb.so", "libqwayland-generic.so", "libqwayland-egl.so"}
    ]
    missing: set[str] = set()
    for plugin in candidates:
        try:
            result = subprocess.run(
                [ldd, str(plugin)], capture_output=True, text=True, timeout=8, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in f"{result.stdout}\n{result.stderr}".splitlines():
            if "not found" in line.lower():
                missing.add(line.strip().split()[0])
    return tuple(sorted(missing))


def collect_diagnostics(include_gui: bool = True) -> DoctorReport:
    """Inspect the host without creating Wine prefixes or changing packages."""

    system = platform.system()
    distribution = detect_linux_distribution()
    architecture = platform.machine() or "unknown"
    libc_name, libc_version = detect_libc()
    libc_label = f"{libc_name} {libc_version}".strip() if libc_version else libc_name
    package_manager = detect_package_manager(distribution)
    checks: list[DiagnosticCheck] = []

    if system == "Linux":
        checks.append(DiagnosticCheck("Operating system", "ok", distribution.pretty_name))
    else:
        checks.append(
            DiagnosticCheck(
                "Operating system",
                "error",
                f"{system} is not a supported execution host",
                "Run RunEXE on Linux; static analysis remains portable.",
            )
        )

    python_ok = sys.version_info >= (3, 10)
    checks.append(
        DiagnosticCheck(
            "Python",
            "ok" if python_ok else "error",
            platform.python_version(),
            None if python_ok else "Install Python 3.10 or newer.",
        )
    )

    normalized_arch = architecture.lower().replace("amd64", "x86_64")
    checks.append(
        DiagnosticCheck(
            "Host architecture",
            "ok" if normalized_arch in {"x86_64", "x86", "i386", "i686"} else "warning",
            architecture,
            None
            if normalized_arch in {"x86_64", "x86", "i386", "i686"}
            else "The current runtime backend only launches x86/x86_64 Windows applications.",
        )
    )
    checks.append(DiagnosticCheck("C library", "ok", libc_label))

    wine = find_executable("wine")
    proton = discover_proton_installations()
    if wine:
        version = _runtime_version(wine)
        checks.append(DiagnosticCheck("Wine", "ok", f"{version or 'detected'} ({wine})"))
    else:
        checks.append(
            DiagnosticCheck("Wine", "warning", "not found", install_hint("wine", distribution))
        )
    checks.append(
        DiagnosticCheck(
            "Proton",
            "ok" if proton else "warning",
            ", ".join(item.name for item in proton) if proton else "not found",
            None if proton else "Install Proton through Steam or set RUNEXE_PROTON_PATH.",
        )
    )
    if not wine and not proton:
        checks.append(
            DiagnosticCheck(
                "Launch runtime",
                "error",
                "neither Wine nor Proton is available",
                install_hint("wine", distribution),
            )
        )

    winetricks = find_executable("winetricks")
    checks.append(
        DiagnosticCheck(
            "Winetricks",
            "ok" if winetricks else "warning",
            winetricks or "not found (automatic dependency setup disabled)",
            None if winetricks else install_hint("winetricks", distribution),
        )
    )

    vulkan = probe_vulkan()
    if vulkan.available:
        devices = ", ".join(vulkan.devices) or "a Vulkan-capable device"
        version = f"; Vulkan {vulkan.version}" if vulkan.version else ""
        checks.append(DiagnosticCheck("Vulkan/GPU", "ok", f"{devices}{version}"))
    elif vulkan.available is False:
        checks.append(
            DiagnosticCheck(
                "Vulkan/GPU",
                "warning",
                vulkan.error or "Vulkan initialization failed",
                "Check the GPU driver and 32/64-bit Vulkan ICD packages.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                "Vulkan/GPU",
                "warning",
                "readiness unknown because vulkaninfo is unavailable",
                install_hint("vulkan", distribution),
            )
        )

    if include_gui:
        display = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")
        explicit_platform = os.environ.get("QT_QPA_PLATFORM") or os.environ.get(
            "RUNEXE_QT_PLATFORM"
        )
        headless_platform = explicit_platform and explicit_platform.split(";", 1)[0] in {
            "offscreen",
            "minimal",
            "linuxfb",
            "eglfs",
            "vnc",
        }
        checks.append(
            DiagnosticCheck(
                "Graphical session",
                "ok" if display or headless_platform else "warning",
                explicit_platform or display or "no Wayland or X11 display detected",
                None
                if display or headless_platform
                else "Start the GUI inside a desktop session; the console UI still works.",
            )
        )
        plugin_dir, plugins = _qt_platform_plugins()
        if plugin_dir is None:
            checks.append(
                DiagnosticCheck(
                    "Desktop GUI",
                    "warning",
                    "PySide6 is not installed",
                    "python -m pip install 'runexe[gui]'",
                )
            )
        elif not plugins:
            checks.append(
                DiagnosticCheck(
                    "Qt platform plugins",
                    "warning",
                    f"none found in {plugin_dir}",
                    "Reinstall the GUI extra and run this command again.",
                )
            )
        else:
            missing = _missing_plugin_libraries(plugin_dir, plugins)
            checks.append(
                DiagnosticCheck(
                    "Qt platform plugins",
                    "warning" if missing else "ok",
                    "missing shared libraries: " + ", ".join(missing)
                    if missing
                    else f"{len(plugins)} available in {plugin_dir}",
                    install_hint("gui", distribution) if missing else None,
                )
            )

    return DoctorReport(
        system,
        distribution,
        architecture,
        libc_label,
        package_manager,
        tuple(checks),
    )
