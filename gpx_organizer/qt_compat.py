"""Qt binding compatibility layer.

Prefers PyQt6 on Debian/Raspberry Pi Bookworm for reliable QtWebEngine runtime
compatibility, and falls back to PySide6 where PyQt6 is not available.
"""

from __future__ import annotations

QT_BINDING = ""

try:
    from PyQt6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, pyqtSignal as Signal
    from PyQt6.QtGui import QColor, QDrag, QIcon, QPainter, QPixmap
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
        QProgressDialog,
        QProgressBar,
        QScrollArea,
        QPushButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QStyle,
        QTabWidget,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    try:
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except ImportError:  # pragma: no cover - optional runtime component
        QWebEngineView = None  # type: ignore[assignment]
        QWebEngineSettings = None  # type: ignore[assignment]

    QT_BINDING = "PyQt6"
except ImportError:
    from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
    from PySide6.QtGui import QColor, QDrag, QIcon, QPainter, QPixmap
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
        QProgressDialog,
        QProgressBar,
        QScrollArea,
        QPushButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QStyle,
        QTabWidget,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    try:
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:  # pragma: no cover - optional runtime component
        QWebEngineView = None  # type: ignore[assignment]
        QWebEngineSettings = None  # type: ignore[assignment]

    QT_BINDING = "PySide6"


__all__ = [
    "QApplication",
    "QCheckBox",
    "QColor",
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
    "QIcon",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMenu",
    "QMessageBox",
    "QMimeData",
    "QObject",
    "QPoint",
    "QProgressDialog",
    "QProgressBar",
    "QScrollArea",
    "QPainter",
    "QPixmap",
    "QPushButton",
    "QSpinBox",
    "QSplitter",
    "QStatusBar",
    "QStyle",
    "QTabWidget",
    "QTimer",
    "QUrl",
    "QTreeWidget",
    "QTreeWidgetItem",
    "QVBoxLayout",
    "QWebEngineView",
    "QWebEngineSettings",
    "QWidget",
    "Qt",
    "Signal",
    "QT_BINDING",
]
