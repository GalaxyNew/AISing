from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from aising_client.audio.engine import PlaybackEngine
from aising_client.audio.separator import SeparationResult, StemSeparator


class SeparationWorker(QObject):
    log = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, input_path: Path, output_dir: Path) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir

    @Slot()
    def run(self) -> None:
        try:
            result = StemSeparator().separate(self.input_path, self.output_dir, self.log.emit)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class LocalSeparationWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.input_path: Path | None = None
        self.output_dir = Path("data/local_separation")
        self.result: SeparationResult | None = None
        self.engine = PlaybackEngine()
        self.thread: QThread | None = None
        self.worker: SeparationWorker | None = None

        self.input_edit = QLineEdit()
        self.input_edit.setReadOnly(True)
        self.input_edit.setPlaceholderText("选择一首需要分离的歌曲")
        self.output_edit = QLineEdit(str(self.output_dir))
        self.output_edit.setReadOnly(True)
        self.status = QLabel("请选择歌曲文件。")
        self.status.setObjectName("SubtleText")
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(170)
        self.logs.setPlaceholderText("处理日志将在这里显示")

        self.select_input_button = QPushButton("选择歌曲")
        self.select_output_button = QPushButton("选择输出目录")
        self.start_button = QPushButton("开始分离")
        self.start_button.setObjectName("PrimaryButton")
        self.play_vocals_button = QPushButton("试听人声")
        self.play_accompaniment_button = QPushButton("试听伴奏")
        self.stop_button = QPushButton("停止试听")
        self.open_output_button = QPushButton("打开输出目录")

        self.select_input_button.clicked.connect(self.choose_input)
        self.select_output_button.clicked.connect(self.choose_output)
        self.start_button.clicked.connect(self.start_separation)
        self.play_vocals_button.clicked.connect(lambda: self.play_stem("vocals"))
        self.play_accompaniment_button.clicked.connect(lambda: self.play_stem("accompaniment"))
        self.stop_button.clicked.connect(self.stop_preview)
        self.open_output_button.clicked.connect(self.open_output)
        self.set_results_enabled(False)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(14)

        title = QLabel("本地人声分离")
        title.setObjectName("SectionTitle")
        subtitle = QLabel("歌曲只在本机处理，分离为人声与伴奏音轨。")
        subtitle.setObjectName("SubtleText")
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)
        panel_layout.addLayout(self._path_row("源文件", self.input_edit, self.select_input_button))
        panel_layout.addLayout(self._path_row("输出目录", self.output_edit, self.select_output_button))

        actions = QHBoxLayout()
        actions.addWidget(self.start_button)
        actions.addWidget(self.open_output_button)
        actions.addStretch()
        panel_layout.addLayout(actions)
        panel_layout.addWidget(self.status)
        panel_layout.addWidget(self.logs, 1)

        preview = QHBoxLayout()
        preview.addWidget(self.play_vocals_button)
        preview.addWidget(self.play_accompaniment_button)
        preview.addWidget(self.stop_button)
        preview.addStretch()
        panel_layout.addLayout(preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

    def _path_row(self, label: str, edit: QLineEdit, button: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit, 1)
        row.addWidget(button)
        return row

    def choose_input(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择歌曲",
            "",
            "Audio Files (*.wav *.mp3 *.flac *.m4a);;All Files (*)",
        )
        if filename:
            self.input_path = Path(filename)
            self.input_edit.setText(filename)

    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.output_dir))
        if folder:
            self.output_dir = Path(folder)
            self.output_edit.setText(folder)

    def start_separation(self) -> None:
        if self.input_path is None:
            self.status.setText("请先选择歌曲文件。")
            return
        self.stop_preview()
        self.result = None
        self.logs.clear()
        self.set_results_enabled(False)
        self.set_processing_enabled(False)
        self.status.setText("正在本地分离音轨...")

        self.thread = QThread(self)
        self.worker = SeparationWorker(self.input_path, self.output_dir)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logs.appendPlainText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_completed(self, result: SeparationResult) -> None:
        self.result = result
        self.status.setText(f"分离完成，使用设备: {result.device.upper()}")
        self.set_results_enabled(True)

    def on_failed(self, message: str) -> None:
        self.status.setText(f"分离失败: {message}")

    def on_finished(self) -> None:
        self.set_processing_enabled(True)

    def set_processing_enabled(self, enabled: bool) -> None:
        self.start_button.setEnabled(enabled)
        self.select_input_button.setEnabled(enabled)
        self.select_output_button.setEnabled(enabled)

    def set_results_enabled(self, enabled: bool) -> None:
        self.play_vocals_button.setEnabled(enabled)
        self.play_accompaniment_button.setEnabled(enabled)
        self.open_output_button.setEnabled(enabled)
        self.stop_button.setEnabled(enabled)

    def play_stem(self, stem: str) -> None:
        if self.result is None:
            return
        self.engine.stop()
        target = self.result.vocals if stem == "vocals" else self.result.accompaniment
        try:
            self.engine.load(target)
            self.engine.start()
            self.status.setText(f"正在试听: {target.name}")
        except Exception as exc:
            self.status.setText(f"试听失败: {exc}")

    def stop_preview(self) -> None:
        self.engine.stop()

    def open_output(self) -> None:
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.output_dir.resolve())))
