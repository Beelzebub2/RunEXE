from typer.testing import CliRunner

from runexe import __version__
from runexe.cli import app
from runexe.models import CompatibilityReport, ExecutableInfo, HostInfo
from runexe.runner import LaunchResult

from .helpers import make_pe

runner = CliRunner()


def test_version_comes_from_package_metadata():
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"RunEXE {__version__}"


def test_json_analysis_is_machine_readable(tmp_path):
    path = make_pe(tmp_path / "sample.exe")

    result = runner.invoke(app, ["analyze", str(path), "--json", "--no-host"])

    assert result.exit_code == 0
    assert '"architecture": "x86"' in result.stdout
    assert '"compatibility"' in result.stdout


def test_run_forwards_every_argument_after_separator(tmp_path, monkeypatch):
    path = tmp_path / "app.exe"
    path.touch()
    executable = ExecutableInfo(path, True, architecture="x86_64")
    compatibility = CompatibilityReport(
        application_type="Native Windows",
        architecture="x86_64",
        category="application",
        backend="wine",
        recommended_runtime="Wine",
        wine_arch="win64",
    )
    host = HostInfo("x86_64", True, "wine-10", True, True, True)
    seen = {}

    monkeypatch.setattr("runexe.cli.analyze_executable", lambda _: executable)
    monkeypatch.setattr("runexe.cli.detect_host", lambda: host)
    monkeypatch.setattr("runexe.cli.analyze_compatibility", lambda *_: compatibility)

    def fake_launch(*args, **kwargs):
        seen.update(kwargs)
        return LaunchResult(0, "", "")

    monkeypatch.setattr("runexe.cli.launch", fake_launch)

    result = runner.invoke(
        app,
        ["run", str(path), "--no-deps", "--", "--portable", "two words"],
    )

    assert result.exit_code == 0
    assert seen["extra_args"] == ["--portable", "two words"]


def test_run_rejects_conflicting_runtime_options(tmp_path):
    path = tmp_path / "app.exe"
    path.touch()

    result = runner.invoke(
        app,
        ["run", str(path), "--backend", "wine", "--proton", "Proton Experimental"],
    )

    assert result.exit_code == 1
    assert "cannot be combined" in result.output
