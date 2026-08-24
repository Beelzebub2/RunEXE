from runexe.constants import (
    ANTI_CHEAT_DLLS,
    GAME_SIGNAL_DLLS,
    IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR,
    STEAM_API_DLLS,
    WINE_ARCH_BY_ARCHITECTURE,
)
from runexe.dependencies import (
    DOTNET_VERB, 
    detect_dependencies, 
    resolve_verbs_for_dependencies,
)
from runexe.models import (
    CompatibilityReport,
    ExecutableInfo,
    HostInfo,
    Dependency,
)
from runexe.resources import extract_requested_execution_level


def detect_blocking_issues(executable: ExecutableInfo) -> list[str]:
    """Return a list of detected reasons this executable is unlikely to
    run under Wine/Proton at all, regardless of backend choice.

    Currently checks imported DLL names against known anti-cheat
    clients. See the comment above ANTI_CHEAT_DLLS in constants.py for
    what this deliberately does not attempt to detect (e.g. Denuvo).
    """

    if not executable.imports:
        return []

    detected_products = set()

    for imported in executable.imports:
        dll_name = imported.name.lower()
        product = ANTI_CHEAT_DLLS.get(dll_name)

        if product is not None:
            detected_products.add(product)

    return [
        f"{product} anti-cheat detected: this application is very "
        f"unlikely to run under Wine or Proton."
        for product in sorted(detected_products)
    ]


def classify_application(executable: ExecutableInfo) -> str:
    """Classify the executable as "game" or "application" based on its
    imports, to drive the Wine vs. Proton recommendation.

    A Steam API import is treated as a strong, standalone signal. A
    graphics/input middleware import (Direct3D, XInput, etc.) is a
    weaker signal and is only used when no Steam API import is
    present, since plenty of non-game applications also touch D3D
    (e.g. video players, CAD tools).
    """

    if not executable.imports:
        return "application"

    imported_names = {
        imported.name.lower() for imported in executable.imports
    }

    if imported_names & STEAM_API_DLLS:
        return "game"

    if imported_names & GAME_SIGNAL_DLLS:
        return "game"

    return "application"


def detect_apphost_dotnet(executable_path: Path) -> bool:
    """Detect modern .NET (Core 3.0+) apphost executables.

    Since .NET Core 3.0, `dotnet publish` produces a native launcher
    stub (no CLR Runtime Header -- see the COM Descriptor check below)
    alongside the actual managed assembly and a `<name>.runtimeconfig.json`
    describing which runtime to load. The stub loads `hostfxr.dll`
    dynamically at runtime, so there's no PE-level signal (no CLR
    header, no static import) that marks it as .NET -- the
    runtimeconfig.json sitting next to it is the only reliable tell.

    This only catches apps published as apphost stubs (the SDK
    default). Self-contained, single-file-trimmed publishes fold the
    runtimeconfig into the binary and won't have a separate JSON file
    -- that case isn't handled here and would need a different check
    (e.g. scanning for an embedded PE resource).
    """

    runtimeconfig = executable_path.with_suffix(".runtimeconfig.json")

    if runtimeconfig.exists():
        return True

    # Publish tooling doesn't always preserve exact case on
    # case-sensitive filesystems; fall back to a case-insensitive
    # sibling scan before giving up.
    stem_lower = executable_path.stem.lower()

    return any(
        sibling.stem.lower() == stem_lower
        and sibling.suffix.lower() == ".json"
        and sibling.name.lower().endswith("runtimeconfig.json")
        for sibling in executable_path.parent.glob("*.json")
    )


def analyze_compatibility(
    executable: ExecutableInfo,
    host: HostInfo | None = None,
) -> CompatibilityReport:

    notes = []

    # Determine application architecture.
    architecture = executable.architecture or "Unknown"

    if architecture == "x86":
        notes.append(
            "32-bit Windows executable detected."
        )

    elif architecture == "x86_64":
        notes.append(
            "64-bit Windows executable detected."
        )

    elif architecture == "ARM64":
        notes.append(
            "Windows ARM64 executable detected."
        )

    else:
        notes.append(
            "Unknown executable architecture."
        )

    # Map the architecture to a WINEARCH value.
    if architecture == "x86":
        if host.wine_32bit_prefix:
            wine_arch = "win32"

            notes.append(
                "32-bit Windows executable detected."
            )
            notes.append(
                "Traditional 32-bit Wine prefix support is available."
            )

        elif host.wine_wow64:
            wine_arch = "win64"

            notes.append(
                "Wine WoW64 support detected."
            )
            notes.append(
                "The application will run through a 64-bit Wine prefix."
            )

        else:
            wine_arch = None
            supported = False

            notes.append(
                "32-bit Windows executable detected."
            )
            notes.append(
                "Neither a traditional 32-bit Wine prefix nor WoW64 "
                "support is available."
            )
            notes.append(
                "Install Wine with 32-bit/multilib support to run "
                "32-bit Windows applications."
            )

    else:
        wine_arch = WINE_ARCH_BY_ARCHITECTURE.get(architecture)

        if wine_arch is None:
            supported = False
            notes.append(
                "Could not determine a WINEARCH value for this "
                "architecture."
            )
        else:
            supported = True
    
    supported = wine_arch is not None

    if architecture == "ARM64":
        notes.append(
            "ARM64 Windows applications are not supported: "
            "Wine and Proton cannot run Windows-on-ARM binaries."
        )

    elif not supported:
        notes.append(
            "Could not determine a WINEARCH value for this "
            "architecture."
        )

    # ---------------------------------------------------------
    # Host compatibility
    # ---------------------------------------------------------

    blocking_issues = []

    if host is not None:
        notes.append(
            f"Host architecture: {host.architecture}"
        )

        if architecture == "x86_64":
            if host.architecture != "x86_64":
                supported = False
                blocking_issues.append(
                    "This executable requires an x86_64 host."
                )

        elif architecture == "x86":
            if host.architecture not in {"x86", "x86_64"}:
                supported = False
                blocking_issues.append(
                    "This executable requires an x86-compatible host."
                )

        # Wine availability
        if not host.wine_installed:
            blocking_issues.append(
                "Wine is not installed."
            )
        else:
            if host.wine_version:
                notes.append(
                    f"Wine detected: {host.wine_version}"
                )
            else:
                notes.append(
                    "Wine is installed."
                )

    # ---------------------------------------------------------
    # Classify as game vs. application
    # ---------------------------------------------------------

    category = classify_application(executable)

    if not supported:
        backend = "unsupported"
        recommended_runtime = "Unsupported"

    elif category == "game":
        backend = "proton"
        recommended_runtime = "Proton (Steam Play)"

        notes.append(
            "Game-related imports detected; Proton is recommended "
            "over plain Wine for DirectX translation and Steam "
            "integration."
        )

    else:
        backend = "wine"
        recommended_runtime = "Wine"

    # ---------------------------------------------------------
    # Anti-cheat / DRM
    # ---------------------------------------------------------

    blocking_issues.extend(
        detect_blocking_issues(executable)
    )

    # ---------------------------------------------------------
    # .NET detection
    # ---------------------------------------------------------

    is_dotnet = False
    is_dotnet_apphost = False

    if (
        executable.data_directories
        and len(executable.data_directories)
        > IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR
    ):
        clr_directory = executable.data_directories[
            IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR
        ]

        if (
            clr_directory.virtual_address != 0
            and clr_directory.size != 0
        ):
            is_dotnet = True

    if not is_dotnet and detect_apphost_dotnet(executable.path):
        is_dotnet = True
        is_dotnet_apphost = True

    # Determine application type.
    if is_dotnet:
        application_type = ".NET"

        if is_dotnet_apphost:
            notes.append(
                "Modern .NET apphost detected via runtimeconfig.json "
                "(no CLR Runtime Header present -- this is a native "
                "launcher stub, not a managed executable)."
            )
        else:
            notes.append(
                "CLR Runtime Header detected."
            )

    else:
        application_type = "Native Windows"

    # ---------------------------------------------------------
    # Dependencies
    # ---------------------------------------------------------

    dependencies = detect_dependencies(
        executable.imports or []
    )

    # .NET is detected structurally through the CLR Runtime Header,
    # rather than through an imported DLL.
    if is_dotnet:
        dependencies.append(
            Dependency(
                name=".NET Framework",
                category="runtime",
                confidence="high",
                winetricks_verb=DOTNET_VERB,
            )
        )
        #========================
        # Add DXVK dependency for .NET applications, might be removed later
        #========================
        dependencies.append(
            Dependency(
                name="DXVK (DirectX-to-Vulkan, common .NET/WPF requirement)",
                category="graphics",
                confidence="medium",
                winetricks_verb="dxvk",
            )
        )

    required_verbs = resolve_verbs_for_dependencies(
        dependencies
    )

    # ---------------------------------------------------------
    # Subsystem
    # ---------------------------------------------------------

    if executable.subsystem == "Windows Console":
        notes.append(
            "Console application; a terminal window will be used."
        )

    elif executable.subsystem == "Windows GUI":
        notes.append(
            "Windows GUI application."
        )

    # ---------------------------------------------------------
    # Manifest
    # ---------------------------------------------------------

    if executable.manifest:
        execution_level = extract_requested_execution_level(
            executable.manifest
        )

        if execution_level == "requireAdministrator":
            notes.append(
                "Manifest requests administrator privileges; may "
                "require additional Wine/Proton configuration."
            )

    return CompatibilityReport(
        application_type=application_type,
        architecture=architecture,
        category=category,
        backend=backend,
        recommended_runtime=recommended_runtime,
        wine_arch=wine_arch,
        supported=supported,
        blocking_issues=blocking_issues,
        notes=notes,
        dependencies=dependencies,
        required_verbs=required_verbs,
    )