from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSignal

from .GeneralTab import GeneralTab
from .NotificationsTab import NotificationsTab
from .RawSettingsTab import RawSettingsTab


class SettingsTab(QWidget):
    settings_changed = pyqtSignal(bool)
    expert_mode_changed = pyqtSignal(bool)

    def __init__(self, settings: dict, cache: dict):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("innerTabs")
        self._general = GeneralTab(settings, cache)
        self._notifications = NotificationsTab(settings)
        self._raw = RawSettingsTab(settings)

        self._notifications.settings_changed.connect(self.settings_changed)
        self._general.expert_mode_changed.connect(self._on_expert_mode)
        self._general.expert_mode_changed.connect(self.expert_mode_changed)

        self._tabs.addTab(self._general, "General")
        self._tabs.addTab(self._notifications, "Notifications")
        self._tabs.addTab(self._raw, "Raw Settings")
        self._raw_idx = self._tabs.count() - 1
        self._tabs.setTabVisible(self._raw_idx, settings.get("expert_mode", False))
        self._tabs.currentChanged.connect(self._on_tab_changed)
        lay.addWidget(self._tabs)

    def _on_expert_mode(self, enabled: bool):
        self._tabs.setTabVisible(self._raw_idx, enabled)

    def _on_tab_changed(self, index: int):
        if index == self._raw_idx:
            self._raw.reload()

    def refresh_cache_info(self):
        self._general.refresh_cache_info()

    def update_settings(self, settings: dict):
        self._general.update_settings(settings)
        self._notifications.update_settings(settings)
        self._raw.update_settings(settings)
