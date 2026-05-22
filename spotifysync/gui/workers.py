import requests
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import QThread, pyqtSignal

from ..auth import authorize
from ..api import SpotifyClient
from .. import sync as SpotifySync


class AuthThread(QThread):
    success = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client_id: str):
        super().__init__()
        self._client_id = client_id

    def run(self):
        try:
            access_token, refresh_token, expires_in = authorize(self._client_id)
            self.success.emit(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": expires_in,
                }
            )
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
            access_token, refresh_token, expires_in = SpotifyClient.refresh(
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
        client = SpotifyClient(self._auth_key)
        try:
            self.success.emit(client.getCurrentUserPlaylists())
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
    loaded = pyqtSignal(str, str, str, object)  # playlist_id, name, image_url, owner

    def __init__(self, playlist_id: str, auth_key: str, cache: dict | None):
        super().__init__()
        self._id = playlist_id
        self._auth_key = auth_key
        self._cache = cache

    def run(self):
        client = SpotifyClient(self._auth_key, self._cache)
        try:
            data = client.getPlaylistMetadata(self._id)
            self.loaded.emit(self._id, data.name, data.cover_url, data.owner)
        except Exception:
            pass


class FetchUserThread(QThread):
    loaded = pyqtSignal(object)  # SpotifyAPI.User
    failed = pyqtSignal(str)

    def __init__(self, auth_key: str):
        super().__init__()
        self._auth_key = auth_key

    def run(self):
        client = SpotifyClient(self._auth_key)
        try:
            self.loaded.emit(client.getCurrentUser())
        except Exception as e:
            self.failed.emit(str(e))


class SyncThread(QThread):
    success = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, dry_run: bool = False):
        super().__init__()
        self._dry_run = dry_run

    def run(self):
        try:
            summary = SpotifySync.run_sync(self._dry_run)
        except Exception as e:
            self.failed.emit(str(e))
            return
        if summary.errors:
            self.failed.emit(summary.errors[0])
        else:
            self.success.emit(summary)


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
