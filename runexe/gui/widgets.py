"""Small reusable widgets shared by RunEXE desktop pages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QScroller,
    QVBoxLayout,
    QWidget,
)


class SmoothScrollArea(QScrollArea):
    """A touch-friendly scroll area with short, interruptible wheel easing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAutoFillBackground(True)
        self.viewport().setObjectName("scrollViewport")
        self.viewport().setAutoFillBackground(True)
        self.verticalScrollBar().setSingleStep(36)
        self._scroll_target = 0
        self._scroll_animation = QVariantAnimation(self)
        self._scroll_animation.setDuration(170)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_animation.valueChanged.connect(
            lambda value: self.verticalScrollBar().setValue(int(value))
        )
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.TouchGesture)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        pixel_delta = event.pixelDelta().y()
        angle_delta = event.angleDelta().y()
        if pixel_delta:
            distance = -pixel_delta
        elif angle_delta:
            distance = int(-angle_delta / 120 * 108)
        else:
            super().wheelEvent(event)
            return

        bar = self.verticalScrollBar()
        if self._scroll_animation.state() != QAbstractAnimation.State.Running:
            self._scroll_target = bar.value()
        self._scroll_target = max(bar.minimum(), min(bar.maximum(), self._scroll_target + distance))
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(self._scroll_target)
        self._scroll_animation.start()
        event.accept()


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)


class MetricCard(QFrame):
    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("metric", True)
        self._color_animation = QVariantAnimation(self)
        self._color_animation.setDuration(180)
        self._color_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(5)
        self.caption = QLabel(caption)
        self.caption.setProperty("muted", True)
        self.value = QLabel("Not analyzed")
        self.value.setObjectName("metricValue")
        self.value.setWordWrap(True)
        self._color_animation.valueChanged.connect(
            lambda color: self.value.setStyleSheet(f"color: {color.name()};")
        )
        self.detail = QLabel("Select Windows software to begin")
        self.detail.setProperty("muted", True)
        self.detail.setWordWrap(True)
        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_data(self, value: str, detail: str = "", state: str = "neutral") -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.value.setProperty("metricState", state)
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)
        colors = {
            "success": QColor("#41d98a"),
            "warning": QColor("#ffb21a"),
            "error": QColor("#ff6577"),
            "neutral": QColor("#16d9ff"),
        }
        self._color_animation.stop()
        self._color_animation.setStartValue(QColor("#91a2bd"))
        self._color_animation.setEndValue(colors.get(state, colors["neutral"]))
        self._color_animation.start()


class StatusPill(QLabel):
    def __init__(self, text: str = "Not checked", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_status(text, "warning")

    def set_status(self, text: str, state: str) -> None:
        self.setText(text)
        self.setProperty("status", state)
        self.style().unpolish(self)
        self.style().polish(self)


class DropZone(QFrame):
    file_selected = Signal(str)
    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Application file picker")
        self.setMinimumHeight(150)
        self._path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(7)
        self.title = QLabel("Drop an EXE, AppX, or MSIX here")
        self.title.setObjectName("sectionTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel("or click to browse your files")
        self.subtitle.setProperty("muted", True)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(False)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    @property
    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: Path) -> None:
        self._path = path
        self.title.setText(path.name)
        self.setToolTip(str(path))
        self._refresh_path_text(self.size())

    def _refresh_path_text(self, size: QSize) -> None:
        if self._path is None:
            return
        available = max(120, size.width() - 80)
        self.subtitle.setText(
            self.subtitle.fontMetrics().elidedText(
                str(self._path), Qt.TextElideMode.ElideMiddle, available
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        self._refresh_path_text(event.size())
        super().resizeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 - Qt API
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        local = next(
            (url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()), ""
        )
        if local:
            self.setProperty("dragActive", False)
            self.style().unpolish(self)
            self.style().polish(self)
            self.file_selected.emit(local)
            event.acceptProposedAction()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.browse_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
