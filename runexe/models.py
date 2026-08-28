from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PEDataDirectory:
    virtual_address: int
    size: int


@dataclass
class PESection:
    name: str
    virtual_size: int
    virtual_address: int
    raw_size: int
    raw_offset: int


@dataclass
class PEImport:
    name: str
    functions: list[str] = field(default_factory=list)


@dataclass
class VersionInfo:
    """Parsed VS_VERSIONINFO resource (RT_VERSION)."""

    file_version: str | None = None
    product_version: str | None = None
    # Raw StringTable key/value pairs, e.g. "ProductName", "CompanyName",
    # "FileDescription".
    strings: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutableInfo:
    path: Path
    valid: bool
    format: str | None = None
    architecture: str | None = None
    subsystem: str | None = None
    reason: str | None = None
    sections: list[PESection] | None = None
    data_directories: list[PEDataDirectory] | None = None
    imports: list[PEImport] | None = None
    manifest: str | None = None
    version_info: VersionInfo | None = None


@dataclass(frozen=True)
class Dependency:
    """A runtime or Windows component detected from an executable."""

    name: str
    category: str
    confidence: str = "high"
    winetricks_verb: str | None = None


@dataclass
class CompatibilityReport:
    application_type: str
    architecture: str
    # "game" or "application" - drives the Wine vs. Proton recommendation.
    category: str
    # "wine", "proton", or "unsupported".
    backend: str
    # Human-readable version of `backend`, e.g. "Proton (Steam Play)".
    recommended_runtime: str
    wine_arch: str | None = None
    supported: bool = True
    # Detected reasons the app is unlikely to run at all regardless of
    # backend (e.g. kernel-level anti-cheat), separate from `notes`
    # so callers can act on this without parsing free text.
    blocking_issues: list[str] = field(default_factory=list)
    # Important but non-deterministic compatibility concerns, such as
    # per-title anti-cheat enablement.
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Winetricks verbs (e.g. "vcrun2015", "dotnet48") that should be
    # installed into the prefix before launch, inferred from imports
    # and the CLR header. See dependencies.py.
    required_verbs: list[str] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)


@dataclass
class HostInfo:
    architecture: str
    wine_installed: bool
    wine_version: str | None
    # None means that read-only inspection could not prove support either
    # way. Prefix creation performs the definitive capability check.
    wine_wow64: bool | None
    wine_32bit_prefix: bool | None
    winetricks_installed: bool
