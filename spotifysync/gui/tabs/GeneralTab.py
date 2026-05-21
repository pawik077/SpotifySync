import os

from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import sync as SpotifySync


class GeneralTab(QWidget):
    def __init__(self, settings: dict, cache: dict):
        super().__init__()
        self._settings = settings
        self._cache = cache
        self._build_ui()
        self.refresh_cache_info()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        lay.addWidget(QLabel("Cache"))

        self._cache_info = QLabel()
        self._cache_info.setStyleSheet("color:#B3B3B3;font-size:12px;")
        lay.addWidget(self._cache_info)

        self._use_cache_cb = QCheckBox("Use cache")
        self._use_cache_cb.setChecked(self._settings.get("use_cache", True))
        self._use_cache_cb.toggled.connect(self._on_use_cache_toggled)
        lay.addWidget(self._use_cache_cb)

        btn_row = QHBoxLayout()
        self._prune_btn = QPushButton("Prune")
        self._clear_btn = QPushButton("Clear")
        for b in (self._prune_btn, self._clear_btn):
            b.setObjectName("small")
            btn_row.addWidget(b)
        btn_row.addStretch()
        self._prune_btn.clicked.connect(self._prune_cache)
        self._clear_btn.clicked.connect(self._clear_cache)
        lay.addLayout(btn_row)

        lay.addStretch()

    def refresh_cache_info(self):
        count = len(self._cache.get("metadata", {}))
        try:
            size = os.path.getsize("data/cache.json")
            size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
        except FileNotFoundError:
            size_str = "0 B"
        noun = "playlist" if count == 1 else "playlists"
        self._cache_info.setText(f"{count} {noun} cached · {size_str}")

    def _on_use_cache_toggled(self, checked: bool):
        self._settings["use_cache"] = checked
        SpotifySync.save_settings(self._settings)

    def _prune_cache(self):
        active = set(self._settings.get("playlists", []))
        merge = self._settings.get("merge_playlist", "")
        if merge:
            active.add(merge)
        for section in ("metadata", "contents"):
            stale = set(self._cache.get(section, {}).keys()) - active
            for pid in stale:
                del self._cache[section][pid]
        SpotifySync.save_cache(self._cache)
        self.refresh_cache_info()

    def _clear_cache(self):
        self._cache.clear()
        SpotifySync.save_cache(self._cache)
        self.refresh_cache_info()

    def update_settings(self, settings: dict):
        self._settings = settings
