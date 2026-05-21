import sys
import json
import os
import logging

from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .tabs import AuthTab, LogTab, PlaylistsTab, SettingsTab
from ._helpers import make_auth_key
from .workers import StatusDot, SyncThread
from ..utils import setup_logger
from .. import sync as SpotifySync
from .. import api as SpotifyApi

SETTINGS_FILE = "data/settings.json"
CACHE_FILE = "data/cache.json"

logger = logging.getLogger("SpotifySync")


def load_settings(filename: str = SETTINGS_FILE) -> dict:
    _defaults: dict = {
        "access_token": "",
        "refresh_token": "",
        "client_id": "",
        "expires_at": 0,
        "playlists": [],
        "merge_playlist": "",
        "filename": SETTINGS_FILE,
    }
    try:
        with open(filename, "r") as s:
            return json.load(s)
    except FileNotFoundError:
        logger.warning(
            "Error while reading settings file - settings file not found - creating new"
        )
        return _defaults
    except json.JSONDecodeError:
        logger.error("Error while reading settings file - JSON decoding failed")
        retval = QMessageBox.warning(
            None,
            "Warning: Malformed settings file",
            "The settings file cannot be parsed. Should a clean one be created?",
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
        )
        if retval == QMessageBox.StandardButton.No:
            sys.exit(1)
        logger.warning(
            "Error while reading settings file - JSON decoding failed - creating new"
        )
        return _defaults


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpotifySync")
        self.setMinimumSize(640, 540)
        os.makedirs("data", exist_ok=True)
        setup_logger("data/sync.log")
        self._settings = load_settings()
        self._cache = SpotifySync.load_cache(CACHE_FILE)
        self._sync_thread = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        central = QWidget()
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        self._tabs = QTabWidget()
        self._auth_tab = AuthTab(self._settings)
        self._playlists_tab = PlaylistsTab(self._settings, self._cache)
        self._log_tab = LogTab()
        self._settings_tab = SettingsTab(self._settings, self._cache)

        self._auth_tab.authenticated.connect(self._on_authenticated)
        self._auth_tab.token_cleared.connect(self._on_token_cleared)
        self._auth_tab.user_changed.connect(self._playlists_tab.set_user)
        self._playlists_tab.settings_changed.connect(self._on_settings_changed)
        self._settings_tab.settings_changed.connect(self._on_settings_changed)
        self._settings_tab.expert_mode_changed.connect(self._playlists_tab.set_expert_mode)

        self._tabs.addTab(self._auth_tab, "Authentication")
        self._tabs.addTab(self._playlists_tab, "Playlists")
        self._tabs.addTab(self._log_tab, "Log")
        self._tabs.addTab(self._settings_tab, "Settings")

        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 8, 12, 8)

        self._sync_btn = QPushButton("Run Sync")
        self._sync_btn.clicked.connect(self._run_sync)
        self._sync_status = QLabel("Ready")
        self._sync_status.setStyleSheet("color:#B3B3B3;")
        self._sync_dot = StatusDot("green")

        bar_lay.addWidget(self._sync_btn)
        bar_lay.addStretch()
        bar_lay.addWidget(self._sync_status)
        bar_lay.addSpacing(8)
        bar_lay.addWidget(self._sync_dot)

        main_lay.addWidget(self._tabs)
        main_lay.addWidget(bar)
        self.setCentralWidget(central)

    def _on_settings_changed(self, dirty: bool):
        self._sync_btn.setEnabled(not dirty)
        if dirty:
            self._sync_status.setText("Save settings before syncing")
            self._sync_dot.set_color("grey")

    def _on_authenticated(self, access_token: str, refresh_token: str, expires_at: int):
        self._settings["access_token"] = access_token
        self._settings["refresh_token"] = refresh_token
        self._settings["expires_at"] = expires_at
        SpotifySync.save_settings(self._settings)
        self._playlists_tab.set_auth_key(make_auth_key(access_token))
        self._playlists_tab.update_settings(self._settings)

    def _on_token_cleared(self):
        self._settings["access_token"] = ""
        self._settings["refresh_token"] = ""
        self._settings["expires_at"] = 0
        SpotifySync.save_settings(self._settings)
        self._playlists_tab.set_auth_key("")
        self._playlists_tab.update_settings(self._settings)

    def _run_sync(self):
        if self._sync_thread and self._sync_thread.isRunning():
            return
        self._sync_btn.setEnabled(False)
        self._sync_dot.set_color("yellow")
        self._sync_status.setText("Syncing…")
        self._sync_thread = SyncThread()
        self._sync_thread.success.connect(self._on_sync_ok)
        self._sync_thread.failed.connect(self._on_sync_failed)
        self._sync_thread.start()

    def _on_sync_ok(self, summary: SpotifyApi.SyncSummary):
        self._cache.update(SpotifySync.load_cache(CACHE_FILE))
        self._settings_tab.refresh_cache_info()
        self._sync_btn.setEnabled(True)
        self._sync_dot.set_color("green")

        parts = [
            f"{len(items)} {name}"
            for name in ("added", "removed", "reordered", "warnings")
            if (items := getattr(summary, name))
        ]
        self._sync_status.setText(
            "Sync complete" + (f" - {', '.join(parts)}" if parts else "")
        )

    def _on_sync_failed(self, message: str):
        self._sync_btn.setEnabled(True)
        self._sync_dot.set_color("red")
        self._sync_status.setText(f"Sync failed: {message}")

    def closeEvent(self, a0):
        SpotifySync.save_cache(self._cache, CACHE_FILE)
        super().closeEvent(a0)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #121212;
                color: #FFFFFF;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1DB954;
                color: #000000;
                border: none;
                border-radius: 20px;
                padding: 8px 20px;
                font-weight: 600;
                min-width: 80px;
            }
            QPushButton:hover    { background-color: #1ed760; }
            QPushButton:pressed  { background-color: #169c47; }
            QPushButton:disabled { background-color: #333333; color: #666666; }
            QPushButton#secondary {
                background-color: transparent;
                color: #B3B3B3;
                border: 1px solid #535353;
            }
            QPushButton#secondary:hover { color: #FFFFFF; border-color: #FFFFFF; }
            QPushButton#small {
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: normal;
                min-width: 0;
            }
            QTabWidget::pane    { border: none; background: #121212; }
            QTabBar::tab {
                background: #121212;
                color: #B3B3B3;
                padding: 10px 24px;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected { color: #FFFFFF; border-bottom-color: #1DB954; }
            QTabBar::tab:hover    { color: #FFFFFF; }
            #innerTabs::pane { border: none; background: #121212; }
            #innerTabs QTabBar::tab {
                padding: 6px 16px;
                font-size: 12px;
                border-bottom: 1px solid transparent;
            }
            #innerTabs QTabBar::tab:selected { border-bottom-color: #1DB954; }
            QTableWidget {
                background-color: #181818;
                border: none;
                gridline-color: transparent;
                outline: none;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #282828;
            }
            QTableWidget::item:selected {
                background-color: #282828;
                color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #121212;
                color: #B3B3B3;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #282828;
                font-weight: 600;
                font-size: 11px;
                text-transform: uppercase;
            }
            QLineEdit {
                background-color: #282828;
                color: #FFFFFF;
                border: 1px solid #3E3E3E;
                border-radius: 4px;
                padding: 8px;
            }
            QLineEdit:focus { border-color: #1DB954; }
            QTableWidget QLineEdit {
                padding: 2px 6px;
                border-radius: 0;
            }
            QComboBox {
                background-color: #282828;
                color: #FFFFFF;
                border: none;
                padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background-color: #282828;
                color: #FFFFFF;
                selection-background-color: #1DB954;
                selection-color: #000000;
                outline: none;
            }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border-radius: 3px;
                border: 1px solid #535353;
                background: #282828;
            }
            QCheckBox::indicator:checked {
                background-color: #1DB954;
                border-color: #1DB954;
            }
            QCheckBox::indicator:hover { border-color: #B3B3B3; }
            QListWidget {
                background-color: #181818;
                border: 1px solid #282828;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #282828;
            }
            QListWidget::item:hover    { background-color: #282828; }
            QListWidget::item:selected { background-color: #1DB954; color: #000000; }
            QDialog { background-color: #121212; }
            QScrollBar:vertical {
                background: #121212; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #535353; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            #bottomBar {
                background-color: #181818;
                border-top: 1px solid #282828;
            }
        """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SpotifySync")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
