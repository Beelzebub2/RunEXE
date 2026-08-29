"""Reusable background-task primitives for the Qt interface."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str, str)
    finished = Signal()


class Worker(QRunnable):
    """Execute one callable without blocking Qt's event loop."""

    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as error:  # noqa: BLE001 - failures are forwarded to the UI thread
            self.signals.error.emit(str(error) or error.__class__.__name__, traceback.format_exc())
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
