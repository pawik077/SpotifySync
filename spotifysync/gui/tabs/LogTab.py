from PyQt6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtCore import QFileSystemWatcher
from PyQt6.QtGui import QColor, QTextCharFormat


class LogTab(QWidget):
    LOG_FILE = "data/sync.log"

    def __init__(self):
        super().__init__()
        self._build_ui()
        self._watcher = QFileSystemWatcher([self.LOG_FILE])
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._load_log()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search logs…")
        self._search.textChanged.connect(self._load_log)
        lay.addWidget(self._search)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setStyleSheet(
            "QPlainTextEdit { background:#181818; color:#B3B3B3;"
            " font-family: monospace; font-size: 12px; border: none; }"
        )
        lay.addWidget(self._view)

    def _on_file_changed(self, path: str):
        # Re-add path in case the file was replaced (log rotation)
        if path not in self._watcher.files():
            self._watcher.addPath(path)
        self._load_log()

    def _load_log(self):
        try:
            with open(self.LOG_FILE, "r") as f:
                log = f.readlines()
        except FileNotFoundError:
            log = []
        log.reverse()
        query = self._search.text().lower()
        if query:
            log = [x for x in log if query in x.lower()]
        self._view.setPlainText("".join(log))
        self._highlight_matches(query)

    def _highlight_matches(self, query: str):
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#1DB954"))
        fmt.setForeground(QColor("#000000"))
        selections: list[QTextEdit.ExtraSelection] = []
        if query:
            doc = self._view.document()
            assert doc is not None
            cur = doc.find(query)
            while not cur.isNull():
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cur
                selection.format = fmt
                selections.append(selection)
                cur = doc.find(query, cur)
        self._view.setExtraSelections(selections)
