import json
from pathlib import Path
from typing import Callable

import requests
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from aising_client.api import ApiClient
from aising_client.branding import APP_NAME
from aising_client.audio.metadata import audio_title_or_filename
from aising_client.ui.playback import PlaybackWidget
from aising_client.ui.separator import LocalSeparationWidget


class SongUploadDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("上传歌曲处理")
        self.song_path: Path | None = None
        self.lyrics_path: Path | None = None
        self._last_default_name = ""

        self.song_edit = QLineEdit()
        self.song_edit.setReadOnly(True)
        self.song_edit.setPlaceholderText("请选择歌曲文件")
        self.lyrics_edit = QLineEdit()
        self.lyrics_edit.setReadOnly(True)
        self.lyrics_edit.setPlaceholderText("请选择歌词文件")
        self.task_name_edit = QLineEdit()
        self.task_name_edit.setPlaceholderText("任务名称")

        song_button = QPushButton("选择歌曲")
        song_button.clicked.connect(self.choose_song)
        lyrics_button = QPushButton("选择歌词")
        lyrics_button.clicked.connect(self.choose_lyrics)

        song_row = QHBoxLayout()
        song_row.addWidget(self.song_edit, 1)
        song_row.addWidget(song_button)
        lyrics_row = QHBoxLayout()
        lyrics_row.addWidget(self.lyrics_edit, 1)
        lyrics_row.addWidget(lyrics_button)

        form = QFormLayout()
        form.addRow("歌曲文件", song_row)
        form.addRow("歌词文件", lyrics_row)
        form.addRow("任务名称", self.task_name_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("开始上传")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        title = QLabel("上传歌曲和歌词")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self.resize(620, 180)

    def choose_song(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择歌曲文件",
            "",
            "Audio Files (*.wav *.mp3 *.flac *.m4a);;All Files (*)",
        )
        if filename:
            self.set_song_path(Path(filename))

    def choose_lyrics(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择歌词文件",
            "",
            "Lyrics Files (*.lrc *.txt);;All Files (*)",
        )
        if filename:
            self.set_lyrics_path(Path(filename))

    def set_song_path(self, path: Path) -> None:
        old_name = self.task_name_edit.text().strip()
        self.song_path = path
        self.song_edit.setText(str(path))
        default_name = audio_title_or_filename(path)
        if not old_name or old_name == self._last_default_name:
            self.task_name_edit.setText(default_name)
            self._last_default_name = default_name

    def set_lyrics_path(self, path: Path) -> None:
        self.lyrics_path = path
        self.lyrics_edit.setText(str(path))

    def accept(self) -> None:
        if self.song_path is None:
            QMessageBox.warning(self, "缺少歌曲", "请先选择歌曲文件。")
            return
        if self.lyrics_path is None:
            QMessageBox.warning(self, "缺少歌词", "请先选择歌词文件。")
            return
        if not self.task_name_edit.text().strip():
            QMessageBox.warning(self, "缺少任务名称", "请填写任务名称。")
            return
        super().accept()

    def values(self) -> tuple[Path, Path, str]:
        if self.song_path is None or self.lyrics_path is None:
            raise ValueError("Song and lyrics paths are required")
        return self.song_path, self.lyrics_path, self.task_name_edit.text().strip()


class UploadWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        api: ApiClient,
        job_type: str,
        voice_path: Path | None = None,
        song_path: Path | None = None,
        lyrics_path: Path | None = None,
        task_name: str = "",
    ) -> None:
        super().__init__()
        self.api = api
        self.job_type = job_type
        self.voice_path = voice_path
        self.song_path = song_path
        self.lyrics_path = lyrics_path
        self.task_name = task_name

    @Slot()
    def run(self) -> None:
        try:
            if self.job_type == "voice_train":
                if self.voice_path is None:
                    raise ValueError("Voice path is required")
                result = self.api.create_voice_train_job(self.voice_path)
            elif self.job_type == "song_process":
                if self.song_path is None or self.lyrics_path is None:
                    raise ValueError("Song and lyrics paths are required")
                result = self.api.create_song_process_job(self.song_path, self.lyrics_path, self.task_name)
            else:
                raise ValueError(f"Unknown upload job type: {self.job_type}")
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class JobsWidget(QWidget):
    def __init__(
        self,
        api: ApiClient,
        user: dict,
        on_theme_toggle: Callable[[], str],
        on_logout: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.api = api
        self.user = user
        self.on_theme_toggle = on_theme_toggle
        self.on_logout = on_logout
        self.refresh_interval_ms = 8000
        self.stack = QStackedWidget()
        self.playback = PlaybackWidget(api)
        self.tasks = TasksPage(api, user, self.refresh_jobs, self.show_playback)
        self.separator = LocalSeparationWidget()
        self.profile = ProfilePage(api)
        self.stack.addWidget(self.playback)
        self.stack.addWidget(self.tasks)
        self.stack.addWidget(self.separator)
        self.stack.addWidget(self.profile)

        self.play_button = QPushButton("播放")
        self.play_button.setCheckable(True)
        self.play_button.setChecked(True)
        self.play_button.clicked.connect(self.show_playback)
        self.tasks_button = QPushButton("任务与上传")
        self.tasks_button.setCheckable(True)
        self.tasks_button.clicked.connect(self.show_tasks)
        self.separator_button = QPushButton("本地分离")
        self.separator_button.setCheckable(True)
        self.separator_button.clicked.connect(self.show_separator)
        self.profile_button = QPushButton("我的")
        self.profile_button.setCheckable(True)
        self.profile_button.clicked.connect(self.show_profile)
        self.theme_button = QPushButton("切换深色")
        self.theme_button.clicked.connect(self.toggle_theme)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh_jobs)
        self.logout_button = QPushButton("\u9000\u51fa\u767b\u5f55")
        self.logout_button.setObjectName("DangerButton")
        self.logout_button.setMinimumHeight(38)
        self.logout_button.clicked.connect(self.logout)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("PageTitle")
        user_label = QLabel(user["username"])
        user_label.setObjectName("SubtleText")
        header.addWidget(title)
        header.addSpacing(22)
        header.addWidget(self.play_button)
        header.addWidget(self.tasks_button)
        header.addWidget(self.separator_button)
        header.addWidget(self.profile_button)
        header.addStretch()
        header.addWidget(user_label)
        header.addWidget(refresh_button)
        header.addWidget(self.theme_button)
        header.addWidget(self.logout_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(self.stack, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(self.refresh_interval_ms)
        self.timer.timeout.connect(self.refresh_jobs)
        self.refresh_jobs()

    def show_playback(self) -> None:
        self.stack.setCurrentWidget(self.playback)
        self.play_button.setChecked(True)
        self.tasks_button.setChecked(False)
        self.separator_button.setChecked(False)
        self.profile_button.setChecked(False)

    def show_tasks(self) -> None:
        self.stack.setCurrentWidget(self.tasks)
        self.play_button.setChecked(False)
        self.tasks_button.setChecked(True)
        self.separator_button.setChecked(False)
        self.profile_button.setChecked(False)

    def show_separator(self) -> None:
        self.stack.setCurrentWidget(self.separator)
        self.play_button.setChecked(False)
        self.tasks_button.setChecked(False)
        self.separator_button.setChecked(True)
        self.profile_button.setChecked(False)

    def show_profile(self) -> None:
        self.profile.refresh()
        self.stack.setCurrentWidget(self.profile)
        self.play_button.setChecked(False)
        self.tasks_button.setChecked(False)
        self.separator_button.setChecked(False)
        self.profile_button.setChecked(True)

    def toggle_theme(self) -> None:
        theme = self.on_theme_toggle()
        self.theme_button.setText("切换浅色" if theme == "dark" else "切换深色")

    def logout(self) -> None:
        if self.on_logout:
            self.on_logout()

    def refresh_jobs(self) -> None:
        try:
            jobs = self.api.list_jobs()
            self.tasks.set_jobs(jobs)
            song_jobs = [job for job in jobs if job["type"] == "song_process" and job["status"] == "success"]
            self.playback.set_jobs(song_jobs)
            self.update_refresh_timer(jobs)
        except Exception as exc:
            self.tasks.set_status(f"刷新失败: {exc}")
            self.update_refresh_timer([])

    def update_refresh_timer(self, jobs: list[dict]) -> None:
        has_active_job = any(job.get("status") in {"queued", "running"} for job in jobs)
        if has_active_job:
            if self.timer.interval() != self.refresh_interval_ms:
                self.timer.setInterval(self.refresh_interval_ms)
            if not self.timer.isActive():
                self.timer.start()
        elif self.timer.isActive():
            self.timer.stop()


class ProfilePage(QWidget):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.credits_label = QLabel("积分: -")
        self.credits_label.setObjectName("SectionTitle")
        self.support_label = QLabel("")
        self.support_label.setObjectName("SubtleText")
        self.support_qr = QLabel("")
        self.support_qr.setObjectName("SupportQr")
        self.support_qr.setFixedSize(132, 132)
        self.support_qr.setAlignment(Qt.AlignCenter)
        self.support_qr.hide()
        self.rules_label = QLabel("")
        self.records = QTableWidget(0, 3)
        self.records.setHorizontalHeaderLabels(["时间", "积分", "说明"])
        self.records.verticalHeader().setVisible(False)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(12)
        title_row = QHBoxLayout()
        title = QLabel("我的账户")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(refresh_button)
        panel_layout.addLayout(title_row)
        panel_layout.addWidget(self.credits_label)
        info_row = QHBoxLayout()
        support_card = QFrame()
        support_card.setObjectName("ControlGroup")
        support_layout = QVBoxLayout(support_card)
        support_layout.setContentsMargins(16, 14, 16, 14)
        support_layout.addWidget(QLabel("客服与充值"))
        support_layout.addWidget(self.support_label)
        support_layout.addWidget(self.support_qr, 0, Qt.AlignHCenter)
        rules_card = QFrame()
        rules_card.setObjectName("ControlGroup")
        rules_layout = QVBoxLayout(rules_card)
        rules_layout.setContentsMargins(16, 14, 16, 14)
        rules_layout.addWidget(QLabel("积分规则"))
        rules_layout.addWidget(self.rules_label)
        info_row.addWidget(support_card)
        info_row.addWidget(rules_card)
        panel_layout.addLayout(info_row)
        panel_layout.addWidget(QLabel("积分消费记录"))
        panel_layout.addWidget(self.records, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

    def refresh(self) -> None:
        profile = self.api.profile()
        transactions = self.api.credit_transactions()
        config = profile["config"]
        support = profile["support"]
        self.credits_label.setText(f"当前积分: {profile['credits']}")
        self.support_label.setText(f"开通/充值请联系客服: {support.get('name', '官方客服')}")
        self.load_support_qr(support.get("qr_code_url", ""))
        self.rules_label.setText(
            f"充值价格: 1积分={config['recharge_price_per_credit']}元；"
            f"干声训练消耗{config['voice_train_cost']}积分；歌曲处理消耗{config['song_process_cost']}积分。"
        )
        self.records.setRowCount(len(transactions))
        for row, item in enumerate(transactions):
            self.records.setItem(row, 0, QTableWidgetItem(str(item.get("created_at", ""))))
            self.records.setItem(row, 1, QTableWidgetItem(str(item.get("amount", ""))))
            self.records.setItem(row, 2, QTableWidgetItem(str(item.get("note", ""))))

    def load_support_qr(self, url: str) -> None:
        self.support_qr.hide()
        self.support_qr.clear()
        if not url:
            return
        self.support_qr.show()
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                self.support_qr.setPixmap(pixmap.scaled(126, 126, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        except Exception:
            pass
        self.support_qr.setText("客服二维码")


class TasksPage(QWidget):
    def __init__(self, api: ApiClient, user: dict, on_refresh: Callable[[], None], on_back: Callable[[], None]) -> None:
        super().__init__()
        self.api = api
        self.user = user
        self.on_refresh = on_refresh
        self.upload_thread: QThread | None = None
        self.upload_worker: UploadWorker | None = None
        self.upload_dialog: QProgressDialog | None = None
        self.status = QLabel("")
        self.status.setObjectName("SubtleText")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "类型", "任务名", "状态", "进度", "输出", "错误"])
        self.table.verticalHeader().setVisible(False)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("任务与上传")
        title.setObjectName("SectionTitle")
        back_button = QPushButton("返回播放")
        back_button.clicked.connect(on_back)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(back_button)

        hint = QLabel("训练和歌曲处理会按当前积分规则扣费，提交前会弹窗确认。")
        hint.setObjectName("SubtleText")

        voice_button = QPushButton("上传干音并训练")
        voice_button.setObjectName("PrimaryButton")
        voice_button.clicked.connect(self.upload_voice)
        song_button = QPushButton("上传歌曲并处理")
        song_button.clicked.connect(self.upload_song)
        refresh_button = QPushButton("刷新任务")
        refresh_button.clicked.connect(on_refresh)

        controls = QHBoxLayout()
        controls.addWidget(voice_button)
        controls.addWidget(song_button)
        controls.addWidget(refresh_button)
        controls.addStretch()

        panel_layout.addLayout(title_row)
        panel_layout.addWidget(hint)
        rules = QHBoxLayout()
        voice_rule = QLabel("干声训练: 训练专属音色模型")
        song_rule = QLabel("歌曲处理: 生成 AI 人声与伴奏缓存")
        voice_rule.setObjectName("SubtleText")
        song_rule.setObjectName("SubtleText")
        rules.addWidget(voice_rule)
        rules.addWidget(song_rule)
        rules.addStretch()
        panel_layout.addLayout(rules)
        panel_layout.addLayout(controls)
        panel_layout.addWidget(self.status)
        panel_layout.addWidget(self.table, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)

    def upload_voice(self) -> None:
        path = self.choose_file()
        if path and self.confirm_credit_cost("voice_train"):
            self.start_upload_task("voice_train", voice_path=path)

    def upload_song(self) -> None:
        dialog = SongUploadDialog(self)
        if dialog.exec() != QDialog.Accepted:
            self.set_status("已取消上传")
            return
        path, lyrics_path, task_name = dialog.values()
        if self.confirm_credit_cost("song_process"):
            self.start_upload_task("song_process", song_path=path, lyrics_path=lyrics_path, task_name=task_name)

    def start_upload_task(
        self,
        job_type: str,
        voice_path: Path | None = None,
        song_path: Path | None = None,
        lyrics_path: Path | None = None,
        task_name: str = "",
        auto_start: bool = True,
    ) -> None:
        if self.is_upload_running():
            QMessageBox.warning(self, "\u6b63\u5728\u4e0a\u4f20", "\u5df2\u6709\u4e00\u4e2a\u4e0a\u4f20\u4efb\u52a1\u6b63\u5728\u8fdb\u884c\uff0c\u8bf7\u7a0d\u540e\u3002")
            return
        label = "\u6b63\u5728\u4e0a\u4f20\u5e72\u58f0\u97f3\u9891..." if job_type == "voice_train" else "\u6b63\u5728\u4e0a\u4f20\u6b4c\u66f2\u548c\u6b4c\u8bcd..."
        self.upload_dialog = QProgressDialog(label, "", 0, 0, self)
        self.upload_dialog.setWindowTitle("\u4e0a\u4f20\u4e2d")
        self.upload_dialog.setCancelButton(None)
        self.upload_dialog.setWindowModality(Qt.WindowModal)
        self.upload_dialog.setMinimumDuration(0)
        self.upload_dialog.show()

        self.upload_thread = QThread(self)
        self.upload_worker = UploadWorker(
            self.api,
            job_type,
            voice_path=voice_path,
            song_path=song_path,
            lyrics_path=lyrics_path,
            task_name=task_name,
        )
        self.upload_worker.moveToThread(self.upload_thread)
        self.upload_thread.started.connect(self.upload_worker.run)
        self.upload_worker.finished.connect(self.on_upload_finished)
        self.upload_worker.failed.connect(self.on_upload_failed)
        self.upload_worker.finished.connect(self.upload_thread.quit)
        self.upload_worker.failed.connect(self.upload_thread.quit)
        self.upload_worker.finished.connect(self.upload_worker.deleteLater)
        self.upload_worker.failed.connect(self.upload_worker.deleteLater)
        self.upload_thread.finished.connect(self.clear_upload_state)
        self.upload_thread.finished.connect(self.upload_thread.deleteLater)
        if auto_start:
            self.upload_thread.start()

    def is_upload_running(self) -> bool:
        if self.upload_thread is None:
            return False
        try:
            return self.upload_thread.isRunning()
        except RuntimeError:
            self.clear_upload_state()
            return False

    def clear_upload_state(self) -> None:
        self.upload_thread = None
        self.upload_worker = None
        self.upload_dialog = None

    def on_upload_finished(self, result: dict) -> None:
        if self.upload_dialog:
            self.upload_dialog.close()
        self.set_status("\u4e0a\u4f20\u5b8c\u6210\uff0c\u4efb\u52a1\u5df2\u63d0\u4ea4")
        self.on_refresh()

    def on_upload_failed(self, message: str) -> None:
        if self.upload_dialog:
            self.upload_dialog.close()
        self.set_status(f"\u4e0a\u4f20\u5931\u8d25: {message}")
        QMessageBox.warning(self, "\u4e0a\u4f20\u5931\u8d25", message)

    def confirm_credit_cost(self, job_type: str) -> bool:
        profile = self.api.profile()
        config = profile["config"]
        cost = config["voice_train_cost"] if job_type == "voice_train" else config["song_process_cost"]
        credits = profile["credits"]
        if credits < cost:
            QMessageBox.warning(self, "积分不足", f"当前积分 {credits}，本次需要 {cost} 积分。")
            return False
        return QMessageBox.question(
            self,
            "确认消耗积分",
            f"本次将消耗 {cost} 积分，当前积分 {credits}。是否继续？",
        ) == QMessageBox.Yes

    def choose_file(self, title: str = "选择音频文件", file_filter: str = "Audio Files (*.wav *.mp3 *.flac *.m4a);;All Files (*)") -> Path | None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            title,
            "",
            file_filter,
        )
        return Path(filename) if filename else None

    def set_jobs(self, jobs: list[dict]) -> None:
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            self.table.setItem(row, 0, QTableWidgetItem(str(job["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(job["type"]))
            self.table.setItem(row, 2, QTableWidgetItem(self.task_name_for_job(job)))
            self.table.setItem(row, 3, QTableWidgetItem(job["status"]))
            self.table.setItem(row, 4, QTableWidgetItem(f"{job['progress']}%"))
            self.table.setItem(row, 5, QTableWidgetItem(job.get("output_path") or ""))
            self.table.setItem(row, 6, QTableWidgetItem(job.get("error_message") or ""))
        self.set_status("任务已刷新")

    def set_status(self, message: str) -> None:
        self.status.setText(message)

    def task_name_for_job(self, job: dict) -> str:
        metadata_json = job.get("metadata_json")
        if not metadata_json:
            return ""
        try:
            metadata = json.loads(metadata_json)
        except (TypeError, json.JSONDecodeError):
            return ""
        return str(metadata.get("task_name") or "")
