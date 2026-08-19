IMAGE_DIRECTORY_ENTRY_IMPORT = 1
IMAGE_DIRECTORY_ENTRY_RESOURCE = 2
IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR = 14

# Resource types (used to locate RT_MANIFEST / RT_VERSION in the
# resource directory tree).
RESOURCE_TYPE_VERSION = 16
RESOURCE_TYPE_MANIFEST = 24

# IMAGE_OPTIONAL_HEADER.Subsystem values.
SUBSYSTEM_TYPES = {
    0: "Unknown",
    1: "Native",
    2: "Windows GUI",
    3: "Windows Console",
    5: "OS/2 Console",
    7: "POSIX Console",
    9: "Windows CE GUI",
    10: "EFI Application",
    11: "EFI Boot Service Driver",
    12: "EFI Runtime Driver",
    13: "EFI ROM",
    14: "Xbox",
    16: "Windows Boot Application",
}

# Architecture -> WINEARCH mapping. Architectures absent from this map
# (e.g. ARM64) are not supported by Wine/Proton.
WINE_ARCH_BY_ARCHITECTURE = {
    "x86": "win32",
    "x86_64": "win64",
}

# Anti-cheat / DRM DLLs that are reliably identifiable by name in the
# import table. Both entries below are dominant, well-documented
# anti-cheat systems that ship a distinctly named client DLL the game
# actually imports.
#
# Deliberately NOT included: Denuvo and most VM-based packers/DRM.
# These wrap or encrypt the executable itself rather than shipping a
# separate imported DLL, so they aren't reliably detectable this way;
# claiming to detect them via the import table would be misleading.
# A packed/obfuscated import table (very few imports, mostly from
# KERNEL32) is a soft hint of such protection but not proof, so it's
# left out of automatic detection for now.
ANTI_CHEAT_DLLS = {
    "easyanticheat.dll": "Easy Anti-Cheat",
    "easyanticheat_x64.dll": "Easy Anti-Cheat",
    "easyanticheat_x86.dll": "Easy Anti-Cheat",
    "beclient.dll": "BattlEye",
    "beclient_x64.dll": "BattlEye",
    "beservice.dll": "BattlEye",
}

# DLLs that strongly suggest the executable is a Steam game.
STEAM_API_DLLS = {
    "steam_api.dll",
    "steam_api64.dll",
}

# DLLs commonly used by games (graphics/input middleware) but rare in
# ordinary desktop applications. Any one of these is a moderate signal;
# it's weaker than a Steam API import, so it's only used when no Steam
# API import is present.
GAME_SIGNAL_DLLS = {
    "d3d9.dll",
    "d3d10.dll",
    "d3d11.dll",
    "d3d12.dll",
    "dxgi.dll",
    "d3dcompiler_43.dll",
    "d3dcompiler_47.dll",
    "dinput8.dll",
    "xinput1_3.dll",
    "xinput1_4.dll",
    "xinput9_1_0.dll",
    "xaudio2_9.dll",
}