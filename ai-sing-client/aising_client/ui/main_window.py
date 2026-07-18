from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from aising_client.api import ApiClient
from aising_client.branding import APP_ICON_PATH, APP_NAME
from aising_client.ui.login import LoginWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1240, 780)
        self.theme = "light"
        self.api = ApiClient()
        self.stack = QStackedWidget()
        self.login = LoginWidget(self.api)
        self.login.logged_in.connect(self.show_app)
        self.stack.addWidget(self.login)
        self.setCentralWidget(self.stack)
        self.apply_theme()
        QTimer.singleShot(0, self.login.restore_saved_login)

    def show_app(self, user: dict) -> None:
        from aising_client.ui.jobs import JobsWidget

        self.jobs = JobsWidget(self.api, user, self.toggle_theme, self.logout)
        self.stack.addWidget(self.jobs)
        self.stack.setCurrentWidget(self.jobs)

    def logout(self) -> None:
        self.api.logout()
        self.login.clear_saved_login()
        self.stack.setCurrentWidget(self.login)

    def toggle_theme(self) -> str:
        self.theme = "dark" if self.theme == "light" else "light"
        self.apply_theme()
        return self.theme

    def apply_theme(self) -> None:
        self.setStyleSheet(DARK_STYLE if self.theme == "dark" else LIGHT_STYLE)


BASE_STYLE = """
QMainWindow, QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel#PageTitle {
    font-size: 22px;
    font-weight: 700;
}
QLabel#SectionTitle {
    font-size: 20px;
    font-weight: 700;
}
QLabel#HeroTitle {
    font-size: 34px;
    font-weight: 800;
}
QLabel#Eyebrow {
    font-size: 12px;
    font-weight: 800;
}
QLabel#FeatureLine {
    font-size: 14px;
    font-weight: 700;
}
QLabel#ErrorText {
    font-size: 13px;
    font-weight: 700;
}
QLabel#MetricValue {
    font-size: 18px;
    font-weight: 700;
}
QPushButton {
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton:checked {
    font-weight: 700;
}
QComboBox, QLineEdit {
    border-radius: 6px;
    padding: 7px 10px;
}
QTextEdit {
    border-radius: 8px;
    padding: 12px;
}
QSlider::groove:horizontal {
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QHeaderView::section {
    border: 0;
    padding: 7px;
}
QFrame#Panel {
    border-radius: 12px;
}
QFrame#ControlGroup {
    border-radius: 10px;
}
QFrame#LoginPanel, QFrame#LoginBrandPanel {
    border-radius: 14px;
}
QLabel#SupportQr {
    border-radius: 10px;
    padding: 4px;
}
QLabel#LoginAppIcon {
    border-radius: 24px;
    padding: 10px;
}
"""


LIGHT_STYLE = BASE_STYLE + """
QMainWindow, QWidget {
    background: #f6f7fb;
    color: #111827;
}
QLabel#PageTitle, QLabel#SectionTitle, QLabel#MetricValue, QLabel#HeroTitle {
    color: #111827;
}
QLabel#Eyebrow {
    color: #4f46e5;
}
QLabel#SubtleText {
    color: #667085;
}
QLabel#FeatureLine {
    color: #312e81;
}
QLabel#ErrorText {
    color: #dc2626;
}
QPushButton {
    background: #ffffff;
    color: #111827;
    border: 1px solid #d8e0eb;
}
QPushButton:hover {
    background: #f1f5ff;
}
QPushButton:checked {
    background: #eef2ff;
    border-color: #6366f1;
    color: #3730a3;
}
QPushButton#PrimaryButton {
    background: #4f46e5;
    border-color: #4f46e5;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#DangerButton {
    background: #dc2626;
    border-color: #dc2626;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#DangerButton:hover {
    background: #b91c1c;
    border-color: #b91c1c;
}
QListWidget#SongList {
    background: transparent;
    border: 0;
    outline: 0;
}
QFrame#SongRow {
    background: #ffffff;
    border: 0;
    border-radius: 0;
}
QFrame#SongRow:hover {
    background: #eef6ff;
}
QFrame#SongRow[playing="true"] {
    background: #dbeafe;
    border-left: 4px solid #2563eb;
}
QLabel#SongRowTitle {
    background: transparent;
    color: #1f2937;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#IconDangerButton {
    background: #fff1f2;
    border: 1px solid #fecdd3;
    border-radius: 9px;
    padding: 4px;
}
QPushButton#IconDangerButton:hover {
    background: #ffe4e6;
    border-color: #fb7185;
}
QComboBox, QLineEdit, QTextEdit {
    background: #ffffff;
    border: 1px solid #d8e0eb;
    color: #111827;
}
QSlider::groove:horizontal {
    background: #dbe3ef;
}
QSlider::handle:horizontal {
    background: #4f46e5;
}
QTableWidget {
    background: #ffffff;
    gridline-color: #dce5ee;
    border: 1px solid #d4dde8;
    border-radius: 6px;
}
QHeaderView::section {
    background: #eaf0f7;
    color: #435364;
}
QFrame#Panel {
    background: #ffffff;
    border: 1px solid #dbe3ee;
}
QFrame#ControlGroup {
    background: #f9fbff;
    border: 1px solid #dfe7f1;
}
QFrame#LoginPanel {
    background: #ffffff;
    border: 1px solid #dbe3ee;
}
QFrame#LoginBrandPanel {
    background: #eef2ff;
    border: 1px solid #d9ddff;
}
QLabel#SupportQr {
    background: #ffffff;
    border: 1px solid #dbe3ee;
    color: #667085;
}
QLabel#LoginAppIcon {
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid #d9ddff;
}
"""


DARK_STYLE = BASE_STYLE + """
QMainWindow, QWidget {
    background: #101418;
    color: #e7edf3;
}
QLabel#PageTitle, QLabel#SectionTitle, QLabel#MetricValue {
    color: #f4f8fb;
}
QLabel#SubtleText {
    color: #8f9ba8;
}
QLabel#ErrorText {
    color: #ff7a7a;
}
QPushButton {
    background: #202a33;
    color: #e7edf3;
    border: 1px solid #314150;
}
QPushButton:hover {
    background: #293744;
}
QPushButton:checked {
    background: #1f7a6d;
    border-color: #2fb89f;
    color: #ffffff;
}
QPushButton#PrimaryButton {
    background: #2f7dd1;
    border-color: #4a97e6;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#DangerButton {
    background: #dc2626;
    border-color: #ef4444;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#DangerButton:hover {
    background: #b91c1c;
    border-color: #f87171;
}
QListWidget#SongList {
    background: transparent;
    border: 0;
    outline: 0;
}
QFrame#SongRow {
    background: #151c23;
    border: 0;
    border-radius: 0;
}
QFrame#SongRow:hover {
    background: #1e2a36;
}
QFrame#SongRow[playing="true"] {
    background: #1e3a5f;
    border-left: 4px solid #60a5fa;
}
QLabel#SongRowTitle {
    background: transparent;
    color: #f3f6f8;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#IconDangerButton {
    background: #3f1f27;
    border: 1px solid #7f3844;
    border-radius: 9px;
    padding: 4px;
}
QPushButton#IconDangerButton:hover {
    background: #5b2630;
    border-color: #fb7185;
}
QComboBox, QLineEdit, QTextEdit {
    background: #151c23;
    border: 1px solid #314150;
    color: #f3f6f8;
}
QSlider::groove:horizontal {
    background: #26323d;
}
QSlider::handle:horizontal {
    background: #2fb89f;
}
QTableWidget {
    background: #121920;
    gridline-color: #273540;
    border: 1px solid #273540;
    border-radius: 6px;
}
QHeaderView::section {
    background: #1b2530;
    color: #cdd6df;
}
QFrame#Panel {
    background: #151c23;
    border: 1px solid #273540;
}
QFrame#ControlGroup {
    background: #111820;
    border: 1px solid #273540;
}
QLabel#SupportQr {
    background: #151c23;
    border: 1px solid #314150;
    color: #8f9ba8;
}
QLabel#LoginAppIcon {
    background: #151c23;
    border: 1px solid #314150;
}
"""
