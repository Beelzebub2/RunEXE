import json

from runexe.compatibility import (
    analyze_compatibility,
    classify_application,
    detect_anti_cheat_warnings,
    detect_apphost_dotnet_version,
    dotnet_version_to_verb,
)
from runexe.models import ExecutableInfo, HostInfo, PEImport
from runexe.profiles import PAINT_NET, detect_runtime_issue


def executable(tmp_path, imports=None, architecture="x86_64"):
    path = tmp_path / "app.exe"
    path.touch()
    return ExecutableInfo(
        path=path,
        valid=True,
        architecture=architecture,
        subsystem="Windows GUI",
        imports=imports or [],
        data_directories=[],
    )


def test_single_generic_graphics_import_is_not_enough_to_call_app_a_game(tmp_path):
    app = executable(tmp_path, [PEImport("d3d11.dll")])

    assert classify_application(app) == "application"


def test_game_uses_available_wine_backend_and_recommends_proton(tmp_path):
    app = executable(tmp_path, [PEImport("d3d11.dll"), PEImport("xinput1_3.dll")])
    host = HostInfo(
        "x86_64",
        True,
        "wine-10",
        True,
        True,
        True,
        proton_installed=True,
        proton_versions=["Proton Experimental"],
    )

    report = analyze_compatibility(app, host)

    assert report.category == "game"
    assert report.backend == "proton"
    assert report.recommended_runtime == "Proton Experimental"


def test_anti_cheat_is_a_warning_not_a_hard_blocker(tmp_path):
    app = executable(tmp_path, [PEImport("EasyAntiCheat_x64.dll")])

    report = analyze_compatibility(app)

    assert detect_anti_cheat_warnings(app)
    assert report.warnings
    assert not report.blocking_issues


def test_x86_is_not_marked_unsupported_when_host_probe_is_inconclusive(tmp_path):
    app = executable(tmp_path, architecture="x86")
    host = HostInfo("x86_64", True, "wine-10", None, None, True)

    report = analyze_compatibility(app, host)

    assert report.supported
    assert report.wine_arch == "win64"


def test_reads_desktop_runtimeconfig(tmp_path):
    app = executable(tmp_path)
    app.path.with_name("app.runtimeconfig.json").write_text(
        json.dumps(
            {
                "runtimeOptions": {
                    "frameworks": [
                        {"name": "Microsoft.NETCore.App", "version": "8.0.1"},
                        {"name": "Microsoft.WindowsDesktop.App", "version": "8.0.1"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert detect_apphost_dotnet_version(app.path) == ("8.0.1", True)
    assert dotnet_version_to_verb("8.0.1", True) == "dotnetdesktop8"
    assert dotnet_version_to_verb("6.0.30", False) == "dotnet6"


def test_self_contained_dotnet_does_not_install_shared_runtime(tmp_path):
    app = executable(tmp_path)
    app.path.with_name("app.runtimeconfig.json").write_text(
        json.dumps(
            {
                "runtimeOptions": {
                    "includedFrameworks": [
                        {"name": "Microsoft.WindowsDesktop.App", "version": "8.0.1"}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    report = analyze_compatibility(app)

    assert "dotnetdesktop8" not in report.required_verbs
    assert any("self-contained" in note for note in report.notes)


def test_rejects_non_object_runtimeconfig(tmp_path):
    app = executable(tmp_path)
    app.path.with_name("app.runtimeconfig.json").write_text("[]", encoding="utf-8")

    assert detect_apphost_dotnet_version(app.path) == (None, False)


def test_detects_paint_net_and_recommends_modern_windows(tmp_path):
    app = executable(tmp_path)
    app.path = app.path.with_name("PaintDotNet.exe")
    app.path.touch()

    report = analyze_compatibility(app)

    assert report.profile is not None
    assert report.profile.key == "paint-dot-net"
    assert report.profile.minimum_windows_build == 19044
    assert report.profile.recommended_windows_version == "11"
    assert any("21H2" in note for note in report.notes)


def test_recognizes_paint_net_old_windows_failure():
    diagnostic = detect_runtime_issue("", 1150 % 256, PAINT_NET)

    assert diagnostic is not None
    assert diagnostic.recommended_windows_version == "11"
    assert "rejected the Windows version" in diagnostic.message
