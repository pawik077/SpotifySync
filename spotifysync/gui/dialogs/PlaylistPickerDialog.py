from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

from ..workers import BatchCoverThread, FetchPlaylistsThread
from .._helpers import COVER_SIZE, ROW_HEIGHT, _format_owner
from ... import api as SpotifyAPI


class PlaylistPickerDialog(QDialog):
    def __init__(
        self,
        auth_key: str,
        existing_ids: set,
        single_select: bool = False,
        current_id: str = "",
        user_id: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._auth_key = auth_key
        self._existing_ids = existing_ids
        self._single_select = single_select
        self._current_id = current_id
        self._user_id = user_id
        self._all_playlists: list = []
        self._covers: dict = {}
        self._fetch_thread = None
        self._cover_thread = None

        self.setWindowTitle("Select Playlist" if single_select else "Add Playlists")
        self.setMinimumSize(480, 520)
        self._build_ui()
        self._fetch()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search playlists…")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._loading = QLabel("Loading…")
        self._loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading.setStyleSheet("color:#B3B3B3;padding:40px;")
        lay.addWidget(self._loading)

        self._list = QListWidget()
        self._list.setIconSize(QSize(COVER_SIZE, COVER_SIZE))
        self._list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
            if self._single_select
            else QAbstractItemView.SelectionMode.NoSelection
        )
        self._list.setSpacing(2)
        self._list.hide()
        lay.addWidget(self._list)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        self._confirm = QPushButton("Select" if self._single_select else "Add")
        self._confirm.setEnabled(False)
        self._confirm.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(self._confirm)
        lay.addLayout(btns)

    def _fetch(self):
        self._fetch_thread = FetchPlaylistsThread(self._auth_key)
        self._fetch_thread.success.connect(self._on_loaded)
        self._fetch_thread.failed.connect(
            lambda e: self._loading.setText(f"Error loading playlists:\n{e}")
        )
        self._fetch_thread.start()

    def _on_loaded(self, playlists: list[SpotifyAPI.Playlist]):
        if self._single_select and self._user_id:
            playlists = [
                pl
                for pl in playlists
                if pl.owner is None
                or pl.collaborative is None
                or pl.owner.id == self._user_id
                or pl.collaborative
            ]
        self._all_playlists = playlists
        self._loading.hide()
        self._list.show()
        self._populate(playlists)
        self._confirm.setEnabled(True)
        self._cover_thread = BatchCoverThread(playlists)
        self._cover_thread.loaded.connect(self._on_cover)
        self._cover_thread.start()

    def _populate(self, playlists: list):
        self._list.clear()
        for pl in playlists:
            owner_str = _format_owner(pl.owner, self._user_id)
            text = f"  {pl.name}\n  {owner_str}" if owner_str else f"  {pl.name}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, pl)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            if pl.id in self._covers:
                item.setIcon(QIcon(self._covers[pl.id]))
            if not self._single_select:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                already = pl.id in self._existing_ids
                item.setCheckState(
                    Qt.CheckState.Checked if already else Qt.CheckState.Unchecked
                )
                if already:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._list.addItem(item)
            if self._single_select and pl.id == self._current_id:
                item.setSelected(True)

    def _filter(self, text: str):
        q = text.lower()
        self._populate([p for p in self._all_playlists if q in p.name.lower()])

    def _on_cover(self, playlist_id: str, data: bytes):
        px = QPixmap()
        px.loadFromData(data)
        if px.isNull():
            return
        scaled = px.scaled(
            COVER_SIZE,
            COVER_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._covers[playlist_id] = scaled
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            pl = item.data(Qt.ItemDataRole.UserRole)
            if pl and pl.id == playlist_id:
                item.setIcon(QIcon(scaled))

    def get_selected(self) -> list[SpotifyAPI.Playlist]:
        if self._single_select:
            items = self._list.selectedItems()
            return [items[0].data(Qt.ItemDataRole.UserRole)] if items else []
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked and bool(
                item.flags() & Qt.ItemFlag.ItemIsEnabled
            ):
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result
