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

# Direct3D dependency names (see dependencies.py) that DXVK/VKD3D-Proton
# translate through Vulkan. Direct3D 9 Extensions (d3dx9) is deliberately
# excluded: it is a helper library, not the graphics API entry point
# itself, and importing it alone doesn't mean the app renders with D3D.
DIRECT3D_VULKAN_APIS = {
    "Direct3D 9",
    "Direct3D 10",
    "Direct3D 10.1",
    "Direct3D 11",
    "Direct3D 12",
}

# Anti-cheat DLLs that are identifiable by name in the import table.
# Presence is a compatibility warning, not a blocker: EAC and BattlEye
# support is enabled by publishers on a per-title basis for Proton.
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

# DLLs commonly used by games (graphics/input middleware, or a game
# engine's runtime) but rare in ordinary desktop applications. Any one
# of these is a moderate signal; it's weaker than a Steam API import,
# so it's only used when no Steam API import is present.
#
# UnityPlayer.dll indicates the Unity engine was used, which is heavily
# game-dominated but also used for some non-game interactive software
# (visualization tools, simulators, etc.), so it belongs here as a
# moderate signal rather than as its own hard "this is a game" rule.
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
    "unityplayer.dll",
    # Audio/physics middleware: heavily used by games, but also shows up
    # in some non-game interactive media/simulation software, so these
    # stay in the weak-signal set rather than being treated as standalone
    # strong signals.
    "fmod.dll",
    "fmodstudio.dll",
    "fmodstudio64.dll",
    "physx3.dll",
    "physx3_x64.dll",
    "physx3_x86.dll",
}

# Third-party game-distribution/matchmaking SDKs. Unlike the generic
# middleware in GAME_SIGNAL_DLLS, these are only ever linked by games
# (or launchers), so a single import is treated as a strong, standalone
# signal alongside the Steam API.
GAME_PLATFORM_DLLS = {
    # Epic Online Services -- Epic's cross-platform matchmaking/friends
    # SDK, used by Epic Games Store titles and many Unreal games that
    # don't ship on Epic's own store.
    "eossdk-win32-shipping.dll": "Epic Online Services",
    "eossdk-win64-shipping.dll": "Epic Online Services",
    # GOG Galaxy -- GOG's equivalent of the Steam API.
    "galaxy.dll": "GOG Galaxy",
    "galaxy64.dll": "GOG Galaxy",
    "galaxypeer.dll": "GOG Galaxy",
    "galaxypeer64.dll": "GOG Galaxy",
}

# Case-folded substrings checked against an executable's local identity
# text (filename, VS_VERSIONINFO strings) to catch engines that link
# their runtime statically and therefore never appear in the PE import
# table -- Unreal Engine and Godot both do this, unlike Unity which
# ships UnityPlayer.dll as a separate import. Each entry is a strong,
# standalone signal: these strings are specific enough that they don't
# show up in ordinary applications by accident.
GAME_ENGINE_IDENTITY_MARKERS = {
    "unreal engine": "Unreal Engine",
    "unrealengine": "Unreal Engine",
    "godot engine": "Godot Engine",
    "gamemaker": "GameMaker",
    "yoyo games": "GameMaker",
}

# Filenames/suffixes found alongside an executable that indicate a
# specific engine packaged its assets there, independent of anything
# inside the PE file itself. These survive packing/obfuscation of the
# executable since they're just sibling files on disk. Matched
# case-insensitively against directory entries next to the executable.
#
# - "<stem>_Data" directory: Unity's standard build layout.
# - "Engine" + "Content" directories together: Unreal's standard
#   packaged-game layout (checked as a pair, not individually, since
#   either name alone is a common ordinary word).
# - "data.win": GameMaker's asset/bytecode bundle.
# - "*.pck": Godot's packed resource file.
GAME_ENGINE_DATA_DIR_SUFFIX = "_data"
GAME_ENGINE_UNREAL_DIRS = {"engine", "content"}
GAME_ENGINE_SIBLING_FILES = {
    "data.win": "GameMaker",
}
GAME_ENGINE_SIBLING_EXTENSIONS = {
    ".pck": "Godot Engine",
}
