import sys
import json
import os
import logging
import time
import requests
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QLineEdit,
    QHeaderView,
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon, QColor

from auth import authorize
import SpotifyAPI
import SpotifySync
from utils import setup_logger

SETTINGS_FILE = "data/settings.json"
COVER_SIZE = 48
ROW_HEIGHT = 56

logger = logging.getLogger("SpotifySync")


# ── Settings ──────────────────────────────────────────────────────────────────


def load_settings(filename: str = SETTINGS_FILE):
    try:
        with open(filename, "r") as s:
            settings = json.load(s)
    except FileNotFoundError:
        logger.warning(
            "Error while reading settings file - settings file not found - creating new"
        )
        settings = {
            "access_token": "",
            "refresh_token": "",
            "client_id": "",
            "expires_at": 0,
            "playlists": [],
            "merge_playlist": "",
        }
    except json.JSONDecodeError:
        # copied the previous one for now
        # should log an error and ask user for permission to overwrite
        logger.error("Error while reading settings file - JSON decoding failed")
        settings = {
            "access_token": "",
            "refresh_token": "",
            "client_id": "",
            "expires_at": 0,
            "playlists": [],
            "merge_playlist": "",
        }
    return settings


def make_auth_key(access_token: str) -> str:
    return f"Bearer {access_token}" if access_token else ""


# ── Worker threads ────────────────────────────────────────────────────────────


class AuthThread(QThread):
    success = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client_id: str):
        super().__init__()
        self._client_id = client_id

    def run(self):
        try:
            self.success.emit(authorize(self._client_id))
        except Exception as e:
            self.failed.emit(str(e))


class RefreshThread(QThread):
    success = pyqtSignal(dict)
    revoked = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, client_id: str, refresh_token: str):
        super().__init__()
        self._client_id = client_id
        self._refresh_token = refresh_token

    def run(self):
        try:
            access_token, refresh_token, expires_in = SpotifyAPI.refresh(
                self._refresh_token, self._client_id
            )
            self.success.emit(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": expires_in,
                }
            )
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (400, 401):
                self.revoked.emit()
            else:
                self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(str(e))


class FetchPlaylistsThread(QThread):
    success = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, auth_key: str):
        super().__init__()
        self._auth_key = auth_key

    def run(self):
        try:
            self.success.emit(SpotifyAPI.getCurrentUserPlaylists(self._auth_key))
        except Exception as e:
            self.failed.emit(str(e))


class CoverThread(QThread):
    loaded = pyqtSignal(object, bytes)  # tag, raw image bytes

    def __init__(self, tag, url: str):
        super().__init__()
        self._tag = tag
        self._url = url

    def run(self):
        try:
            r = requests.get(self._url, timeout=8)
            r.raise_for_status()
            self.loaded.emit(self._tag, r.content)
        except Exception:
            pass


class BatchCoverThread(QThread):
    loaded = pyqtSignal(str, bytes)  # playlist_id, raw image bytes

    def __init__(self, playlists: list):
        super().__init__()
        self._playlists = playlists

    def run(self):
        for pl in self._playlists:
            if not pl.cover_url:
                continue
            try:
                r = requests.get(pl.cover_url, timeout=8)
                r.raise_for_status()
                self.loaded.emit(pl.id, r.content)
            except Exception:
                pass


class PlaylistDetailsThread(QThread):
    loaded = pyqtSignal(str, str, str)  # playlist_id, name, image_url

    def __init__(self, playlist_id: str, auth_key: str):
        super().__init__()
        self._id = playlist_id
        self._auth_key = auth_key

    def run(self):
        try:
            data = SpotifyAPI.getPlaylistMetadata(self._id, self._auth_key)
            self.loaded.emit(self._id, data.name, data.cover_url)
        except Exception:
            pass


class SyncThread(QThread):
    success = pyqtSignal()
    failed = pyqtSignal(str)

    def run(self):
        try:
            SpotifySync.main()
            self.success.emit()
        except SystemExit as e:
            if e.code not in (None, 0):
                self.failed.emit(f"Sync exited (code {e.code})")
            else:
                self.success.emit()
        except Exception as e:
            self.failed.emit(str(e))


# ── StatusDot ─────────────────────────────────────────────────────────────────


class StatusDot(QLabel):
    _COLORS = {
        "green": "#1DB954",
        "red": "#E63946",
        "yellow": "#FFC947",
        "grey": "#535353",
    }

    def __init__(self, color: str = "grey"):
        super().__init__()
        self.setFixedSize(12, 12)
        self.set_color(color)

    def set_color(self, color: str):
        c = self._COLORS.get(color, color)
        self.setStyleSheet(f"background-color:{c};border-radius:6px;")


# ── PlaylistPickerDialog ──────────────────────────────────────────────────────


class PlaylistPickerDialog(QDialog):
    def __init__(
        self,
        auth_key: str,
        existing_ids: set,
        single_select: bool = False,
        current_id: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._auth_key = auth_key
        self._existing_ids = existing_ids
        self._single_select = single_select
        self._current_id = current_id
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

    def _on_loaded(self, playlists: list):
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
            item = QListWidgetItem(f"  {pl.name}")
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


# ── ClientIdDialog ────────────────────────────────────────────────────────────


class ClientIdDialog(QDialog):
    saved = pyqtSignal(str)

    def __init__(self, current_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Client ID")
        self.setFixedWidth(420)
        self._build_ui(current_id)

    def _build_ui(self, current_id: str):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        info = QLabel(
            "Enter your Spotify application's Client ID.\n"
            "Obtain it from the Spotify Developer Dashboard."
        )
        info.setStyleSheet("color:#B3B3B3;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._field = QLineEdit(current_id)
        lay.addWidget(self._field)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

    def _save(self):
        self.saved.emit(self._field.text().strip())
        self.accept()


# ── AuthTab ───────────────────────────────────────────────────────────────────


class AuthTab(QWidget):
    authenticated = pyqtSignal(str, str, int)  # access_token, refresh_token, expires_at
    token_cleared = pyqtSignal()

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings
        self._auth_thread = None
        self._refresh_thread = None
        self._build_ui()
        self._init_state()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setFixedWidth(340)
        lay = QVBoxLayout(card)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(20)

        status_row = QHBoxLayout()
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.setSpacing(10)
        self._dot = StatusDot("grey")
        self._status_lbl = QLabel("Checking…")
        self._status_lbl.setStyleSheet("font-size:14px;")
        status_row.addWidget(self._dot)
        status_row.addWidget(self._status_lbl)

        self._btn = QPushButton("Authenticate")
        self._btn.setEnabled(False)
        self._btn.setFixedWidth(180)
        self._btn.clicked.connect(self._start_auth)

        self._configure_btn = QPushButton("Configure Client ID…")
        self._configure_btn.setObjectName("secondary")
        self._configure_btn.setFixedWidth(180)
        self._configure_btn.clicked.connect(self._open_configure)

        lay.addLayout(status_row)
        lay.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._configure_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(card)

    def _init_state(self):
        if not self._settings.get("client_id", ""):
            self._set("grey", "Client ID not configured", enabled=False)
            return
        rt = self._settings.get("refresh_token", "")
        if not rt:
            self._set("grey", "Not authenticated", enabled=True)
            return
        if time.time() < self._settings.get("expires_at", 0):
            self._set("green", "Authenticated", enabled=False)
            return
        self._set("yellow", "Refreshing token…", enabled=False)
        self._refresh_thread = RefreshThread(self._settings["client_id"], rt)
        self._refresh_thread.success.connect(self._on_refresh_ok)
        self._refresh_thread.revoked.connect(self._on_revoked)
        self._refresh_thread.failed.connect(
            lambda _: self._set("grey", "Not authenticated", enabled=True)
        )
        self._refresh_thread.start()

    def _open_configure(self):
        dlg = ClientIdDialog(self._settings.get("client_id", ""), parent=self)
        dlg.saved.connect(self._on_client_id_saved)
        dlg.exec()

    def _on_client_id_saved(self, client_id: str):
        self._settings["client_id"] = client_id
        SpotifySync.save_settings(self._settings)
        self._init_state()

    def _start_auth(self):
        self._set("yellow", "Authenticating…", enabled=False)
        self._auth_thread = AuthThread(self._settings["client_id"])
        self._auth_thread.success.connect(self._on_auth_ok)
        self._auth_thread.failed.connect(
            lambda _: self._set("grey", "Not authenticated", enabled=True)
        )
        self._auth_thread.start()

    def _on_auth_ok(self, td: dict):
        expires_at = int(time.time()) + td["expires_in"]
        self.authenticated.emit(td["access_token"], td["refresh_token"], expires_at)
        self._set("green", "Authenticated", enabled=False)

    def _on_refresh_ok(self, td: dict):
        rt = td.get("refresh_token") or self._settings.get("refresh_token", "")
        expires_at = int(time.time()) + td["expires_in"]
        self.authenticated.emit(td["access_token"], rt, expires_at)
        self._set("green", "Authenticated", enabled=False)

    def _on_revoked(self):
        self.token_cleared.emit()
        self._set("red", "Token invalid — re-authenticate", enabled=True)

    def _set(self, color: str, text: str, *, enabled: bool):
        self._dot.set_color(color)
        self._status_lbl.setText(text)
        self._btn.setEnabled(enabled)


# ── PlaylistsTab ──────────────────────────────────────────────────────────────


class PlaylistsTab(QWidget):
    settings_changed = pyqtSignal(bool)  # True = unsaved changes, False = saved

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings
        self._auth_key = make_auth_key(settings.get("access_token", ""))
        self._merge_id = settings.get("merge_playlist", "")
        self._cover_threads: list = []
        self._dirty = False
        self._build_ui()
        self._load_table()
        self._update_auth_state()
        if self._auth_key:
            self._load_all_covers()
            self._load_merge_info()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        lay.addWidget(QLabel("Source Playlists"))

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["", "Name", "Playlist ID"])
        hdr = self._table.horizontalHeader()
        assert hdr is not None
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, ROW_HEIGHT + 4)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
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
        lay.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._remove_btn = QPushButton("− Remove")
        self._up_btn = QPushButton("↑")
        self._down_btn = QPushButton("↓")
        for b in (self._add_btn, self._remove_btn, self._up_btn, self._down_btn):
            b.setObjectName("small")
            btn_row.addWidget(b)
        btn_row.addStretch()
        self._add_btn.clicked.connect(self._open_add)
        self._remove_btn.clicked.connect(self._remove_row)
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn.clicked.connect(self._move_down)
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
        self._merge_btn = QPushButton("Change…")
        self._merge_btn.setObjectName("small")
        self._merge_btn.clicked.connect(self._open_merge)
        merge_row.addWidget(self._merge_cover)
        merge_row.addSpacing(8)
        merge_row.addWidget(self._merge_name)
        merge_row.addStretch()
        merge_row.addWidget(self._merge_btn)
        lay.addLayout(merge_row)

        lay.addStretch()

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

    def _load_table(self):
        self._table.blockSignals(True)
        for pl_id in self._settings.get("playlists", []):
            self._append_row("", pl_id, fetch_cover=False)
        self._table.blockSignals(False)

    def _append_row(
        self, name: str, playlist_id: str, image_url: str = "", fetch_cover: bool = True
    ):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setRowHeight(row, ROW_HEIGHT)

        cover = QLabel()
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet("background:#2a2a2a;margin:2px;border-radius:3px;")
        self._table.setCellWidget(row, 0, cover)

        self._table.blockSignals(True)
        self._table.setItem(row, 1, QTableWidgetItem(name))
        id_item = QTableWidgetItem(playlist_id)
        id_item.setForeground(QColor("#B3B3B3"))
        self._table.setItem(row, 2, id_item)
        self._table.blockSignals(False)

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
        t.start()
        self._cover_threads.append(t)

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
        t = PlaylistDetailsThread(playlist_id, self._auth_key)

        def _on_details(_: str, name: str, url: str, r: int = row):
            if name:
                name_item = self._table.item(r, 1)
                if name_item and not name_item.text():
                    name_item.setText(name)
            if url:
                self._load_cover(r, url)

        t.loaded.connect(_on_details)
        t.finished.connect(lambda t=t: self._cover_threads.remove(t))
        t.start()
        self._cover_threads.append(t)

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
            self._auth_key, self._get_all_ids(), single_select=False, parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.get_selected()
            if selected:
                self._mark_dirty()
            for pl in selected:
                self._append_row(pl.name, pl.id, image_url=pl.cover_url)

    def _open_merge(self):
        dlg = PlaylistPickerDialog(
            self._auth_key,
            set(),
            single_select=True,
            current_id=self._merge_id,
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

    def _remove_row(self):
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if rows:
            self._mark_dirty()
        for row in rows:
            self._table.removeRow(row)

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
        self._table.blockSignals(True)
        for col in (1, 2):
            ia, ib = self._table.takeItem(a, col), self._table.takeItem(b, col)
            self._table.setItem(a, col, ib)
            self._table.setItem(b, col, ia)
        self._table.blockSignals(False)
        # Swap cover pixmaps
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
        t = PlaylistDetailsThread(self._merge_id, self._auth_key)

        def _on_info(_: str, name: str, url: str):
            if self._merge_id != expected_id:
                return
            self._merge_name.setText(name or expected_id)
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
        t.start()
        self._cover_threads.append(t)

    def update_settings(self, settings: dict):
        self._settings = settings


# ── MainWindow ────────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpotifySync")
        self.setMinimumSize(640, 540)
        os.makedirs("data", exist_ok=True)
        setup_logger("data/sync.log")
        self._settings = load_settings()
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
        self._playlists_tab = PlaylistsTab(self._settings)

        self._auth_tab.authenticated.connect(self._on_authenticated)
        self._auth_tab.token_cleared.connect(self._on_token_cleared)
        self._playlists_tab.settings_changed.connect(self._on_settings_changed)

        self._tabs.addTab(self._auth_tab, "Authentication")
        self._tabs.addTab(self._playlists_tab, "Playlists")

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

    def _on_sync_ok(self):
        self._sync_btn.setEnabled(True)
        self._sync_dot.set_color("green")
        self._sync_status.setText("Sync complete")

    def _on_sync_failed(self, message: str):
        self._sync_btn.setEnabled(True)
        self._sync_dot.set_color("red")
        self._sync_status.setText(f"Sync failed: {message}")

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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("SpotifySync")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
