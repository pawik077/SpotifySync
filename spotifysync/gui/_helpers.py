from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap

from .. import api as SpotifyAPI

COVER_SIZE = 48
ROW_HEIGHT = 56


def make_auth_key(access_token: str) -> str:
    return f"Bearer {access_token}" if access_token else ""


def _make_circular(px: QPixmap, size: int) -> QPixmap:
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(result.rect().toRectF())
    painter.setClipPath(path)
    painter.drawPixmap(
        result.rect(),
        px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding),
    )
    painter.end()
    return result


def _format_owner(owner: SpotifyAPI.User | None, user_id: str) -> str:
    if owner is None or owner.id == user_id:
        return ""
    if owner.display_name and owner.display_name != owner.id:
        return f"{owner.display_name} ({owner.id})"
    return owner.id
