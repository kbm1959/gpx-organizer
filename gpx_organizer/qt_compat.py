"""Qt binding compatibility layer.

Prefers PyQt6 on Debian/Raspberry Pi Bookworm for reliable QtWebEngine runtime
compatibility, and falls back to PySide6 where PyQt6 is not available.
"""

from __future__ import annotations

QT_BINDING = ""

try:
    from PyQt6.QtCore import QEvent, QMimeData, QPoint, Qt, QTimer, pyqtSignal as Signal
    from PyQt6.QtGui import QDrag
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGridLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QTabWidget,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except ImportError:  # pragma: no cover - optional runtime component
        QWebEngineView = None  # type: ignore[assignment]

    QT_BINDING = "PyQt6"
except ImportError:
    from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt, QTimer, Signal
    from PySide6.QtGui import QDrag
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGridLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QTabWidget,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:  # pragma: no cover - optional runtime component
        QWebEngineView = None  # type: ignore[assignment]

    QT_BINDING = "PySide6"


__all__ = [
    "QApplication",
    "QCheckBox",
    "QColorDialog",
    "QComboBox",
    "QDialog",
    "QDialogButtonBox",
    "QDoubleSpinBox",
    "QDrag",
    "QEvent",
    "QFileDialog",
    "QFormLayout",
    "QGridLayout",
    "QHBoxLayout",
    "QInputDialog",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMenu",
    "QMessageBox",
    "QMimeData",
    "QPoint",
    "QPushButton",
    "QSpinBox",
    "QSplitter",
    "QStatusBar",
    "QTabWidget",
    "QTimer",
    "QTreeWidget",
    "QTreeWidgetItem",
    "QVBoxLayout",
    "QWebEngineView",
    "QWidget",
    "Qt",
    "Signal",
    "QT_BINDING",
]
