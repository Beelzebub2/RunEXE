"""DLL -> winetricks verb mapping.

Used to pre-emptively install the runtime dependencies an executable's
imports suggest it needs, before attempting to launch it -- catching a
missing-DLL failure before it happens rather than parsing it out of
stderr after the fact.

This is a deliberately small, high-confidence set covering the
runtimes that show up constantly (VC++ redistributables, common D3D
extension DLLs), not an attempt at an exhaustive list. If you extend
it, check the verb name against `winetricks list-all` -- winetricks'
own catalog is the source of truth, not this file. Nothing here has
been validated against a real winetricks run yet; treat it as a first
draft to sanity-check, not gospel.
"""

# Visual C++ Redistributable runtimes. VS2015, 2017, 2019 and 2022 all
# ship binary-compatible, identically-named DLLs for the "140" runtime,
# so a single `vcrun2015` verb covers all four vcredist releases
# despite the DLL name only mentioning "140".
DLL_TO_WINETRICKS_VERB = {
    # VC++ 2015-2022 runtime (140 series)
    "msvcp140.dll": "vcrun2015",
    "vcruntime140.dll": "vcrun2015",
    "vcruntime140_1.dll": "vcrun2015",
    "concrt140.dll": "vcrun2015",
    # VC++ 2013 runtime (120 series)
    "msvcp120.dll": "vcrun2013",
    "msvcr120.dll": "vcrun2013",
    # VC++ 2012 runtime (110 series)
    "msvcp110.dll": "vcrun2012",
    "msvcr110.dll": "vcrun2012",
    # VC++ 2010 runtime (100 series)
    "msvcp100.dll": "vcrun2010",
    "msvcr100.dll": "vcrun2010",
    # VC++ 2008 runtime (90 series)
    "msvcp90.dll": "vcrun2008",
    "msvcr90.dll": "vcrun2008",
    # VC++ 2005 runtime (80 series)
    "msvcr80.dll": "vcrun2005",
    # Direct3D 9 extension library, commonly missing on older titles.
    "d3dx9_43.dll": "d3dx9",
    "d3dx9_42.dll": "d3dx9",
    "d3dx9_41.dll": "d3dx9",
    "d3dx9_40.dll": "d3dx9",
    # Direct3D 11 compiler / effects helper libraries.
    "d3dcompiler_43.dll": "d3dcompiler_43",
    "d3dcompiler_47.dll": "d3dcompiler_47",
    # OpenAL, common in older audio engines.
    "openal32.dll": "openal",
}

# .NET is detected via the CLR Runtime Header (see analyzer.py /
# compatibility.py), not via an import name, so it isn't in the table
# above -- it gets its own branch in resolve_dependencies(). This verb
# targets classic .NET Framework apps; a .NET Core / 5+ app usually
# ships self-contained or needs wine-mono instead. Telling those apart
# would require reading assembly metadata this parser doesn't extract
# yet, so this is a reasonable default, not the final word.
DOTNET_VERB = "dotnet48"


def resolve_verbs_for_imports(dll_names: list[str]) -> list[str]:
    """Map a list of imported DLL names to deduplicated winetricks
    verbs, preserving first-seen order."""

    verbs: list[str] = []
    seen = set()

    for dll_name in dll_names:
        verb = DLL_TO_WINETRICKS_VERB.get(dll_name.lower())

        if verb is not None and verb not in seen:
            verbs.append(verb)
            seen.add(verb)

    return verbs