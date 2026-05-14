import time

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from ..workers import AuthThread, CoverThread, FetchUserThread, RefreshThread, StatusDot
from ..dialogs import ClientIdDialog
from .._helpers import COVER_SIZE, make_circular, make_auth_key
from ... import api as SpotifyAPI
from ... import sync as SpotifySync


class AuthTab(QWidget):
    authenticated = pyqtSignal(str, str, int)  # access_token, refresh_token, expires_at
    token_cleared = pyqtSignal()
    user_changed = pyqtSignal(object)  # SpotifyAPI.User | None

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings
        self._auth_thread = None
        self._refresh_thread = None
        self._user_thread = None
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

        self._signout_btn = QPushButton("Sign out")
        self._signout_btn.setObjectName("secondary")
        self._signout_btn.setFixedWidth(180)
        self._signout_btn.setVisible(False)
        self._signout_btn.clicked.connect(self._sign_out)

        user_row = QHBoxLayout()
        user_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_row.setSpacing(10)
        self._user_avatar = QLabel()
        self._user_avatar.setFixedSize(COVER_SIZE, COVER_SIZE)
        self._user_avatar.setStyleSheet("background:#2a2a2a;border-radius:24px;")
        self._user_name = QLabel()
        self._user_name.setStyleSheet("color:#B3B3B3;font-size:12px;")
        user_row.addWidget(self._user_avatar)
        user_row.addWidget(self._user_name)
        self._user_widget = QWidget()
        self._user_widget.setLayout(user_row)
        self._user_widget.setVisible(False)

        lay.addLayout(status_row)
        lay.addWidget(self._user_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._signout_btn, alignment=Qt.AlignmentFlag.AlignCenter)
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
            self._fetch_user(make_auth_key(self._settings.get("access_token", "")))
            return
        self._set("yellow", "Refreshing token…", enabled=False)
        self._refresh_thread = RefreshThread(self._settings["client_id"], rt)
        self._refresh_thread.success.connect(self._on_refresh_ok)
        self._refresh_thread.revoked.connect(self._on_revoked)
        self._refresh_thread.failed.connect(
            lambda _: self._set(
                "red", "Refresh failed — check connection", enabled=True
            )
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
        self._fetch_user(make_auth_key(td["access_token"]))

    def _on_refresh_ok(self, td: dict):
        rt = td.get("refresh_token") or self._settings.get("refresh_token", "")
        expires_at = int(time.time()) + td["expires_in"]
        self.authenticated.emit(td["access_token"], rt, expires_at)
        self._set("green", "Authenticated", enabled=False)
        self._fetch_user(make_auth_key(td["access_token"]))

    def _on_revoked(self):
        self.token_cleared.emit()
        self.user_changed.emit(None)
        self._set("red", "Token invalid — re-authenticate", enabled=True)

    def _sign_out(self):
        self.token_cleared.emit()
        self.user_changed.emit(None)
        self._set("grey", "Logged out", enabled=True)

    def _fetch_user(self, auth_key: str):
        self._user_thread = FetchUserThread(auth_key)
        self._user_thread.loaded.connect(self._on_user_loaded)
        self._user_thread.start()

    def _on_user_loaded(self, user: SpotifyAPI.User):
        self._user_name.setText(
            f"{user.display_name} ({user.id})"
            if user.display_name != user.id
            else f"{user.id}"
        )
        if user.image_url:

            def _set(_, data: bytes):
                px = QPixmap()
                px.loadFromData(data)
                if not px.isNull():
                    self._user_avatar.setPixmap(make_circular(px, COVER_SIZE))

            self._load_image("user_image", user.image_url, callback=_set)

        self._user_widget.setVisible(True)
        self.user_changed.emit(user)

    def _load_image(self, tag, url, callback):
        self._user_thread = CoverThread(tag, url)
        self._user_thread.loaded.connect(callback)
        self._user_thread.finished.connect(lambda: setattr(self, "_user_thread", None))
        self._user_thread.start()

    def _set(self, color: str, text: str, *, enabled: bool):
        self._dot.set_color(color)
        self._status_lbl.setText(text)
        self._btn.setEnabled(enabled)
        self._signout_btn.setVisible(color == "green")
        if color != "green":
            self._user_widget.setVisible(False)
            self._user_name.setText("")
            self._user_avatar.setPixmap(QPixmap())
