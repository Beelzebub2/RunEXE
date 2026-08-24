"""Executable dependency detection.

This module identifies Windows runtimes and components required or
strongly suggested by an executable's imports and metadata.

Dependency detection is intentionally separate from Winetricks
installation. Detecting a dependency does not necessarily mean that
RunEXE should install a Winetricks verb for it.

For example, importing d3d11.dll indicates Direct3D 11 usage, but Wine
already provides d3d11.dll, so there is no reason to install a generic
"DirectX 11" verb.

The Winetricks mapping is therefore optional and only used for
dependencies where installing a known runtime is appropriate.
"""

from .models import Dependency, PEImport


# DLL -> dependency information.
#
# Keep this list conservative. A DLL should only be added when its
# presence is a reliable indicator of the corresponding runtime or
# component.

DLL_DEPENDENCIES: dict[str, Dependency] = {

    # ---------------------------------------------------------
    # Microsoft Visual C++ Redistributables
    # ---------------------------------------------------------

    "msvcp140.dll": Dependency(
        name="Microsoft Visual C++ Runtime",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2015",
    ),

    "vcruntime140.dll": Dependency(
        name="Microsoft Visual C++ Runtime",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2015",
    ),

    "vcruntime140_1.dll": Dependency(
        name="Microsoft Visual C++ Runtime",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2015",
    ),

    "concrt140.dll": Dependency(
        name="Microsoft Visual C++ Runtime",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2015",
    ),

    "msvcp120.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2013",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2013",
    ),

    "msvcr120.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2013",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2013",
    ),

    "msvcp110.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2012",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2012",
    ),

    "msvcr110.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2012",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2012",
    ),

    "msvcp100.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2010",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2010",
    ),

    "msvcr100.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2010",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2010",
    ),

    "msvcp90.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2008",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2008",
    ),

    "msvcr90.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2008",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2008",
    ),

    "msvcr80.dll": Dependency(
        name="Microsoft Visual C++ Runtime 2005",
        category="runtime",
        confidence="high",
        winetricks_verb="vcrun2005",
    ),

    # ---------------------------------------------------------
    # Direct3D
    # ---------------------------------------------------------

    "d3dx9_40.dll": Dependency(
        name="Direct3D 9 Extensions",
        category="graphics",
        confidence="high",
        winetricks_verb="d3dx9",
    ),

    "d3dx9_41.dll": Dependency(
        name="Direct3D 9 Extensions",
        category="graphics",
        confidence="high",
        winetricks_verb="d3dx9",
    ),

    "d3dx9_42.dll": Dependency(
        name="Direct3D 9 Extensions",
        category="graphics",
        confidence="high",
        winetricks_verb="d3dx9",
    ),

    "d3dx9_43.dll": Dependency(
        name="Direct3D 9 Extensions",
        category="graphics",
        confidence="high",
        winetricks_verb="d3dx9",
    ),

    "d3dcompiler_43.dll": Dependency(
        name="Direct3D Shader Compiler",
        category="graphics",
        confidence="high",
        winetricks_verb="d3dcompiler_43",
    ),

    "d3dcompiler_47.dll": Dependency(
        name="Direct3D Shader Compiler",
        category="graphics",
        confidence="high",
        winetricks_verb="d3dcompiler_47",
    ),

    # These indicate Direct3D usage but do not require a Winetricks
    # installation by themselves.

    "d3d9.dll": Dependency(
        name="Direct3D 9",
        category="graphics",
        confidence="high",
    ),

    "d3d10.dll": Dependency(
        name="Direct3D 10",
        category="graphics",
        confidence="high",
        winetricks_verb="dxvk",
    ),

    "d3d10_1.dll": Dependency(
        name="Direct3D 10.1",
        category="graphics",
        confidence="high",
        winetricks_verb="dxvk",
    ),

    "d3d11.dll": Dependency(
        name="Direct3D 11",
        category="graphics",
        confidence="high",
        winetricks_verb="dxvk",
    ),

    "dxgi.dll": Dependency(
        name="DirectX Graphics Infrastructure",
        category="graphics",
        confidence="high",
        winetricks_verb="dxvk",
    ),

    # ---------------------------------------------------------
    # Input
    # ---------------------------------------------------------

    "xinput1_3.dll": Dependency(
        name="XInput",
        category="input",
        confidence="high",
        winetricks_verb="xinput",
    ),

    "xinput1_4.dll": Dependency(
        name="XInput",
        category="input",
        confidence="high",
    ),

    # ---------------------------------------------------------
    # Audio
    # ---------------------------------------------------------

    "openal32.dll": Dependency(
        name="OpenAL",
        category="audio",
        confidence="high",
        winetricks_verb="openal",
    ),

    "xaudio2_7.dll": Dependency(
        name="XAudio 2.7",
        category="audio",
        confidence="high",
        winetricks_verb="xact",
    ),

    # ---------------------------------------------------------
    # Multimedia
    # ---------------------------------------------------------

    "mf.dll": Dependency(
        name="Windows Media Foundation",
        category="multimedia",
        confidence="high",
    ),

    "mfplat.dll": Dependency(
        name="Windows Media Foundation",
        category="multimedia",
        confidence="high",
    ),

    "mfreadwrite.dll": Dependency(
        name="Windows Media Foundation",
        category="multimedia",
        confidence="high",
    ),
}


DOTNET_VERB = "dotnet48"


def detect_dependencies(
    imports: list[PEImport],
) -> list[Dependency]:
    """Detect runtime/component dependencies from PE imports."""

    dependencies: list[Dependency] = []
    seen: set[tuple[str, str]] = set()

    for imported in imports or []:
        dependency = DLL_DEPENDENCIES.get(
            imported.name.lower()
        )

        if dependency is None:
            continue

        key = (
            dependency.name,
            dependency.category,
        )

        if key in seen:
            continue

        dependencies.append(dependency)
        seen.add(key)

    return dependencies


def resolve_verbs_for_dependencies(
    dependencies: list[Dependency],
) -> list[str]:
    """Return the Winetricks verbs required by detected dependencies."""

    verbs: list[str] = []
    seen: set[str] = set()

    for dependency in dependencies:
        verb = dependency.winetricks_verb

        if verb is None or verb in seen:
            continue

        verbs.append(verb)
        seen.add(verb)

    return verbs