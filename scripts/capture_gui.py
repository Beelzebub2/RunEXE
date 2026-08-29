"""Refresh the README screenshot using a deterministic demonstration state."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Native Windows rendering is required for the bundled Segoe UI font.  Headless
# Linux builders can still refresh the screenshot with Qt's offscreen backend.
if sys.platform != "win32" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from runexe.gui.theme import apply_theme
from runexe.gui.window import AnalysisBundle, RunEXEWindow
from runexe.models import CompatibilityReport, ExecutableInfo, HostInfo, VersionInfo
from runexe.proton import ProtonInstallation


def main() -> None:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    source = Path.home() / "Downloads" / "Aurora Studio.exe"
    executable = ExecutableInfo(
        source,
        True,
        format="PE32+ (64-bit)",
        architecture="x86_64",
        subsystem="Windows GUI",
        version_info=VersionInfo(product_version="2.4", strings={"ProductName": "Aurora Studio"}),
    )
    host = HostInfo(
        "x86_64",
        True,
        "wine-11.0",
        True,
        True,
        True,
        proton_installed=True,
        proton_versions=["Proton Experimental"],
    )
    compatibility = CompatibilityReport(
        application_type="Native Windows",
        architecture="x86_64",
        category="application",
        backend="wine",
        recommended_runtime="Wine 11.0",
        wine_arch="win64",
        notes=[
            "64-bit Windows executable detected.",
            "An isolated per-application Wine prefix will be used.",
        ],
    )
    proton = ProtonInstallation(
        "Proton Experimental",
        Path.home() / ".steam" / "root" / "steamapps" / "common" / "Proton Experimental" / "proton",
        "experimental",
        Path.home() / ".steam" / "root",
    )

    window = RunEXEWindow(auto_refresh=False)
    window.resize(1180, 790)
    window._analysis_ready(AnalysisBundle(source, executable, host, compatibility, [proton]))
    window.show()
    app.processEvents()
    settle = QEventLoop()
    QTimer.singleShot(260, settle.quit)
    settle.exec()
    target = Path(__file__).resolve().parent.parent / "assets" / "runexe-gui.png"
    if not window.grab().save(str(target), "PNG"):
        raise RuntimeError(f"Could not save GUI screenshot to {target}")
    print(target)
    window.close()


if __name__ == "__main__":
    main()
