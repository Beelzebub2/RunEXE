"""Read-only GPU and Vulkan capability detection.

DXVK and VKD3D-Proton -- the Direct3D-over-Vulkan translation layers used
by both Wine and Proton -- need a working hardware Vulkan driver. This
module discovers what is actually installed (DRM render nodes, Vulkan ICD
manifests, the Vulkan loader) without querying the GPU, creating a Wine
prefix, or changing any host state, so it is safe to call from `runexe
doctor`, host detection, and the GUI on every platform.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .platform_support import find_executable

# Vendor id -> family, as assigned by the PCI-SIG and exposed verbatim by
# the kernel under /sys/class/drm/*/device/vendor.
_PCI_VENDOR_NAMES: dict[str, str] = {
    "0x10de": "nvidia",
    "0x1002": "amd",
    "0x1022": "amd",
    "0x8086": "intel",
}

# Substrings found in Vulkan ICD manifest filenames/library paths that
# reliably identify the driver family. Order matters: "software" is
# checked first since lavapipe/llvmpipe manifests can otherwise look
# generic.
_VENDOR_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("software", ("lvp", "llvmpipe", "swrast", "lavapipe")),
    ("nvidia", ("nvidia",)),
    ("amd", ("radeon", "radv", "amdvlk", "amdgpu")),
    ("intel", ("intel", "anv")),
)

_LIBVULKAN_DIRS = (
    Path("/usr/lib"),
    Path("/usr/lib64"),
    Path("/usr/lib/x86_64-linux-gnu"),
    Path("/usr/lib/i386-linux-gnu"),
    Path("/usr/lib/aarch64-linux-gnu"),
    Path("/usr/local/lib"),
    Path("/lib"),
    Path("/lib64"),
)


@dataclass(frozen=True)
class GraphicsAdapter:
    """A GPU exposed through a kernel DRM render node."""

    render_node: Path
    # PCI vendor family: "nvidia", "amd", "intel", or "unknown".
    vendor: str
    # Kernel driver module bound to the device (e.g. "amdgpu", "i915",
    # "nvidia", "nouveau"), when the sysfs symlink is readable.
    driver: str | None = None


@dataclass(frozen=True)
class VulkanIcd:
    """One installed Vulkan Installable Client Driver manifest."""

    path: Path
    library_path: str | None
    api_version: str | None
    # "nvidia", "amd", "intel", "software" (lavapipe/llvmpipe), or "unknown".
    vendor: str


@dataclass(frozen=True)
class GpuInfo:
    """Read-only snapshot of the host's GPU and Vulkan capabilities."""

    adapters: tuple[GraphicsAdapter, ...] = ()
    vulkan_icds: tuple[VulkanIcd, ...] = ()
    vulkan_loader_installed: bool = False
    vulkaninfo_path: str | None = None

    @property
    def hardware_vulkan_icds(self) -> tuple[VulkanIcd, ...]:
        return tuple(icd for icd in self.vulkan_icds if icd.vendor != "software")

    @property
    def vulkan_supported(self) -> bool:
        """True when a hardware-backed Vulkan ICD is loadable.

        A software-only renderer (lavapipe/llvmpipe) is deliberately not
        enough here: DXVK and VKD3D-Proton will load it, but performance
        is generally too poor for real use, so callers should still warn.
        """

        return self.vulkan_loader_installed and bool(self.hardware_vulkan_icds)

    @property
    def gpu_vendors(self) -> tuple[str, ...]:
        vendors = {adapter.vendor for adapter in self.adapters if adapter.vendor != "unknown"}
        return tuple(sorted(vendors))


def _read_first_line(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
        return None


def discover_graphics_adapters(root: Path = Path("/sys/class/drm")) -> tuple[GraphicsAdapter, ...]:
    """Enumerate DRM render nodes and their PCI vendor/driver, read-only."""

    if not root.is_dir():
        return ()

    adapters: list[GraphicsAdapter] = []
    for node in sorted(root.glob("renderD*")):
        device_dir = node / "device"
        vendor_id = (_read_first_line(device_dir / "vendor") or "").lower()
        vendor = _PCI_VENDOR_NAMES.get(vendor_id, "unknown")
        driver_link = device_dir / "driver"
        driver = driver_link.resolve().name if driver_link.is_symlink() else None
        adapters.append(
            GraphicsAdapter(
                render_node=Path("/dev/dri") / node.name,
                vendor=vendor,
                driver=driver,
            )
        )
    return tuple(adapters)


def _default_icd_dirs() -> list[Path]:
    dirs = [
        Path("/usr/local/share/vulkan/icd.d"),
        Path("/usr/share/vulkan/icd.d"),
        Path("/etc/vulkan/icd.d"),
    ]
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    dirs.extend(
        Path(entry) / "vulkan" / "icd.d" for entry in xdg_data_dirs.split(os.pathsep) if entry
    )
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    dirs.append(Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share")
    dirs[-1] = dirs[-1] / "vulkan" / "icd.d"
    return dirs


def _icd_override_files() -> list[Path]:
    # VK_DRIVER_FILES is the current Khronos loader name; VK_ICD_FILENAMES
    # is the older alias that some distributions and users still set.
    raw = os.environ.get("VK_DRIVER_FILES") or os.environ.get("VK_ICD_FILENAMES") or ""
    return [Path(entry).expanduser() for entry in raw.split(os.pathsep) if entry]


def _vendor_from_icd(path: Path, library_path: str | None) -> str:
    haystack = f"{path.name} {library_path or ''}".lower()
    for vendor, hints in _VENDOR_HINTS:
        if any(hint in haystack for hint in hints):
            return vendor
    return "unknown"


def _read_icd(path: Path) -> VulkanIcd | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    icd = data.get("ICD") if isinstance(data, dict) else None
    if not isinstance(icd, dict):
        return None
    library_path = icd.get("library_path")
    library_path = library_path if isinstance(library_path, str) else None
    api_version = icd.get("api_version")
    return VulkanIcd(
        path=path,
        library_path=library_path,
        api_version=api_version if isinstance(api_version, str) else None,
        vendor=_vendor_from_icd(path, library_path),
    )


def discover_vulkan_icds() -> tuple[VulkanIcd, ...]:
    """Find installed Vulkan ICD manifests without querying the loader."""

    candidates = list(_icd_override_files())
    for directory in _default_icd_dirs():
        if directory.is_dir():
            candidates.extend(sorted(directory.glob("*.json")))

    found: dict[Path, VulkanIcd] = {}
    for candidate in candidates:
        resolved = candidate.expanduser()
        if resolved in found or not resolved.is_file():
            continue
        icd = _read_icd(resolved)
        if icd is not None:
            found[resolved] = icd
    return tuple(found.values())


def _vulkan_loader_installed() -> bool:
    """Detect libvulkan.so without assuming a particular distro layout."""

    ldconfig = shutil.which("ldconfig")
    if ldconfig:
        try:
            result = subprocess.run(
                [ldconfig, "-p"], capture_output=True, text=True, timeout=8, check=False
            )
            if "libvulkan.so" in result.stdout:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    # Immutable/musl/portable layouts may not ship or populate ldconfig's
    # cache, so also check well-known library directories directly.
    return any(
        any(directory.glob("libvulkan.so*")) for directory in _LIBVULKAN_DIRS if directory.is_dir()
    )


def detect_gpu() -> GpuInfo:
    """Inspect installed GPUs and Vulkan drivers without changing the host."""

    return GpuInfo(
        adapters=discover_graphics_adapters(),
        vulkan_icds=discover_vulkan_icds(),
        vulkan_loader_installed=_vulkan_loader_installed(),
        vulkaninfo_path=find_executable("vulkaninfo"),
    )


__all__ = [
    "GpuInfo",
    "GraphicsAdapter",
    "VulkanIcd",
    "detect_gpu",
    "discover_graphics_adapters",
    "discover_vulkan_icds",
]
