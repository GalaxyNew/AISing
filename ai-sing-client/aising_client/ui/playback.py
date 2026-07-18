import json
from pathlib import Path
from html import escape

from PySide6.QtCore import QObject, QPoint, QSize, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aising_client.api import ApiClient
from aising_client.audio.engine import PlaybackEngine
from aising_client.audio.lyrics import LyricLine, parse_lyrics
from aising_client.audio.meter import MicrophoneMeter
from aising_client.branding import DELETE_ICON_PATH


class SongListRow(QFrame):
    def __init__(self, title_text: str, delete_button: QPushButton) -> None:
        super().__init__()
        self.delete_button = delete_button
        self.setObjectName("SongRow")
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(12, 7, 6, 7)
        row_layout.setSpacing(10)
        title = QLabel(title_text)
        title.setObjectName("SongRowTitle")
        title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        row_layout.addWidget(title, 1)
        row_layout.addWidget(delete_button)
        delete_button.hide()

    def enterEvent(self, event) -> None:
        self.delete_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.delete_button.hide()
        super().leaveEvent(event)


class WaveformSlider(QWidget):
    seekRequested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.peaks: list[float] = []
        self.progress = 0
        self.track_height = 3
        self.played_color = QColor("#2f7dd3")
        self.remaining_color = QColor("#aeb9c6")
        self.bar_width = 1
        self.played_bar_color = QColor("#2f7dd3")
        self.remaining_bar_color = QColor("#c4ceda")
        self.setMinimumHeight(54)
        self.setCursor(Qt.PointingHandCursor)

    def set_peaks(self, peaks) -> None:
        self.peaks = [float(value) for value in peaks]
        self.update()

    def set_progress(self, percent: int) -> None:
        self.progress = max(0, min(100, percent))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = self.rect().adjusted(8, 8, -8, -8)
        center_y = rect.center().y()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))
        if self.peaks:
            step = rect.width() / max(1, len(self.peaks))
            played_until = len(self.peaks) * self.progress / 100
            for index, peak in enumerate(self.peaks):
                x = rect.left() + index * step
                half = max(2, peak * rect.height() / 2)
                bar_color = self.played_bar_color if index <= played_until else self.remaining_bar_color
                painter.setPen(QPen(bar_color, self.bar_width, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPoint(int(x), int(center_y - half)), QPoint(int(x), int(center_y + half)))
        else:
            pass
        progress_x = rect.left() + rect.width() * self.progress / 100
        painter.setPen(QPen(self.remaining_color, self.track_height, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPoint(int(progress_x), int(center_y)), QPoint(rect.right(), int(center_y)))
        painter.setPen(QPen(self.played_color, self.track_height, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPoint(rect.left(), int(center_y)), QPoint(int(progress_x), int(center_y)))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._seek_from_x(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton:
            self._seek_from_x(event.position().x())

    def _seek_from_x(self, x: float) -> None:
        rect = self.rect().adjusted(8, 8, -8, -8)
        if rect.width() <= 0:
            return
        percent = int(((x - rect.left()) / rect.width()) * 100)
        self.seekRequested.emit(max(0, min(100, percent)))


class SongAssetsDownloadWorker(QObject):
    progress = Signal(str, int, int, int)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, api: ApiClient, job: dict, targets: dict[str, Path]) -> None:
        super().__init__()
        self.api = api
        self.job = job
        self.targets = targets

    @Slot()
    def run(self) -> None:
        try:
            missing = [(kind, path) for kind, path in self.targets.items() if not path.exists()]
            total_files = max(1, len(missing))
            for file_index, (kind, path) in enumerate(missing, start=1):

                def update_progress(done: int, total: int, file_kind=kind, index=file_index) -> None:
                    file_percent = int(done * 100 / total) if total > 0 else 0
                    overall = int(((index - 1) + file_percent / 100) * 100 / total_files)
                    self.progress.emit(file_kind, index, total_files, overall)

                self.progress.emit(kind, file_index, total_files, int((file_index - 1) * 100 / total_files))
                self.api.download_job_file_from_job(self.job, kind, path, update_progress)
            self.progress.emit("", total_files, total_files, 100)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class PlaybackWidget(QWidget):
    def __init__(self, api: ApiClient, settings: QSettings | None = None) -> None:
        super().__init__()
        self.api = api
        self.settings = settings or QSettings("Miaochang", "Client")
        self.jobs: list[dict] = []
        self.filtered_jobs: list[dict] = []
        self.mode = "auto"
        self.ai_voice_enabled = False
        self.pending_ai_voice_state: bool | None = None
        self.pending_ai_voice_elapsed_ms = 0
        self.ai_voice_on_delay_ms = 250
        self.ai_voice_off_delay_ms = 1200
        self.timer_interval_ms = 100
        self.is_playing = False
        self.playing_job_id: int | None = None
        self.lyric_lines: list[LyricLine] = []
        self.meter = MicrophoneMeter()
        self.engine = PlaybackEngine()
        self.download_thread: QThread | None = None
        self.download_worker: SongAssetsDownloadWorker | None = None
        self.download_dialog: QProgressDialog | None = None
        self.pending_download_job: dict | None = None
        self.pending_download_targets: dict[str, Path] | None = None
        self.song_search = QLineEdit()
        self.song_search.setPlaceholderText("搜索歌曲名")
        self.song_search.textChanged.connect(self.filter_song_tasks)
        self.song_list = QListWidget()
        self.song_list.setMinimumHeight(180)
        self.song_list.setSpacing(0)
        self.song_list.setObjectName("SongList")
        self.song_list.currentItemChanged.connect(self.update_title_from_current_job)
        self.song_list.itemDoubleClicked.connect(self.play_song_item)

        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)
        self.auto_button = self.make_mode_button("自动跟唱", "auto")
        self.ai_button = self.make_mode_button("AI人声", "ai")
        self.user_button = self.make_mode_button("用户人声", "user")
        self.auto_button.setChecked(True)

        self.waveform = WaveformSlider()
        self.waveform.seekRequested.connect(self.seek)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("MetricValue")

        self.mic_threshold = QSlider(Qt.Horizontal)
        self.mic_threshold.setRange(1, 100)
        self.mic_threshold.setValue(self.settings.value("playback/mic_threshold", 8, type=int))
        self.mic_threshold.valueChanged.connect(self.save_thresholds)
        self.mic_threshold_value = QLabel("0.008")
        self.mic_threshold_value.setObjectName("MetricValue")
        self.ai_threshold = QSlider(Qt.Horizontal)
        self.ai_threshold.setRange(1, 1000)
        self.ai_threshold.setValue(self.settings.value("playback/ai_threshold", 20, type=int))
        self.ai_threshold.valueChanged.connect(self.save_thresholds)
        self.ai_threshold_value = QLabel("0.020")
        self.ai_threshold_value.setObjectName("MetricValue")
        self.level = QLabel("0.000")
        self.level.setObjectName("MetricValue")
        self.ai_energy = QLabel("0.000")
        self.ai_energy.setObjectName("MetricValue")

        self.lyrics = QTextEdit()
        self.lyrics.setReadOnly(True)
        self.lyrics.setMinimumHeight(210)
        self.lyrics.setFrameShape(QFrame.NoFrame)
        self.lyrics.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lyrics.setStyleSheet("QTextEdit { border: 0; background: transparent; font-size: 26px; }")
        self.lyrics.setPlainText("暂无歌词")

        self.status = QLabel("")
        self.status.setObjectName("SubtleText")
        self.start_button = QPushButton("播放")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setMinimumSize(118, 48)
        self.start_button.clicked.connect(self.toggle_playback)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(16)

        content_row = QHBoxLayout()
        content_row.setSpacing(20)

        song_column = QVBoxLayout()
        song_column.setSpacing(12)
        self.title_label = QLabel("请选择歌曲")
        self.title_label.setObjectName("SectionTitle")
        song_column.addWidget(self.title_label)
        song_column.addWidget(self.song_search)
        song_column.addWidget(self.song_list, 1)

        lyric_column = QVBoxLayout()
        lyric_column.setSpacing(12)
        lyric_column.addWidget(self.lyrics, 6)
        timeline_row = QHBoxLayout()
        timeline_row.addWidget(self.waveform, 1)
        timeline_row.addWidget(self.time_label)
        lyric_column.addLayout(timeline_row)

        content_row.addLayout(song_column, 1)
        content_row.addLayout(lyric_column, 3)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.auto_button)
        mode_row.addWidget(self.ai_button)
        mode_row.addWidget(self.user_button)
        mode_row.addStretch()

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(18)
        metrics.setVerticalSpacing(10)
        metrics.addWidget(QLabel("麦克风电平"), 0, 0)
        metrics.addWidget(self.level, 0, 1)
        metrics.addWidget(QLabel("麦克风阈值"), 0, 2)
        metrics.addWidget(self.mic_threshold_value, 0, 3)
        metrics.addWidget(self.mic_threshold, 1, 0, 1, 4)
        metrics.addWidget(QLabel("AI人声能量"), 2, 0)
        metrics.addWidget(self.ai_energy, 2, 1)
        metrics.addWidget(QLabel("AI人声阈值"), 2, 2)
        metrics.addWidget(self.ai_threshold_value, 2, 3)
        metrics.addWidget(self.ai_threshold, 3, 0, 1, 4)

        self.controls_panel = QFrame()
        self.controls_panel.setObjectName("ControlGroup")
        self.controls_panel.setMaximumHeight(124)
        controls_layout = QVBoxLayout(self.controls_panel)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setSpacing(10)
        controls_layout.addWidget(self.start_button, 0, Qt.AlignLeft)
        controls_layout.addLayout(mode_row)

        self.metrics_panel = QFrame()
        self.metrics_panel.setObjectName("ControlGroup")
        self.metrics_panel.setMaximumHeight(124)
        metrics_panel_layout = QVBoxLayout(self.metrics_panel)
        metrics_panel_layout.setContentsMargins(16, 12, 16, 12)
        metrics_panel_layout.setSpacing(0)
        metrics_panel_layout.addLayout(metrics)

        config_row = QHBoxLayout()
        config_row.setSpacing(24)
        config_row.addWidget(self.controls_panel, 1)
        config_row.addWidget(self.metrics_panel, 2)

        panel_layout.addLayout(content_row, 6)
        panel_layout.addWidget(self.status)
        panel_layout.addLayout(config_row, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(self.timer_interval_ms)
        self.start_microphone_monitor()

    def make_mode_button(self, text: str, value: str) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.clicked.connect(lambda checked, mode=value: self.set_mode(mode))
        self.mode_buttons.addButton(button)
        return button

    def set_jobs(self, jobs: list[dict]) -> None:
        current_job_id = self.current_job_id()
        self.jobs = [job for job in jobs if job["type"] == "song_process" and job["status"] == "success"]
        self.filtered_jobs = list(self.jobs)
        search = self.song_search.text().strip()
        if search:
            self.filtered_jobs = self.matching_song_tasks(search)
        self.populate_song_list(self.filtered_jobs, current_job_id)

    def populate_song_list(self, jobs: list[dict], preferred_job_id: int | None = None) -> None:
        blocked = self.song_list.blockSignals(True)
        self.song_list.clear()
        for job in jobs:
            item = QListWidgetItem(self.song_task_label(job))
            item.setData(Qt.UserRole, job["id"])
            item.setSizeHint(QSize(0, 58))
            self.song_list.addItem(item)
            self.song_list.setItemWidget(item, self.make_song_row(job))
        self.song_list.blockSignals(blocked)
        target_row = 0
        if preferred_job_id is not None:
            for row in range(self.song_list.count()):
                if self.song_list.item(row).data(Qt.UserRole) == preferred_job_id:
                    target_row = row
                    break
        if self.song_list.count():
            self.song_list.setCurrentRow(target_row)
        self.update_title_from_current_job()
        self.update_song_row_states()

    def make_song_row(self, job: dict) -> QWidget:
        delete_button = QPushButton("")
        delete_button.setObjectName("IconDangerButton")
        delete_button.setToolTip("\u5220\u9664\u6b4c\u66f2")
        delete_button.setFixedSize(34, 34)
        delete_button.setCursor(Qt.PointingHandCursor)
        if DELETE_ICON_PATH.exists():
            delete_button.setIcon(QIcon(str(DELETE_ICON_PATH)))
            delete_button.setIconSize(QSize(22, 22))
        delete_button.clicked.connect(lambda checked=False, job_id=job["id"]: self.delete_song_by_id(int(job_id)))
        row = SongListRow(self.song_task_label(job), delete_button)
        row.setProperty("job_id", int(job["id"]))
        return row

    def update_song_row_states(self) -> None:
        for row_index in range(self.song_list.count()):
            item = self.song_list.item(row_index)
            row = self.song_list.itemWidget(item)
            if row is None:
                continue
            is_playing = self.playing_job_id is not None and item.data(Qt.UserRole) == self.playing_job_id
            row.setProperty("playing", is_playing)
            row.style().unpolish(row)
            row.style().polish(row)

    def filter_song_tasks(self, text: str) -> None:
        current_job_id = self.current_job_id()
        self.filtered_jobs = self.matching_song_tasks(text)
        self.populate_song_list(self.filtered_jobs, current_job_id)

    def matching_song_tasks(self, text: str) -> list[dict]:
        keyword = text.strip().lower()
        if not keyword:
            return list(self.jobs)
        return [job for job in self.jobs if keyword in self.song_task_label(job).lower()]

    def toggle_playback(self) -> None:
        if self.is_playing:
            self.stop()
        else:
            self.start()

    def play_song_item(self, item: QListWidgetItem) -> None:
        self.song_list.setCurrentItem(item)
        self.start()

    def delete_current_song(self) -> None:
        job = self.current_job()
        if job:
            self.delete_song(job)

    def delete_song_by_id(self, job_id: int) -> None:
        for row in range(self.song_list.count()):
            item = self.song_list.item(row)
            if item.data(Qt.UserRole) == job_id:
                self.song_list.setCurrentRow(row)
                break
        job = self.current_job()
        if job:
            self.delete_song(job)

    def delete_song(self, job: dict) -> None:
        if not job:
            return
        if self.is_playing and self.current_job_id() == job["id"]:
            self.stop()
        confirm = QMessageBox.question(
            self,
            "\u5220\u9664\u6b4c\u66f2",
            f"\u786e\u5b9a\u5220\u9664\u300c{self.song_task_label(job)}\u300d\u5417\uff1f",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.api.delete_job(int(job["id"]))
            self.jobs = [item for item in self.jobs if item.get("id") != job["id"]]
            self.filtered_jobs = self.matching_song_tasks(self.song_search.text())
            self.populate_song_list(self.filtered_jobs)
            self.status.setText("\u6b4c\u66f2\u5df2\u5220\u9664")
        except Exception as exc:
            self.status.setText(f"\u5220\u9664\u5931\u8d25: {exc}")

    def start(self) -> None:
        job = self.current_job()
        if not job:
            self.status.setText("没有可播放的歌曲任务，请先到任务与上传处理歌曲。")
            return
        targets = self.song_asset_targets(job)
        try:
            if self.song_assets_missing(targets):
                self.start_song_asset_download(job, targets)
                return
            self.load_and_play_song(job, targets)
        except Exception as exc:
            self.status.setText(f"播放失败: {exc}")
            self.start_microphone_monitor()

    def stop(self) -> None:
        self.engine.stop()
        self.start_microphone_monitor()
        self.playing_job_id = None
        self.set_playing_state(False, self.song_task_label(self.current_job()) if self.current_job() else "")
        self.status.setText("")
        self.status.setObjectName("SubtleText")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def set_playing_state(self, is_playing: bool, song_name: str) -> None:
        self.is_playing = is_playing
        self.start_button.setText("停止" if is_playing else "播放")
        self.start_button.setObjectName("DangerButton" if is_playing else "PrimaryButton")
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)
        if song_name:
            self.title_label.setText(song_name)
        self.status.setText("")
        self.update_song_row_states()

    def tick(self) -> None:
        mic_level = self.engine.input_level if self.is_playing else self.meter.level
        mic_threshold = self.mic_threshold.value() / 1000.0
        ai_threshold = self.ai_threshold.value() / 1000.0
        ai_energy = self.engine.ai_voice_energy()
        target_ai_enabled = self.should_enable_ai_voice(mic_level, ai_energy, mic_threshold, ai_threshold)
        ai_enabled = self.stabilize_ai_voice_decision(target_ai_enabled, self.timer_interval_ms)
        self.engine.set_ai_voice_enabled(ai_enabled)
        self.level.setText(f"{mic_level:.3f}")
        self.mic_threshold_value.setText(f"{mic_threshold:.3f}")
        self.ai_energy.setText(f"{ai_energy:.3f}")
        self.ai_threshold_value.setText(f"{ai_threshold:.3f}")
        self.waveform.set_progress(self.engine.progress_percent)
        self.time_label.setText(
            f"{self.format_seconds(self.engine.position_seconds)} / {self.format_seconds(self.engine.duration_seconds)}"
        )
        self.render_lyrics()

    def song_asset_targets(self, job: dict) -> dict[str, Path]:
        cache_dir = Path("data/client_cache")
        return {
            "ai_vocal": cache_dir / f"job_{job['id']}_ai_vocal.wav",
            "instrumental": cache_dir / f"job_{job['id']}_instrumental.wav",
            "lyrics": cache_dir / f"job_{job['id']}_lyrics.lrc",
        }

    def song_assets_missing(self, targets: dict[str, Path]) -> bool:
        return any(not path.exists() for path in targets.values())

    def start_song_asset_download(self, job: dict, targets: dict[str, Path], auto_start: bool = True) -> None:
        if self.download_thread is not None and self.download_thread.isRunning():
            QMessageBox.warning(self, "\u6b63\u5728\u4e0b\u8f7d", "\u6b4c\u66f2\u6587\u4ef6\u6b63\u5728\u4e0b\u8f7d\uff0c\u8bf7\u7a0d\u540e\u3002")
            return
        self.pending_download_job = job
        self.pending_download_targets = targets
        self.download_dialog = QProgressDialog("\u6b63\u5728\u4e0b\u8f7d\u6b4c\u66f2\u6587\u4ef6...", "", 0, 100, self)
        self.download_dialog.setWindowTitle("\u8bf7\u7a0d\u5019")
        self.download_dialog.setCancelButton(None)
        self.download_dialog.setWindowModality(Qt.WindowModal)
        self.download_dialog.setMinimumDuration(0)
        self.download_dialog.setValue(0)
        self.download_dialog.show()
        self.status.setText("\u6b63\u5728\u4e0b\u8f7d\u6b4c\u66f2\u6587\u4ef6...")

        self.download_thread = QThread(self)
        self.download_worker = SongAssetsDownloadWorker(self.api, job, targets)
        self.download_worker.moveToThread(self.download_thread)
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.progress.connect(self.on_song_asset_download_progress)
        self.download_worker.finished.connect(self.on_song_asset_download_finished)
        self.download_worker.failed.connect(self.on_song_asset_download_failed)
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_worker.failed.connect(self.download_thread.quit)
        self.download_worker.finished.connect(self.download_worker.deleteLater)
        self.download_worker.failed.connect(self.download_worker.deleteLater)
        self.download_thread.finished.connect(self.clear_song_asset_download_state)
        self.download_thread.finished.connect(self.download_thread.deleteLater)
        if auto_start:
            self.download_thread.start()

    def on_song_asset_download_progress(self, kind: str, file_index: int, total_files: int, overall_percent: int) -> None:
        if self.download_dialog:
            if kind:
                self.download_dialog.setLabelText(f"\u6b63\u5728\u4e0b\u8f7d {kind} ({file_index}/{total_files})")
            self.download_dialog.setValue(max(0, min(100, overall_percent)))

    def on_song_asset_download_finished(self) -> None:
        if self.download_dialog:
            self.download_dialog.setValue(100)
            self.download_dialog.close()
        job = self.pending_download_job
        targets = self.pending_download_targets
        if job and targets:
            try:
                self.load_and_play_song(job, targets)
            except Exception as exc:
                self.status.setText(f"鎾斁澶辫触: {exc}")
                self.start_microphone_monitor()

    def on_song_asset_download_failed(self, message: str) -> None:
        if self.download_dialog:
            self.download_dialog.close()
        self.status.setText(f"\u4e0b\u8f7d\u5931\u8d25: {message}")
        QMessageBox.warning(self, "\u4e0b\u8f7d\u5931\u8d25", message)
        self.start_microphone_monitor()

    def clear_song_asset_download_state(self) -> None:
        self.download_thread = None
        self.download_worker = None
        self.download_dialog = None
        self.pending_download_job = None
        self.pending_download_targets = None

    def load_and_play_song(self, job: dict, targets: dict[str, Path]) -> None:
        self.engine.load_layers(targets["ai_vocal"], targets["instrumental"])
        self.waveform.set_peaks(self.engine.waveform_peaks())
        self.load_lyrics(targets["lyrics"])
        self.stop_microphone_monitor()
        self.engine.start()
        self.playing_job_id = int(job["id"])
        self.set_playing_state(True, self.song_task_label(job))

    def download_song_assets(self, job: dict, targets: dict[str, Path]) -> None:
        missing = [(kind, path) for kind, path in targets.items() if not path.exists()]
        if not missing:
            return
        progress = QProgressDialog("正在下载歌曲文件...", "取消", 0, len(missing), self)
        progress.setWindowTitle("请稍候")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        for index, (kind, path) in enumerate(missing, start=1):
            progress.setLabelText(f"正在下载 {kind} ({index}/{len(missing)})")

            def update_progress(done: int, total: int, file_kind=kind) -> None:
                if total > 0:
                    percent = int(done * 100 / total)
                    progress.setLabelText(f"正在下载 {file_kind}: {percent}%")

            self.api.download_job_file_from_job(job, kind, path, update_progress)
            progress.setValue(index)
            if progress.wasCanceled():
                raise RuntimeError("下载已取消")
        progress.close()

    def start_microphone_monitor(self) -> None:
        try:
            self.meter.start()
            if self.status.objectName() == "ErrorText":
                self.status.setText("")
                self.status.setObjectName("SubtleText")
                self.status.style().unpolish(self.status)
                self.status.style().polish(self.status)
        except Exception as exc:
            self.show_microphone_error(exc)

    def stop_microphone_monitor(self) -> None:
        self.meter.stop()

    def show_microphone_error(self, exc: Exception) -> None:
        self.status.setText(f"未检测到可用麦克风: {exc}")
        self.status.setObjectName("ErrorText")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def should_enable_ai_voice(
        self,
        mic_level: float,
        ai_energy: float,
        mic_threshold: float,
        ai_threshold: float,
    ) -> bool:
        if self.mode == "ai":
            return mic_level >= mic_threshold
        if self.mode == "user":
            return False
        return ai_energy >= ai_threshold and mic_level >= mic_threshold

    def stabilize_ai_voice_decision(self, target_enabled: bool, elapsed_ms: int) -> bool:
        if target_enabled == self.ai_voice_enabled:
            self.pending_ai_voice_state = None
            self.pending_ai_voice_elapsed_ms = 0
            return self.ai_voice_enabled
        if self.pending_ai_voice_state != target_enabled:
            self.pending_ai_voice_state = target_enabled
            self.pending_ai_voice_elapsed_ms = 0
        self.pending_ai_voice_elapsed_ms += elapsed_ms
        delay_ms = self.ai_voice_on_delay_ms if target_enabled else self.ai_voice_off_delay_ms
        if self.pending_ai_voice_elapsed_ms >= delay_ms:
            self.ai_voice_enabled = target_enabled
            self.pending_ai_voice_state = None
            self.pending_ai_voice_elapsed_ms = 0
        return self.ai_voice_enabled

    def current_job(self) -> dict | None:
        job_id = self.current_job_id()
        for job in self.jobs:
            if job["id"] == job_id:
                return job
        return None

    def current_job_id(self) -> int | None:
        item = self.song_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def update_title_from_current_job(self, *args) -> None:
        job = self.current_job()
        self.title_label.setText(self.song_task_label(job) if job else "请选择歌曲")

    def song_task_label(self, job: dict) -> str:
        metadata_json = job.get("metadata_json")
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            task_name = str(metadata.get("task_name") or "").strip()
            if task_name:
                return task_name
        return f"任务 {job['id']}"

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.pending_ai_voice_state = None
        self.pending_ai_voice_elapsed_ms = 0

    def save_thresholds(self) -> None:
        self.settings.setValue("playback/mic_threshold", self.mic_threshold.value())
        self.settings.setValue("playback/ai_threshold", self.ai_threshold.value())

    def seek(self, percent: int) -> None:
        self.engine.seek_percent(percent)
        self.waveform.set_progress(percent)

    def load_lyrics(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8", errors="ignore")
        self.lyric_lines = parse_lyrics(content)
        self.render_lyrics()

    def render_lyrics(self) -> None:
        if not self.lyric_lines:
            self.lyrics.setPlainText("暂无歌词")
            return
        current_index = self.current_lyric_index(self.engine.position_seconds)
        html = []
        for index, line in enumerate(self.lyric_lines):
            text = escape(line.text) if line.text else "&nbsp;"
            if index == current_index:
                html.append(f'<p align="center" style="color:#1f6fd1;font-weight:700;font-size:34px;">{text}</p>')
            else:
                html.append(f'<p align="center" style="color:#526170;font-size:26px;">{text}</p>')
        self.lyrics.setHtml("".join(html))
        if current_index is not None:
            self.scroll_lyrics_to_index(current_index)

    def scroll_lyrics_to_index(self, index: int) -> None:
        cursor = self.lyrics.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(index):
            cursor.movePosition(QTextCursor.NextBlock)
        self.lyrics.setTextCursor(cursor)
        self.lyrics.ensureCursorVisible()
        scrollbar = self.lyrics.verticalScrollBar()
        block_rect = self.lyrics.cursorRect(cursor)
        target = scrollbar.value() + block_rect.center().y() - self.lyrics.viewport().height() // 2
        scrollbar.setValue(max(scrollbar.minimum(), min(scrollbar.maximum(), target)))

    def current_lyric_index(self, seconds: float) -> int | None:
        timed = [(index, line) for index, line in enumerate(self.lyric_lines) if line.time_seconds is not None]
        if not timed:
            return None
        current = timed[0][0]
        for index, line in timed:
            if line.time_seconds is not None and line.time_seconds <= seconds:
                current = index
            else:
                break
        return current

    def format_seconds(self, seconds: float) -> str:
        total = max(0, int(seconds))
        minutes = total // 60
        secs = total % 60
        return f"{minutes:02d}:{secs:02d}"
