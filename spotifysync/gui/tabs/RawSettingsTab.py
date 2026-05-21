import json
import re

from PyQt6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtCore import pyqtSignal

from ... import sync as SpotifySync


class _JsonHighlighter(QSyntaxHighlighter):
    _STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')
    _NUMBER = re.compile(r'\b-?\d+\.?\d*(?:[eE][+-]?\d+)?\b')
    _KEYWORD = re.compile(r'\b(?:true|false|null)\b')
    _KEY = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"(?=\s*:)')

    def __init__(self, parent):
        super().__init__(parent)
        self._fmt_string = self._fmt("#CE9178")
        self._fmt_number = self._fmt("#B5CEA8")
        self._fmt_keyword = self._fmt("#569CD6")
        self._fmt_key = self._fmt("#9CDCFE")

    @staticmethod
    def _fmt(color: str) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        return f

    def highlightBlock(self, text: str | None):  # type: ignore[override]
        if text is None:
            return
        for m in self._STRING.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_string)
        for m in self._NUMBER.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_number)
        for m in self._KEYWORD.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_keyword)
        # keys override the string colour applied above
        for m in self._KEY.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_key)


class RawSettingsTab(QWidget):
    settings_reloaded = pyqtSignal()

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        self._warn = QLabel(
            "Direct edits bypass all validation. Invalid JSON will be rejected on save."
        )
        self._warn.setWordWrap(True)
        self._warn.setStyleSheet("color:#FFC947;font-size:11px;")
        lay.addWidget(self._warn)

        self._editor = QPlainTextEdit()
        self._editor.setFont(self._editor.font())
        self._editor.setStyleSheet(
            "background:#1a1a1a;color:#D4D4D4;font-family:monospace;font-size:12px;"
            "border:1px solid #333;border-radius:4px;"
        )
        self._highlighter = _JsonHighlighter(self._editor.document())
        lay.addWidget(self._editor)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

    def _load(self):
        display = {k: v for k, v in self._settings.items() if k != "filename"}
        self._editor.setPlainText(json.dumps(display, indent=2))

    def _save(self):
        text = self._editor.toPlainText()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            self._warn.setText(f"Invalid JSON — {e}")
            self._warn.setStyleSheet("color:#E63946;font-size:11px;")
            return
        filename = self._settings.get("filename", "data/settings.json")
        self._settings.clear()
        self._settings.update(parsed)
        self._settings["filename"] = filename
        SpotifySync.save_settings(self._settings)
        self._warn.setText(
            "Direct edits bypass all validation. Invalid JSON will be rejected on save."
        )
        self._warn.setStyleSheet("color:#FFC947;font-size:11px;")
        self.settings_reloaded.emit()

    def reload(self):
        self._load()

    def update_settings(self, settings: dict):
        self._settings = settings
        self._load()
