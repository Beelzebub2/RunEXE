"""Main window and page orchestration for the RunEXE desktop interface."""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QProcess,
    QProcessEnvironment,
    QPropertyAnimation,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from runexe import __version__
from runexe.analyzer import analyze_executable
from runexe.compatibility import analyze_compatibility
from runexe.host import detect_host
from runexe.models import CompatibilityReport, ExecutableInfo, HostInfo
from runexe.profiles import detect_runtime_issue
from runexe.proton import ProtonInstallation, discover_proton_installations
from runexe.runner import (
    PreparedEnvironment,
    build_launch_spec,
    open_runtime_configuration,
    prepare_environment,
)

from .theme import COLORS, apply_theme
from .widgets import Card, DropZone, MetricCard, SmoothScrollArea, StatusPill
from .workers import Worker


@dataclass(frozen=True)
class AnalysisBundle:
    source: Path
    executable: ExecutableInfo
    host: HostInfo
    compatibility: CompatibilityReport
    proton_installations: list[ProtonInstallation]


def _asset_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "runexe-logo.png"


def _muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("muted", True)
    label.setWordWrap(True)
    return label


def _section_header(title: str, description: str = "") -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(4)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    if description:
        layout.addWidget(_muted(description))
    return layout


def _button(text: str, *, primary: bool = False, accent: bool = False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setProperty("primary", True)
    if accent:
        button.setProperty("accent", True)
    return button


class RunEXEWindow(QMainWindow):
    """Responsive desktop shell around RunEXE's analysis and runtime services."""

    PAGE_TITLES = (
        ("Overview", "Inspect an application and launch it with a clear compatibility plan."),
        ("Runtime setup", "Choose, prepare, and configure isolated Wine or Proton environments."),
        ("Activity", "Review analysis, preparation, launch output, and errors."),
    )

    def __init__(self, initial_file: Path | None = None, *, auto_refresh: bool = True) -> None:
        super().__init__()
        self.settings = QSettings("RunEXE", "RunEXE")
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: dict[str, Worker] = {}
        self.source_path: Path | None = None
        self.executable: ExecutableInfo | None = None
        self.host: HostInfo | None = None
        self.compatibility: CompatibilityReport | None = None
        self.proton_installations: list[ProtonInstallation] = []
        self.application_process: QProcess | None = None
        self._application_output: list[str] = []
        self._page_animation: QVariantAnimation | None = None
        self._profile_animation: QPropertyAnimation | None = None

        self.setWindowTitle(f"RunEXE {__version__}")
        self.setMinimumSize(920, 680)
        self.resize(1180, 790)
        if _asset_path().is_file():
            self.setWindowIcon(QIcon(str(_asset_path())))

        self._build_ui()
        self._create_shortcuts()
        self._restore_settings()
        self._show_page(0)
        self._update_controls()

        if auto_refresh:
            QTimer.singleShot(80, self.refresh_runtimes)
        if initial_file is not None:
            QTimer.singleShot(150, lambda: self.analyze_path(initial_file))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._build_sidebar())
        shell.addWidget(self._build_workspace(), 1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo_label = QLabel()
        logo_label.setFixedSize(46, 46)
        if _asset_path().is_file():
            pixmap = QPixmap(str(_asset_path()))
            logo_label.setPixmap(
                pixmap.scaled(
                    46,
                    46,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("RunEXE")
        title.setObjectName("brandTitle")
        version = _muted(f"Desktop {__version__}")
        brand_text.addWidget(title)
        brand_text.addWidget(version)
        brand.addWidget(logo_label)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(20)

        self.nav_buttons: list[QPushButton] = []
        for index, title_text in enumerate(("Overview", "Runtime setup", "Activity")):
            nav = QPushButton(title_text)
            nav.setProperty("nav", True)
            nav.setCheckable(True)
            nav.setAccessibleName(f"Open {title_text} page")
            nav.clicked.connect(lambda _checked=False, page=index: self._show_page(page))
            layout.addWidget(nav)
            self.nav_buttons.append(nav)
        layout.addStretch(1)

        cli_card = Card()
        cli_layout = QVBoxLayout(cli_card)
        cli_layout.setContentsMargins(13, 12, 13, 12)
        cli_layout.setSpacing(5)
        cli_title = QLabel("Terminal included")
        cli_title.setStyleSheet("font-weight: 650;")
        cli_layout.addWidget(cli_title)
        cli_layout.addWidget(_muted("Every desktop action remains available through runexe."))
        layout.addWidget(cli_card)
        return sidebar

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(30, 22, 30, 15)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = _muted()
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        header_layout.addLayout(titles, 1)
        self.header_status = StatusPill("Checking runtimes")
        header_layout.addWidget(self.header_status, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(header)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.pages = QStackedWidget()
        self.pages.setAutoFillBackground(True)
        self.pages.addWidget(self._build_overview_page())
        self.pages.addWidget(self._build_runtime_page())
        self.pages.addWidget(self._build_activity_page())
        layout.addWidget(self.pages, 1)

        status = QFrame()
        status.setObjectName("statusBar")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(30, 9, 30, 13)
        self.task_status = _muted("Ready")
        self.environment_status = _muted("No application selected")
        self.environment_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        status_layout.addWidget(self.task_status, 1)
        status_layout.addWidget(self.environment_status, 1)
        layout.addWidget(status)
        return workspace

    def _scroll_page(self) -> tuple[SmoothScrollArea, QWidget, QVBoxLayout]:
        scroll = SmoothScrollArea()
        content = QWidget()
        content.setObjectName("scrollContent")
        content.setAutoFillBackground(True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 14, 30, 30)
        layout.setSpacing(18)
        scroll.setWidget(content)
        return scroll, content, layout

    def _build_overview_page(self) -> QWidget:
        scroll, _content, layout = self._scroll_page()
        self.overview_scroll = scroll

        hero = Card()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 22)
        hero_layout.setSpacing(14)
        heading_row = QHBoxLayout()
        heading_text = QVBoxLayout()
        hero_title = QLabel("Launch Windows software with confidence")
        hero_title.setObjectName("heroTitle")
        heading_text.addWidget(hero_title)
        heading_text.addWidget(
            _muted("Static inspection first. Isolated runtime preparation only when you ask.")
        )
        heading_row.addLayout(heading_text, 1)
        self.browse_button = _button("Browse files")
        self.browse_button.clicked.connect(self.browse_file)
        self.analyze_button = _button("Analyze", primary=True)
        self.analyze_button.clicked.connect(self.analyze_selected)
        heading_row.addWidget(self.browse_button)
        heading_row.addWidget(self.analyze_button)
        hero_layout.addLayout(heading_row)

        self.drop_zone = DropZone()
        self.drop_zone.browse_requested.connect(self.browse_file)
        self.drop_zone.file_selected.connect(lambda path: self.analyze_path(Path(path)))
        hero_layout.addWidget(self.drop_zone)
        layout.addWidget(hero)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.format_metric = MetricCard("Format")
        self.arch_metric = MetricCard("Architecture")
        self.runtime_metric = MetricCard("Selected runtime")
        self.readiness_metric = MetricCard("Readiness")
        metrics.addWidget(self.format_metric, 0, 0)
        metrics.addWidget(self.arch_metric, 0, 1)
        metrics.addWidget(self.runtime_metric, 1, 0)
        metrics.addWidget(self.readiness_metric, 1, 1)
        metrics.setColumnStretch(0, 1)
        metrics.setColumnStretch(1, 1)
        layout.addLayout(metrics)

        details = Card()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(20, 18, 20, 20)
        details_layout.addLayout(
            _section_header(
                "Application details", "Information read directly from the package or PE file."
            )
        )
        form = QFormLayout()
        form.setContentsMargins(0, 12, 0, 0)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)
        self.detail_path = _muted("Not selected")
        self.detail_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_product = QLabel("-")
        self.detail_subsystem = QLabel("-")
        self.detail_dependencies = QLabel("-")
        self.detail_dependencies.setWordWrap(True)
        form.addRow("Source", self.detail_path)
        form.addRow("Product", self.detail_product)
        form.addRow("Subsystem", self.detail_subsystem)
        form.addRow("Dependencies", self.detail_dependencies)
        details_layout.addLayout(form)
        layout.addWidget(details)

        self.profile_card = Card()
        self.profile_card.setProperty("recommendation", True)
        profile_layout = QHBoxLayout(self.profile_card)
        profile_layout.setContentsMargins(20, 17, 20, 17)
        profile_copy = QVBoxLayout()
        profile_copy.setSpacing(5)
        self.profile_title = QLabel("Compatibility preset detected")
        self.profile_title.setObjectName("sectionTitle")
        self.profile_summary = _muted()
        self.profile_requirements = _muted()
        profile_copy.addWidget(self.profile_title)
        profile_copy.addWidget(self.profile_summary)
        profile_copy.addWidget(self.profile_requirements)
        profile_layout.addLayout(profile_copy, 1)
        self.apply_profile_button = _button("Apply recommended setup", primary=True)
        self.apply_profile_button.clicked.connect(self.apply_profile_recommendation)
        profile_layout.addWidget(self.apply_profile_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.profile_card.hide()
        layout.insertWidget(1, self.profile_card)

        compatibility = Card()
        compatibility_layout = QVBoxLayout(compatibility)
        compatibility_layout.setContentsMargins(20, 18, 20, 20)
        compatibility_layout.addLayout(
            _section_header(
                "Compatibility guidance",
                "Blockers, warnings, and useful runtime observations are kept together.",
            )
        )
        self.guidance_list = QListWidget()
        self.guidance_list.setMinimumHeight(150)
        self.guidance_list.addItem("Analyze an application to see compatibility guidance.")
        compatibility_layout.addWidget(self.guidance_list)
        layout.addWidget(compatibility)

        launch_card = Card()
        launch_layout = QVBoxLayout(launch_card)
        launch_layout.setContentsMargins(20, 18, 20, 20)
        launch_layout.addLayout(
            _section_header(
                "Launch",
                "Optional arguments use shell-style quoting; the app is not run through a shell.",
            )
        )
        launch_row = QHBoxLayout()
        self.arguments_input = QLineEdit()
        self.arguments_input.setPlaceholderText(
            'Optional arguments, e.g. --portable "C:\\My Files"'
        )
        self.arguments_input.returnPressed.connect(self.launch_application)
        self.launch_button = _button("Prepare and launch", accent=True)
        self.launch_button.clicked.connect(self.launch_application)
        launch_row.addWidget(self.arguments_input, 1)
        launch_row.addWidget(self.launch_button)
        launch_layout.addLayout(launch_row)
        layout.addWidget(launch_card)
        layout.addStretch(1)
        return scroll

    def _build_runtime_page(self) -> QWidget:
        scroll, _content, layout = self._scroll_page()
        self.runtime_scroll = scroll

        runtime_grid = QGridLayout()
        runtime_grid.setHorizontalSpacing(12)
        self.wine_metric = MetricCard("Wine")
        self.proton_metric = MetricCard("Proton")
        self.winetricks_metric = MetricCard("Winetricks")
        runtime_grid.addWidget(self.wine_metric, 0, 0)
        runtime_grid.addWidget(self.proton_metric, 0, 1)
        runtime_grid.addWidget(self.winetricks_metric, 0, 2)
        for column in range(3):
            runtime_grid.setColumnStretch(column, 1)
        layout.addLayout(runtime_grid)

        strategy = Card()
        strategy_layout = QVBoxLayout(strategy)
        strategy_layout.setContentsMargins(20, 18, 20, 20)
        strategy_layout.addLayout(
            _section_header(
                "Runtime strategy",
                "Automatic mode prefers Proton for games and Wine for desktop applications.",
            )
        )
        form = QFormLayout()
        form.setContentsMargins(0, 14, 0, 0)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Automatic (recommended)", "auto")
        self.backend_combo.addItem("Wine", "wine")
        self.backend_combo.addItem("Proton", "proton")
        self.backend_combo.currentIndexChanged.connect(self.runtime_options_changed)
        self.proton_combo = QComboBox()
        self.proton_combo.addItem("Best available build", None)
        self.proton_combo.currentIndexChanged.connect(self.runtime_options_changed)
        self.winver_combo = QComboBox()
        self.winver_combo.addItem("Runtime default", None)
        for version in ("11", "10", "8.1", "8", "7"):
            self.winver_combo.addItem(f"Windows {version}", version)
        self.winver_combo.currentIndexChanged.connect(self._runtime_setting_changed)
        self.winver_combo.setToolTip(
            "Controls the Windows version reported inside this application's isolated environment."
        )
        self.dependencies_combo = QComboBox()
        self.dependencies_combo.addItem("Automatic (Wine on / Proton off)", "auto")
        self.dependencies_combo.addItem("Install detected components", "install")
        self.dependencies_combo.addItem("Skip dependency changes", "skip")
        self.dependencies_combo.currentIndexChanged.connect(self._runtime_setting_changed)
        for combo in (
            self.backend_combo,
            self.proton_combo,
            self.winver_combo,
            self.dependencies_combo,
        ):
            combo.view().setAutoFillBackground(True)
            combo.view().viewport().setObjectName("comboPopupViewport")
            combo.view().viewport().setAutoFillBackground(True)
        form.addRow("Backend", self.backend_combo)
        form.addRow("Proton build", self.proton_combo)
        form.addRow("Windows version", self.winver_combo)
        form.addRow("Dependencies", self.dependencies_combo)
        strategy_layout.addLayout(form)
        layout.addWidget(strategy)

        environment = Card()
        environment_layout = QVBoxLayout(environment)
        environment_layout.setContentsMargins(20, 18, 20, 20)
        environment_layout.addLayout(
            _section_header(
                "Isolated environment",
                "Leave this empty for RunEXE's stable per-application location.",
            )
        )
        prefix_row = QHBoxLayout()
        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("Automatic per-application path")
        self.prefix_input.textChanged.connect(self._update_environment_preview)
        prefix_browse = _button("Choose folder")
        prefix_browse.clicked.connect(self.browse_prefix)
        prefix_row.addWidget(self.prefix_input, 1)
        prefix_row.addWidget(prefix_browse)
        environment_layout.addLayout(prefix_row)
        self.environment_preview = _muted(
            "Select and analyze an application to preview its environment."
        )
        self.environment_preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        environment_layout.addWidget(self.environment_preview)
        layout.addWidget(environment)

        actions = Card()
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(20, 18, 20, 20)
        actions_layout.addLayout(
            _section_header(
                "Setup actions",
                "Preparation creates or reuses the selected isolated environment "
                "without launching the app.",
            )
        )
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(10)
        action_grid.setVerticalSpacing(10)
        self.prepare_button = _button("Prepare automatically", primary=True)
        self.prepare_button.clicked.connect(self.prepare_selected_environment)
        self.wine_config_button = _button("Open Wine settings")
        self.wine_config_button.clicked.connect(lambda: self.open_runtime_settings("wine"))
        self.proton_config_button = _button("Open Proton settings")
        self.proton_config_button.clicked.connect(lambda: self.open_runtime_settings("proton"))
        self.refresh_button = _button("Refresh detection")
        self.refresh_button.clicked.connect(self.refresh_runtimes)
        action_grid.addWidget(self.prepare_button, 0, 0)
        action_grid.addWidget(self.refresh_button, 0, 1)
        action_grid.addWidget(self.wine_config_button, 1, 0)
        action_grid.addWidget(self.proton_config_button, 1, 1)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)
        actions_layout.addLayout(action_grid)
        layout.addWidget(actions)
        layout.addStretch(1)
        return scroll

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 14, 30, 30)
        layout.setSpacing(14)
        header = QHBoxLayout()
        titles = _section_header(
            "Session activity",
            "Output is kept in memory for this session and is never uploaded.",
        )
        header.addLayout(titles, 1)
        copy_button = _button("Copy")
        copy_button.clicked.connect(self.copy_activity)
        clear_button = _button("Clear")
        clear_button.clicked.connect(self.clear_activity)
        header.addWidget(copy_button)
        header.addWidget(clear_button)
        layout.addLayout(header)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.document().setMaximumBlockCount(3000)
        self.activity_log.setPlaceholderText("Analysis and runtime output will appear here.")
        layout.addWidget(self.activity_log, 1)
        return page

    def _create_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.browse_file)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.analyze_selected)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.launch_application)
        activity_action = QAction("Show activity", self)
        activity_action.setShortcut(QKeySequence("Ctrl+L"))
        activity_action.triggered.connect(lambda: self._show_page(2))
        self.addAction(activity_action)

    # ------------------------------------------------------------- State/UI
    def _show_page(self, index: int) -> None:
        if not 0 <= index < self.pages.count():
            return
        changed = self.pages.currentIndex() != index
        self.pages.setCurrentIndex(index)
        title, subtitle = self.PAGE_TITLES[index]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        if changed:
            self.pages.update()
            self._page_animation = QVariantAnimation(self)
            self._page_animation.setDuration(180)
            self._page_animation.setStartValue(QColor(COLORS["cyan"]))
            self._page_animation.setEndValue(QColor(COLORS["text"]))
            self._page_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._page_animation.valueChanged.connect(
                lambda color: self.page_title.setStyleSheet(f"color: {color.name()};")
            )
            self._page_animation.start()

    def _restore_settings(self) -> None:
        geometry = self.settings.value("window/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        self._select_combo_data(
            self.backend_combo, str(self.settings.value("runtime/backend", "auto"))
        )
        self._select_combo_data(
            self.dependencies_combo, str(self.settings.value("runtime/dependencies", "auto"))
        )
        saved_winver = self.settings.value("runtime/windows-version")
        if saved_winver:
            self._select_combo_data(self.winver_combo, str(saved_winver))
        self.prefix_input.setText(str(self.settings.value("runtime/prefix", "")))

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._workers:
            QMessageBox.information(
                self,
                "RunEXE is still working",
                "Wait for the current preparation task to finish before closing the window.",
            )
            event.ignore()
            return
        if self._application_running():
            answer = QMessageBox.question(
                self,
                "Application still running",
                "Closing RunEXE will also stop the launched application. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            assert self.application_process is not None
            self.application_process.kill()
            self.application_process.waitForFinished(3000)
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("runtime/backend", self.backend_combo.currentData())
        self.settings.setValue("runtime/dependencies", self.dependencies_combo.currentData())
        self.settings.setValue("runtime/windows-version", self.winver_combo.currentData())
        self.settings.setValue("runtime/prefix", self.prefix_input.text().strip())
        super().closeEvent(event)

    def _set_header_status(self, text: str, state: str) -> None:
        self.header_status.set_status(text, state)

    def _update_controls(self) -> None:
        busy = bool(self._workers)
        running = self._application_running()
        analyzed = self.executable is not None and self.compatibility is not None
        ready = analyzed and not self.compatibility.blocking_issues
        self.progress.setVisible(busy)
        self.analyze_button.setEnabled(self.drop_zone.path is not None and not busy)
        self.launch_button.setEnabled(bool(ready) and not busy and not running)
        self.prepare_button.setEnabled(bool(ready) and not busy and not running)
        self.refresh_button.setEnabled(not busy and not running)
        self.wine_config_button.setEnabled(
            analyzed and bool(self.host and self.host.wine_installed) and not busy and not running
        )
        self.proton_config_button.setEnabled(
            analyzed and bool(self.host and self.host.proton_installed) and not busy and not running
        )
        self.proton_combo.setEnabled(bool(self.proton_installations) and not busy)
        if running:
            self._set_header_status("Application running", "ready")
        elif busy:
            self._set_header_status("Working", "warning")
        elif ready:
            self._set_header_status("Ready to launch", "ready")
        elif analyzed:
            self._set_header_status("Action required", "error")
        elif self.host is not None:
            runtime_available = self.host.wine_installed or self.host.proton_installed
            self._set_header_status(
                "Runtimes detected" if runtime_available else "No runtime found",
                "ready" if runtime_available else "warning",
            )

    def _update_runtime_metrics(self) -> None:
        if self.host is None:
            return
        self.wine_metric.set_data(
            "Available" if self.host.wine_installed else "Not found",
            self.host.wine_version or "Install Wine to use this backend",
            "success" if self.host.wine_installed else "error",
        )
        proton_detail = (
            f"{len(self.proton_installations)} build(s) discovered"
            if self.proton_installations
            else "Install through Steam or add a custom build"
        )
        self.proton_metric.set_data(
            "Available" if self.proton_installations else "Not found",
            proton_detail,
            "success" if self.proton_installations else "error",
        )
        self.winetricks_metric.set_data(
            "Available" if self.host.winetricks_installed else "Optional",
            "Automatic dependencies enabled"
            if self.host.winetricks_installed
            else "Required only for detected extra components",
            "success" if self.host.winetricks_installed else "warning",
        )

    def _set_proton_installations(self, installations: list[ProtonInstallation]) -> None:
        selected = self.proton_combo.currentData()
        self.proton_combo.blockSignals(True)
        self.proton_combo.clear()
        self.proton_combo.addItem("Best available build", None)
        for installation in installations:
            label = installation.name
            if installation.version and installation.version not in installation.name:
                label += f"  ({installation.version})"
            self.proton_combo.addItem(label, str(installation.script))
        self.proton_combo.blockSignals(False)
        if selected:
            self._select_combo_data(self.proton_combo, selected)

    def _update_analysis_view(self) -> None:
        executable = self.executable
        report = self.compatibility
        if executable is None or report is None:
            return
        source = self.source_path or executable.path
        self.format_metric.set_data(executable.format or "Unknown", report.application_type)
        self.arch_metric.set_data(report.architecture, report.wine_arch or "Unsupported")
        self.runtime_metric.set_data(
            report.recommended_runtime,
            report.backend.upper(),
            "error" if report.blocking_issues else "neutral",
        )
        if report.blocking_issues:
            self.readiness_metric.set_data(
                "Blocked", f"{len(report.blocking_issues)} issue(s)", "error"
            )
        elif report.warnings:
            self.readiness_metric.set_data(
                "Review warnings", f"{len(report.warnings)} warning(s)", "warning"
            )
        else:
            self.readiness_metric.set_data("Ready", "No blocking issues detected", "success")

        product = "Unknown product"
        if executable.version_info:
            product = executable.version_info.strings.get("ProductName", product)
        if executable.package:
            product = executable.package.display_name or executable.package.identity_name
        self.detail_path.setText(str(source))
        self.detail_product.setText(product)
        self.detail_subsystem.setText(executable.subsystem or "Unknown")
        self.detail_dependencies.setText(
            ", ".join(item.name for item in report.dependencies) or "None detected"
        )

        self._update_profile_view(report)

        self.guidance_list.clear()
        for issue in report.blocking_issues:
            self.guidance_list.addItem(f"BLOCKED  {issue}")
        for warning in report.warnings:
            self.guidance_list.addItem(f"WARNING  {warning}")
        for note in report.notes:
            self.guidance_list.addItem(f"INFO  {note}")
        if self.guidance_list.count() == 0:
            self.guidance_list.addItem("No compatibility concerns were detected.")
        self.environment_status.setText(f"{report.backend.upper()} | {report.architecture}")
        self._update_environment_preview()
        self._update_controls()

    def _update_profile_view(self, report: CompatibilityReport) -> None:
        profile = report.profile
        if profile is None:
            self.profile_card.hide()
            return

        self.profile_title.setText(f"{profile.name} setup detected")
        self.profile_summary.setText(profile.summary)
        self.profile_requirements.setText("  •  ".join(profile.requirements))
        if (
            self.winver_combo.currentData() is None
            and profile.recommended_windows_version is not None
        ):
            self._select_combo_data(self.winver_combo, profile.recommended_windows_version)

        was_hidden = self.profile_card.isHidden()
        self.profile_card.show()
        self._update_profile_button()
        if was_hidden:
            target_height = self.profile_card.sizeHint().height()
            self.profile_card.setMaximumHeight(0)
            self._profile_animation = QPropertyAnimation(self.profile_card, b"maximumHeight", self)
            self._profile_animation.setDuration(220)
            self._profile_animation.setStartValue(0)
            self._profile_animation.setEndValue(target_height)
            self._profile_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._profile_animation.finished.connect(
                lambda: self.profile_card.setMaximumHeight(16777215)
            )
            self._profile_animation.start()

    def _update_profile_button(self) -> None:
        profile = self.compatibility.profile if self.compatibility is not None else None
        recommended = profile.recommended_windows_version if profile is not None else None
        applied = recommended is not None and self.winver_combo.currentData() == recommended
        if recommended is None:
            label = "Review requirements"
        elif applied:
            label = f"Review Windows {recommended} setup"
        else:
            label = f"Use Windows {recommended}"
        self.apply_profile_button.setText(label)
        self.apply_profile_button.setEnabled(recommended is not None)

    def _runtime_setting_changed(self) -> None:
        self.settings.setValue("runtime/windows-version", self.winver_combo.currentData())
        self.settings.setValue("runtime/dependencies", self.dependencies_combo.currentData())
        self._update_profile_button()
        self._update_environment_preview()

    def apply_profile_recommendation(self) -> None:
        if self.compatibility is None or self.compatibility.profile is None:
            return
        recommended = self.compatibility.profile.recommended_windows_version
        if recommended is not None:
            self._select_combo_data(self.winver_combo, recommended)
        self._show_page(1)
        self.runtime_scroll.verticalScrollBar().setValue(0)
        self.task_status.setText(f"Applied the {self.compatibility.profile.name} setup")

    def _update_environment_preview(self) -> None:
        if self.executable is None or self.compatibility is None:
            return
        custom = self.prefix_input.text().strip()
        if custom:
            path = Path(custom).expanduser()
        elif self.compatibility.backend == "proton":
            from runexe.proton import compat_data_path_for

            path = compat_data_path_for(self.executable.path)
        else:
            from runexe.runner import prefix_path_for

            path = prefix_path_for(self.executable)
        kind = "Proton compat data" if self.compatibility.backend == "proton" else "Wine prefix"
        winver = self.winver_combo.currentData()
        version_text = f"Windows {winver}" if winver else "runtime-default Windows version"
        self.environment_preview.setText(f"{kind}: {path}\nReports {version_text}")

    # -------------------------------------------------------------- Tasks
    def _start_task(self, key: str, label: str, function, on_result) -> None:
        if key in self._workers:
            return
        worker = Worker(function)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self._task_failed)
        worker.signals.finished.connect(lambda: self._task_finished(key))
        self._workers[key] = worker
        self.task_status.setText(label)
        self._log(label)
        self._update_controls()
        self.thread_pool.start(worker)

    def _task_failed(self, message: str, details: str) -> None:
        self._log(f"ERROR: {message}")
        self._log(details.rstrip())
        QMessageBox.critical(self, "RunEXE could not complete the action", message)

    def _task_finished(self, key: str) -> None:
        self._workers.pop(key, None)
        if not self._workers:
            self.task_status.setText("Ready")
        self._update_controls()

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.activity_log.appendPlainText(f"[{timestamp}] {message}")

    def _application_running(self) -> bool:
        return bool(
            self.application_process is not None
            and self.application_process.state() != QProcess.ProcessState.NotRunning
        )

    # ------------------------------------------------------------- Actions
    def browse_file(self) -> None:
        start = str(self.source_path.parent if self.source_path else Path.home())
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Windows software",
            start,
            "Windows software (*.exe *.appx *.msix *.appxbundle *.msixbundle);;All files (*)",
        )
        if selected:
            self.analyze_path(Path(selected))

    def browse_prefix(self) -> None:
        start = self.prefix_input.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Choose environment folder", start)
        if selected:
            self.prefix_input.setText(selected)

    def analyze_selected(self) -> None:
        if self.drop_zone.path is None:
            self.browse_file()
            return
        self.analyze_path(self.drop_zone.path)

    def analyze_path(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        self.source_path = resolved
        self.drop_zone.set_path(resolved)
        preference = str(self.backend_combo.currentData())

        def inspect() -> AnalysisBundle:
            executable = analyze_executable(resolved)
            if not executable.valid:
                raise ValueError(executable.reason or "Invalid Windows executable")
            host = detect_host()
            compatibility = analyze_compatibility(executable, host, preference)
            installations = discover_proton_installations()
            return AnalysisBundle(resolved, executable, host, compatibility, installations)

        self._start_task("analysis", f"Analyzing {resolved.name}", inspect, self._analysis_ready)

    def _analysis_ready(self, bundle: AnalysisBundle) -> None:
        self.source_path = bundle.source
        self.drop_zone.set_path(bundle.source)
        self.executable = bundle.executable
        self.host = bundle.host
        self.compatibility = bundle.compatibility
        self.proton_installations = bundle.proton_installations
        self._set_proton_installations(bundle.proton_installations)
        self._update_runtime_metrics()
        self._update_analysis_view()
        self._log(
            f"Analysis complete: {bundle.compatibility.architecture}, "
            f"{bundle.compatibility.backend}, "
            f"{len(bundle.compatibility.blocking_issues)} blocker(s)."
        )

    def refresh_runtimes(self) -> None:
        def detect() -> tuple[HostInfo, list[ProtonInstallation]]:
            return detect_host(), discover_proton_installations()

        self._start_task(
            "runtimes", "Refreshing Wine and Proton detection", detect, self._runtimes_ready
        )

    def _runtimes_ready(self, result: tuple[HostInfo, list[ProtonInstallation]]) -> None:
        self.host, self.proton_installations = result
        self._set_proton_installations(self.proton_installations)
        self._update_runtime_metrics()
        self.runtime_options_changed()
        self._log(
            "Runtime detection complete: "
            f"Wine={'yes' if self.host.wine_installed else 'no'}, "
            f"Proton={len(self.proton_installations)} build(s)."
        )

    def runtime_options_changed(self) -> None:
        self.settings.setValue("runtime/backend", self.backend_combo.currentData())
        if self.executable is not None and self.host is not None:
            self.compatibility = analyze_compatibility(
                self.executable, self.host, str(self.backend_combo.currentData())
            )
            self._update_analysis_view()

    def _selected_prefix(self) -> Path | None:
        value = self.prefix_input.text().strip()
        return Path(value) if value else None

    def _selected_proton(self) -> str | None:
        value = self.proton_combo.currentData()
        return str(value) if value else None

    def _install_dependencies(self, report: CompatibilityReport) -> bool:
        selection = self.dependencies_combo.currentData()
        if selection == "install":
            return True
        if selection == "skip":
            return False
        return report.backend == "wine"

    def _require_analysis(self) -> tuple[ExecutableInfo, CompatibilityReport] | None:
        if self.executable is None or self.compatibility is None:
            QMessageBox.information(self, "Select an application", "Analyze an application first.")
            self._show_page(0)
            return None
        return self.executable, self.compatibility

    def prepare_selected_environment(self) -> None:
        selected = self._require_analysis()
        if selected is None:
            return
        executable, report = selected

        def prepare() -> PreparedEnvironment:
            return prepare_environment(
                executable,
                report,
                prefix=self._selected_prefix(),
                install_dependencies=self._install_dependencies(report),
                proton=self._selected_proton(),
                winver=self.winver_combo.currentData(),
            )

        self._start_task("prepare", "Preparing isolated environment", prepare, self._prepared)

    def _prepared(self, prepared: PreparedEnvironment) -> None:
        self._log(
            f"Environment ready: {prepared.runtime_name} at {prepared.path} ({prepared.wine_arch})."
        )
        self.environment_status.setText(f"READY | {prepared.runtime_name}")
        self._set_header_status("Environment ready", "ready")

    def open_runtime_settings(self, backend: str) -> None:
        selected = self._require_analysis()
        if selected is None or self.host is None:
            return
        executable, _current_report = selected
        report = analyze_compatibility(executable, self.host, backend)
        if report.blocking_issues:
            QMessageBox.warning(self, "Runtime unavailable", "\n".join(report.blocking_issues))
            return

        def configure() -> PreparedEnvironment:
            return open_runtime_configuration(
                executable,
                report,
                prefix=self._selected_prefix(),
                proton=self._selected_proton() if backend == "proton" else None,
            )

        self._start_task(
            f"configure-{backend}",
            f"Opening {backend.title()} settings",
            configure,
            lambda prepared: self._log(
                f"Opened {prepared.runtime_name} settings for {prepared.path}."
            ),
        )

    def launch_application(self) -> None:
        selected = self._require_analysis()
        if selected is None:
            return
        executable, report = selected
        if report.blocking_issues:
            QMessageBox.warning(self, "Launch blocked", "\n".join(report.blocking_issues))
            return
        try:
            arguments = shlex.split(self.arguments_input.text())
        except ValueError as error:
            QMessageBox.warning(self, "Invalid arguments", str(error))
            return

        def prepare() -> PreparedEnvironment:
            return prepare_environment(
                executable,
                report,
                winver=self.winver_combo.currentData(),
                prefix=self._selected_prefix(),
                install_dependencies=self._install_dependencies(report),
                proton=self._selected_proton(),
            )

        self._start_task(
            "launch",
            f"Preparing {executable.path.name}",
            prepare,
            lambda prepared: self._start_application(executable, prepared, arguments),
        )

    def _start_application(
        self,
        executable: ExecutableInfo,
        prepared: PreparedEnvironment,
        arguments: list[str],
    ) -> None:
        spec = build_launch_spec(executable, prepared, arguments)
        process = QProcess(self)
        process.setProgram(spec.command[0])
        process.setArguments(list(spec.command[1:]))
        process.setWorkingDirectory(str(spec.cwd))
        environment = QProcessEnvironment()
        for name, value in spec.env.items():
            environment.insert(name, value)
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(self._read_application_stdout)
        process.readyReadStandardError.connect(self._read_application_stderr)
        process.started.connect(self._application_started)
        process.finished.connect(self._application_finished)
        process.errorOccurred.connect(self._application_error)
        self.application_process = process
        self._application_output.clear()
        process.start()
        self._update_controls()

    def _read_application_stdout(self) -> None:
        if self.application_process is None:
            return
        output = bytes(self.application_process.readAllStandardOutput()).decode(errors="replace")
        if output:
            self._application_output.append(output)
            self._log("Application output:\n" + output.rstrip())

    def _read_application_stderr(self) -> None:
        if self.application_process is None:
            return
        output = bytes(self.application_process.readAllStandardError()).decode(errors="replace")
        if output:
            self._application_output.append(output)
            self._log("Application errors:\n" + output.rstrip())

    def _application_started(self) -> None:
        assert self.executable is not None
        self._log(f"Application started: {self.executable.path.name}")
        self.task_status.setText("Application is running")
        self._update_controls()

    def _application_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._read_application_stdout()
        self._read_application_stderr()
        self._log(f"Application exited with code {exit_code}.")
        diagnostic = detect_runtime_issue(
            "\n".join(self._application_output),
            exit_code,
            self.compatibility.profile if self.compatibility is not None else None,
        )
        self.application_process = None
        self.task_status.setText("Ready")
        if diagnostic is not None:
            self._log(f"DETECTED: {diagnostic.message}")
            if diagnostic.recommended_windows_version is not None:
                self._select_combo_data(self.winver_combo, diagnostic.recommended_windows_version)
            if self.compatibility is not None and self.compatibility.profile is not None:
                self.profile_summary.setText(diagnostic.message)
                self.profile_card.show()
            self._show_page(0)
            QTimer.singleShot(
                180, lambda: self.overview_scroll.ensureWidgetVisible(self.profile_card, 24, 24)
            )
            self.task_status.setText(diagnostic.title)
            self._update_controls()
            self._set_header_status(diagnostic.title, "warning")
            return
        self._set_header_status(
            "Launch completed" if exit_code == 0 else "Application failed",
            "ready" if exit_code == 0 else "error",
        )
        self._update_controls()

    def _application_error(self, error: QProcess.ProcessError) -> None:
        if self.application_process is None:
            return
        self._log(f"Application process error: {self.application_process.errorString()}")
        if error == QProcess.ProcessError.FailedToStart:
            QMessageBox.critical(
                self,
                "Could not start application",
                self.application_process.errorString(),
            )
            self.application_process.deleteLater()
            self.application_process = None
            self.task_status.setText("Ready")
            self._set_header_status("Application failed", "error")
            self._update_controls()

    def copy_activity(self) -> None:
        QApplication.clipboard().setText(self.activity_log.toPlainText())
        self.task_status.setText("Activity copied to clipboard")

    def clear_activity(self) -> None:
        self.activity_log.clear()
        self.task_status.setText("Activity cleared")


def run_gui(initial_file: Path | None = None) -> int:
    """Create the Qt application and display the main window."""

    app = QApplication.instance()
    owns_application = app is None
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("RunEXE")
    app.setApplicationDisplayName("RunEXE")
    app.setOrganizationName("RunEXE")
    apply_theme(app)

    window = RunEXEWindow(initial_file)
    window.show()
    if owns_application:
        return app.exec()
    return 0
