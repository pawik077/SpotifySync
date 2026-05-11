from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from PyQt6.QtCore import pyqtSignal


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
