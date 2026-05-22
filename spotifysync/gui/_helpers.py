import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .. import api as SpotifyAPI

_ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")

COVER_SIZE = 48
ROW_HEIGHT = 56


def make_app_icon() -> QIcon:
    renderer = QSvgRenderer(os.path.join(_ASSETS, "icon.svg"))
    if not renderer.isValid():
        return QIcon()
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pix)
    return icon


def make_auth_key(access_token: str) -> str:
    return f"Bearer {access_token}" if access_token else ""


def make_circular(px: QPixmap, size: int) -> QPixmap:
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


def format_owner(owner: SpotifyAPI.User | None, user_id: str) -> str:
    if owner is None or owner.id == user_id:
        return ""
    if owner.display_name and owner.display_name != owner.id:
        return f"{owner.display_name} ({owner.id})"
    return owner.id
