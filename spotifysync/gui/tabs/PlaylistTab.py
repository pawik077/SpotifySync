import time

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap

from ..workers import CoverThread, PlaylistDetailsThread
from ..dialogs import PlaylistPickerDialog
from .._helpers import COVER_SIZE, ROW_HEIGHT, format_owner, make_auth_key
from ... import api as SpotifyAPI
from ... import sync as SpotifySync


class PlaylistsTab(QWidget):
    settings_changed = pyqtSignal(bool)  # True = unsaved changes, False = saved

    def __init__(self, settings: dict, cache: dict):
        super().__init__()
        self._settings = settings
        self._cache = cache
        self._auth_key = make_auth_key(settings.get("access_token", ""))
        self._merge_id = settings.get("merge_playlist", "")
        self._user_id: str = ""
        self._cover_threads: list = []
        self._dirty = False
        self._build_ui()
        self._load_table()
        self._update_auth_state()
        self.set_expert_mode(settings.get("expert_mode", False))
        if self._auth_key and time.time() < settings.get("expires_at", 0):
            self._load_all_covers()
            self._load_merge_info()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        lay.addWidget(QLabel("Source Playlists"))

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Name", "Playlist ID", ""])
        hdr = self._table.horizontalHeader()
        assert hdr is not None
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, ROW_HEIGHT + 4)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 44)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        vhr = self._table.verticalHeader()
        assert vhr is not None
        vhr.setVisible(False)
        self._table.setShowGrid(False)
        self._table.itemChanged.connect(self._on_id_edited)
        lay.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._add_by_id_btn = QPushButton("+ Add by ID…")
        self._up_btn = QPushButton("↑")
        self._down_btn = QPushButton("↓")
        for b in (self._add_btn, self._add_by_id_btn, self._up_btn, self._down_btn):
            b.setObjectName("small")
            btn_row.addWidget(b)
        btn_row.addStretch()
        self._add_btn.clicked.connect(self._open_add)
        self._add_by_id_btn.clicked.connect(self._add_by_id)
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn.clicked.connect(self._move_down)
        self._add_by_id_btn.hide()
        lay.addLayout(btn_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#282828;")
        lay.addSpacing(4)
        lay.addWidget(sep)
        lay.addSpacing(4)

        lay.addWidget(QLabel("Merge Playlist"))
        merge_row = QHBoxLayout()
        self._merge_cover = QLabel()
        self._merge_cover.setFixedSize(COVER_SIZE, COVER_SIZE)
        self._merge_cover.setStyleSheet("background:#2a2a2a;border-radius:4px;")
        self._merge_name = QLabel("Not selected")
        self._merge_name.setStyleSheet("color:#B3B3B3;")
        self._merge_owner = QLabel()
        self._merge_owner.setStyleSheet("color:#666666;font-size:11px;")
        self._merge_owner.hide()
        self._merge_btn = QPushButton("Change…")
        self._merge_btn.setObjectName("small")
        self._merge_btn.clicked.connect(self._open_merge)
        self._merge_by_id_btn = QPushButton("Set by ID…")
        self._merge_by_id_btn.setObjectName("small")
        self._merge_by_id_btn.clicked.connect(self._set_merge_by_id)
        self._merge_by_id_btn.hide()
        merge_row.addWidget(self._merge_cover)
        merge_row.addSpacing(8)
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.addWidget(self._merge_name)
        info_col.addWidget(self._merge_owner)
        merge_row.addLayout(info_col)
        merge_row.addStretch()
        merge_row.addWidget(self._merge_by_id_btn)
        merge_row.addWidget(self._merge_btn)
        lay.addLayout(merge_row)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

    def _load_table(self):
        self._table.blockSignals(True)
        for pl_id in self._settings.get("playlists", []):
            self._append_row("", pl_id, fetch_cover=False)
        self._table.blockSignals(False)

    def _append_row(
        self,
        name: str,
        playlist_id: str,
        image_url: str = "",
        fetch_cover: bool = True,
        owner: SpotifyAPI.User | None = None,
    ):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setRowHeight(row, ROW_HEIGHT)

        cover = QLabel()
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet("background:#2a2a2a;margin:2px;border-radius:3px;")
        self._table.setCellWidget(row, 0, cover)

        owner_str = format_owner(owner, self._user_id)
        display_name = f"{name}\n{owner_str}" if owner_str else name
        was_blocked = self._table.signalsBlocked()
        self._table.blockSignals(True)
        self._table.setItem(row, 1, QTableWidgetItem(display_name))
        id_item = QTableWidgetItem(playlist_id)
        id_item.setForeground(QColor("#B3B3B3"))
        self._table.setItem(row, 2, id_item)
        self._table.blockSignals(was_blocked)
        self._table.setCellWidget(row, 3, self._make_remove_btn())

        if fetch_cover and self._auth_key and playlist_id:
            if image_url:
                self._load_cover(row, image_url)
            else:
                self._fetch_cover_by_id(row, playlist_id)

    def _load_cover(self, tag, url: str, callback=None):
        t = CoverThread(tag, url)
        if callback:
            t.loaded.connect(callback)
        else:
            t.loaded.connect(self._set_table_cover)
        t.finished.connect(lambda t=t: self._cover_threads.remove(t))
        self._cover_threads.append(t)
        t.start()

    def _set_table_cover(self, row: int, data: bytes):
        if row >= self._table.rowCount():
            return
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
        lbl = self._table.cellWidget(row, 0)
        if isinstance(lbl, QLabel):
            lbl.setPixmap(scaled)

    def _fetch_cover_by_id(self, row: int, playlist_id: str):
        cache = self._cache if self._settings.get("use_cache", True) else None
        t = PlaylistDetailsThread(playlist_id, self._auth_key, cache)

        def _on_details(
            _: str, name: str, url: str, owner: SpotifyAPI.User | None, r: int = row
        ):
            name_item = self._table.item(r, 1)
            if name_item:
                current = name_item.text().split("\n")[0]
                display = name or current
                owner_str = format_owner(owner, self._user_id)
                name_item.setText(f"{display}\n{owner_str}" if owner_str else display)
            if url:
                self._load_cover(r, url)

        t.loaded.connect(_on_details)
        t.finished.connect(lambda t=t: self._cover_threads.remove(t))
        self._cover_threads.append(t)
        t.start()

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self.settings_changed.emit(True)

    def _on_id_edited(self, item: QTableWidgetItem):
        if item.column() == 2:
            self._mark_dirty()
            if self._auth_key and item.text():
                self._fetch_cover_by_id(item.row(), item.text())

    def _open_add(self):
        dlg = PlaylistPickerDialog(
            self._auth_key,
            self._get_all_ids(),
            single_select=False,
            user_id=self._user_id,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.get_selected()
            if selected:
                self._mark_dirty()
            for pl in selected:
                self._append_row(pl.name, pl.id, image_url=pl.cover_url, owner=pl.owner)

    def _open_merge(self):
        dlg = PlaylistPickerDialog(
            self._auth_key,
            set(),
            single_select=True,
            current_id=self._merge_id,
            user_id=self._user_id,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.get_selected()
            if not selected:
                return
            pl = selected[0]
            self._merge_id = pl.id
            self._mark_dirty()
            self._merge_name.setText(pl.name)
            owner_str = format_owner(pl.owner, self._user_id)
            if owner_str:
                self._merge_owner.setText(owner_str)
                self._merge_owner.show()
            else:
                self._merge_owner.hide()
            if pl.cover_url:

                def _set_merge_cover(_, data: bytes, lbl=self._merge_cover):
                    px = QPixmap()
                    px.loadFromData(data)
                    if not px.isNull():
                        lbl.setPixmap(
                            px.scaled(
                                COVER_SIZE,
                                COVER_SIZE,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )

                self._load_cover("merge", pl.cover_url, callback=_set_merge_cover)

    def _make_remove_btn(self) -> QPushButton:
        btn = QPushButton("×")
        btn.setObjectName("delete")

        def _remove():
            for row in range(self._table.rowCount()):
                if self._table.cellWidget(row, 3) is btn:
                    self._table.removeRow(row)
                    self._mark_dirty()
                    break

        btn.clicked.connect(_remove)
        return btn

    def _move_up(self):
        row = self._table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self._table.setCurrentCell(row - 1, self._table.currentColumn())
            self._mark_dirty()

    def _move_down(self):
        row = self._table.currentRow()
        if row < self._table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self._table.setCurrentCell(row + 1, self._table.currentColumn())
            self._mark_dirty()

    def _swap_rows(self, a: int, b: int):
        was_blocked = self._table.signalsBlocked()
        self._table.blockSignals(True)
        for col in (1, 2):
            ia, ib = self._table.takeItem(a, col), self._table.takeItem(b, col)
            self._table.setItem(a, col, ib)
            self._table.setItem(b, col, ia)
        self._table.blockSignals(was_blocked)
        lbl_a = self._table.cellWidget(a, 0)
        lbl_b = self._table.cellWidget(b, 0)
        px_a = lbl_a.pixmap() if isinstance(lbl_a, QLabel) else QPixmap()
        px_b = lbl_b.pixmap() if isinstance(lbl_b, QLabel) else QPixmap()
        self._make_cover_label(a, px_b)
        self._make_cover_label(b, px_a)

    def _make_cover_label(self, row: int, pixmap: QPixmap):
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background:#2a2a2a;margin:2px;border-radius:3px;")
        if not pixmap.isNull():
            lbl.setPixmap(pixmap)
        self._table.setCellWidget(row, 0, lbl)

    def _get_all_ids(self) -> set:
        ids = set()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 2)
            if item:
                ids.add(item.text())
        return ids

    def _save(self):
        playlists = []
        for row in range(self._table.rowCount()):
            i = self._table.item(row, 2)
            if i and i.text():
                playlists.append(i.text())
        self._settings["playlists"] = playlists
        self._settings["merge_playlist"] = self._merge_id
        SpotifySync.save_settings(self._settings)
        self._dirty = False
        self.settings_changed.emit(False)

    def set_auth_key(self, auth_key: str):
        self._auth_key = auth_key
        self._update_auth_state()
        if auth_key:
            self._load_all_covers()
            self._load_merge_info()

    def _update_auth_state(self):
        authenticated = bool(self._auth_key)
        self._table.setColumnHidden(0, not authenticated)
        self._merge_cover.setVisible(authenticated)
        self._add_btn.setEnabled(authenticated)
        self._merge_btn.setEnabled(authenticated)
        if not authenticated:
            self._merge_name.setText("Not selected")
            self._merge_owner.hide()

    def _load_all_covers(self):
        for row in range(self._table.rowCount()):
            lbl = self._table.cellWidget(row, 0)
            if isinstance(lbl, QLabel) and lbl.pixmap().isNull():
                item = self._table.item(row, 2)
                if item and item.text():
                    self._fetch_cover_by_id(row, item.text())

    def _load_merge_info(self):
        if not self._merge_id:
            return
        expected_id = self._merge_id
        cache = self._cache if self._settings.get("use_cache", True) else None
        t = PlaylistDetailsThread(self._merge_id, self._auth_key, cache)

        def _on_info(_: str, name: str, url: str, owner: SpotifyAPI.User | None):
            if self._merge_id != expected_id:
                return
            self._merge_name.setText(name or expected_id)
            owner_str = format_owner(owner, self._user_id)
            if owner_str:
                self._merge_owner.setText(owner_str)
                self._merge_owner.show()
            else:
                self._merge_owner.hide()
            if url:

                def _set(_, data: bytes):
                    px = QPixmap()
                    px.loadFromData(data)
                    if not px.isNull():
                        self._merge_cover.setPixmap(
                            px.scaled(
                                COVER_SIZE,
                                COVER_SIZE,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )

                self._load_cover("merge_init", url, callback=_set)

        t.loaded.connect(_on_info)
        t.finished.connect(lambda t=t: self._cover_threads.remove(t))
        self._cover_threads.append(t)
        t.start()

    def set_user(self, user):  # SpotifyAPI.User | None
        self._user_id = user.id if user is not None else ""

    def _add_by_id(self):
        text, ok = QInputDialog.getText(self, "Add by ID", "Playlist ID:")
        if not ok:
            return
        playlist_id = text.strip()
        if not playlist_id or playlist_id in self._get_all_ids():
            return
        self._append_row("", playlist_id)
        self._mark_dirty()

    def _set_merge_by_id(self):
        text, ok = QInputDialog.getText(
            self, "Set Merge Playlist by ID", "Playlist ID:"
        )
        if not ok:
            return
        playlist_id = text.strip()
        if not playlist_id:
            return
        self._merge_id = playlist_id
        self._mark_dirty()
        self._merge_name.setText(playlist_id)
        self._merge_owner.hide()
        self._merge_cover.clear()
        self._load_merge_info()

    def set_expert_mode(self, enabled: bool):
        self._table.setColumnHidden(2, not enabled)
        self._add_by_id_btn.setVisible(enabled)
        self._merge_by_id_btn.setVisible(enabled)

    def update_settings(self, settings: dict):
        self._settings = settings
