from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import pyqtSignal

from ...api import SyncSummary, Track, Playlist
from ...notifier import Verbosity, notify
from ... import sync as SpotifySync

import importlib.util
_APPRISE_AVAILABLE = importlib.util.find_spec("apprise") is not None

_VERBOSITY_LABELS = ["Short", "Medium", "Full"]


class NotificationsTab(QWidget):
    settings_changed = pyqtSignal(bool)

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings
        self._dirty = False
        self._build_ui()
        self._load_table()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        lay.addWidget(QLabel("Notification Services"))

        if not _APPRISE_AVAILABLE:
            warn = QLabel("Apprise is not installed — notifications will not be sent. Install it with: pip install apprise")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#FFC947;font-size:11px;")
            lay.addWidget(warn)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["URL", "Verbosity"])
        hdr = self._table.horizontalHeader()
        assert hdr is not None
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 110)
        vhr = self._table.verticalHeader()
        assert vhr is not None
        vhr.setDefaultSectionSize(32)
        vhr.setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._table.itemChanged.connect(self._mark_dirty)
        lay.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._remove_btn = QPushButton("− Remove")
        self._test_btn = QPushButton("Test")
        for b in (self._add_btn, self._remove_btn, self._test_btn):
            b.setObjectName("small")
            btn_row.addWidget(b)
        btn_row.addStretch()
        self._add_btn.clicked.connect(self._add_row)
        self._remove_btn.clicked.connect(self._remove_row)
        self._test_btn.clicked.connect(self._test_notify)
        self._test_btn.setEnabled(_APPRISE_AVAILABLE)
        lay.addLayout(btn_row)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

    def _make_verbosity_combo(self, value: int = Verbosity.FULL) -> QComboBox:
        combo = QComboBox()
        combo.addItems(_VERBOSITY_LABELS)
        combo.setCurrentIndex(value)
        combo.currentIndexChanged.connect(self._mark_dirty)
        return combo

    def _load_table(self):
        for entry in self._settings.get("notify_urls", []):
            url = entry.get("url", "")
            verbosity = entry.get("verbosity", Verbosity.FULL)
            self._append_row(url, verbosity)

    def _append_row(self, url: str = "", verbosity: int = Verbosity.FULL):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.blockSignals(True)
        self._table.setItem(row, 0, QTableWidgetItem(url))
        self._table.blockSignals(False)
        self._table.setCellWidget(row, 1, self._make_verbosity_combo(verbosity))

    def _add_row(self):
        self._append_row()
        self._mark_dirty()

    def _remove_row(self):
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if rows:
            for row in rows:
                self._table.removeRow(row)
            self._mark_dirty()

    def _collect_urls(self) -> list[dict]:
        urls = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None:
                continue
            url = item.text().strip()
            if not url:
                continue
            combo = self._table.cellWidget(row, 1)
            if not isinstance(combo, QComboBox):
                continue
            verbosity = combo.currentIndex()
            urls.append({"url": url, "verbosity": verbosity})
        return urls

    def _test_notify(self):
        dummy = SyncSummary()
        dummy.added.append(
            (
                Track(title="Test Track", artist="Test Artist", uri=""),
                Playlist(id="test", name="Test Playlist"),
            )
        )
        notify(dummy, self._collect_urls() or self._settings.get("notify_urls", []))

    def _mark_dirty(self, *_):
        if not self._dirty:
            self._dirty = True
            self.settings_changed.emit(True)

    def _save(self):
        self._settings["notify_urls"] = self._collect_urls()
        SpotifySync.save_settings(self._settings)
        self._dirty = False
        self.settings_changed.emit(False)

    def update_settings(self, settings: dict):
        self._settings = settings
