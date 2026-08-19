from runexe.constants import (
    IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR,
)
from runexe.models import (
    CompatibilityReport,
    ExecutableInfo,
)


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

    # Recommend runtime.
    recommended_runtime = "Wine"

    if architecture == "ARM64":
        notes.append(
            "ARM64 Windows applications may require "
            "additional compatibility support."
        )

    return CompatibilityReport(
        application_type=application_type,
        recommended_runtime=recommended_runtime,
        architecture=architecture,
        notes=notes,
    )