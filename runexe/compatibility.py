from runexe.constants import (
    ANTI_CHEAT_DLLS,
    GAME_SIGNAL_DLLS,
    IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR,
    STEAM_API_DLLS,
    WINE_ARCH_BY_ARCHITECTURE,
)
from runexe.models import (
    CompatibilityReport,
    ExecutableInfo,
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


def analyze_compatibility(
    executable: ExecutableInfo,
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
    wine_arch = WINE_ARCH_BY_ARCHITECTURE.get(architecture)
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

    # Classify as game vs. application, and pick a backend accordingly.
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

    # Check for anti-cheat / DRM that will likely block execution
    # regardless of backend choice.
    blocking_issues = detect_blocking_issues(executable)

    # Check for the CLR Runtime Header.
    is_dotnet = False

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

    # Determine application type.
    if is_dotnet:
        application_type = ".NET"
        notes.append(
            "CLR Runtime Header detected."
        )
    else:
        application_type = "Native Windows"

    # Note the subsystem (GUI apps vs. console apps behave differently
    # under Wine).
    if executable.subsystem == "Windows Console":
        notes.append(
            "Console application; a terminal window will be used."
        )
    elif executable.subsystem == "Windows GUI":
        notes.append(
            "Windows GUI application."
        )

    # Flag elevated-privilege requests declared in an embedded manifest.
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
    )