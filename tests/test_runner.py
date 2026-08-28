import subprocess
from unittest.mock import patch

from runexe.models import CompatibilityReport, ExecutableInfo
from runexe.runner import launch, prefix_path_for, set_windows_version


def report(**changes):
    values = dict(
        application_type="Native Windows",
        architecture="x86_64",
        category="application",
        backend="wine",
        recommended_runtime="Wine",
        wine_arch="win64",
    )
    values.update(changes)
    return CompatibilityReport(**values)


def test_prefix_name_is_sanitized_and_stable(tmp_path):
    executable = ExecutableInfo(tmp_path / "Odd Name! (x64).exe", True)

    first = prefix_path_for(executable)
    second = prefix_path_for(executable)

    assert first == second
    assert first.name.startswith("odd_name_x64-")


@patch("runexe.runner.subprocess.run")
@patch("runexe.runner.ensure_prefix")
@patch("runexe.runner._require_binary", return_value="/usr/bin/wine")
def test_launch_uses_executable_directory_and_forwards_arguments(require, ensure, run, tmp_path):
    path = tmp_path / "app.exe"
    path.touch()
    run.return_value = subprocess.CompletedProcess([], 0, "output", "")

    result = launch(ExecutableInfo(path, True), report(), extra_args=["--portable", "two words"])

    assert result.stdout == "output"
    assert run.call_args.kwargs["cwd"] == tmp_path
    assert run.call_args.args[0][-2:] == ["--portable", "two words"]


@patch("runexe.runner.run_with_progress")
@patch("runexe.runner._wine_tool_command", return_value=["winecfg"])
def test_winver_accepts_friendly_and_native_forms(tool, run_progress, tmp_path):
    run_progress.return_value = subprocess.CompletedProcess([], 0)

    set_windows_version(tmp_path, "win64", "win10")

    assert run_progress.call_args.args[0] == ["winecfg", "-v", "win10"]
