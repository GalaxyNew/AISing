import json

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
import requests

from aising_client.api import ApiClient
from aising_client.branding import APP_ICON_PATH, APP_NAME


class LoginWidget(QWidget):
    logged_in = Signal(dict)

    def __init__(self, api: ApiClient, settings: QSettings | None = None) -> None:
        super().__init__()
        self.api = api
        self.settings = settings or QSettings("Miaochang", "Client")
        self.username = QLineEdit()
        self.username.setPlaceholderText("请输入用户名")
        self.password = QLineEdit()
        self.password.setPlaceholderText("请输入密码")
        self.password.setEchoMode(QLineEdit.Password)
        self.remember_check = QCheckBox("\u8bb0\u4f4f\u767b\u5f55\u72b6\u6001\u548c\u5bc6\u7801")
        self.remember_check.setChecked(self.settings.value("auth/remember", True, type=bool))
        self.status = QLabel("")
        self.status.setObjectName("SubtleText")
        self.button = QPushButton("登录控制台")
        self.button.setObjectName("PrimaryButton")
        self.button.clicked.connect(self.handle_login)
        self.register_button = QPushButton("开通账户")
        self.register_button.clicked.connect(self.show_register_help)
        self.support_qr_url = ""

        brand_panel = QFrame()
        brand_panel.setObjectName("LoginBrandPanel")
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(34, 34, 34, 34)
        brand_layout.setSpacing(16)
        eyebrow = QLabel(f"{APP_NAME} Commercial")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(f"{APP_NAME} 实时跟唱")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("管理歌曲播放、训练任务、积分余额与客服充值信息。")
        subtitle.setObjectName("SubtleText")
        app_icon = QLabel("")
        app_icon.setObjectName("LoginAppIcon")
        app_icon.setFixedSize(176, 176)
        app_icon.setAlignment(Qt.AlignCenter)
        if APP_ICON_PATH.exists():
            pixmap = QPixmap(str(APP_ICON_PATH))
            app_icon.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        rule_1 = QLabel("干声训练与歌曲处理按积分扣费")
        rule_2 = QLabel("账号由客服开通，单账号仅允许一端登录")
        rule_1.setObjectName("FeatureLine")
        rule_2.setObjectName("FeatureLine")
        brand_layout.addWidget(eyebrow)
        brand_layout.addWidget(title)
        brand_layout.addWidget(subtitle)
        brand_layout.addStretch()
        brand_layout.addWidget(app_icon, 0, Qt.AlignHCenter)
        brand_layout.addStretch()
        brand_layout.addWidget(rule_1)
        brand_layout.addWidget(rule_2)

        form_panel = QFrame()
        form_panel.setObjectName("LoginPanel")
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(30, 30, 30, 30)
        form_layout.setSpacing(14)
        form_title = QLabel("登录账户")
        form_title.setObjectName("SectionTitle")
        form_hint = QLabel("输入客服开通的用户名和密码")
        form_hint.setObjectName("SubtleText")
        button_row = QHBoxLayout()
        button_row.addWidget(self.button)
        button_row.addWidget(self.register_button)
        self.support_label = QLabel("没有账户？请联系客服开通")
        self.support_label.setObjectName("SubtleText")
        self.support_qr = QLabel("")
        self.support_qr.setObjectName("SupportQr")
        self.support_qr.setFixedSize(138, 138)
        self.support_qr.setAlignment(Qt.AlignCenter)
        self.support_qr.hide()
        form_layout.addWidget(form_title)
        form_layout.addWidget(form_hint)
        form_layout.addSpacing(8)
        form_layout.addWidget(self.username)
        form_layout.addWidget(self.password)
        form_layout.addWidget(self.remember_check)
        form_layout.addLayout(button_row)
        form_layout.addWidget(self.support_label)
        form_layout.addWidget(self.support_qr, 0, Qt.AlignHCenter)
        form_layout.addWidget(self.status)

        shell = QHBoxLayout()
        shell.setSpacing(18)
        shell.addWidget(brand_panel, 5)
        shell.addWidget(form_panel, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(96, 80, 96, 80)
        layout.addLayout(shell)
        self.load_saved_credentials()
        self.load_support_info()

    def handle_login(self) -> None:
        try:
            name = self.username.text().strip()
            password = self.password.text().strip()
            user = self.api.login(name, password)
            self.save_login_state(user, name, password)
            self.logged_in.emit(user)
        except Exception as exc:
            self.status.setText(f"登录失败: {exc}")

    def load_saved_credentials(self) -> None:
        if not self.settings.value("auth/remember", True, type=bool):
            self.remember_check.setChecked(False)
            return
        self.username.setText(str(self.settings.value("auth/username", "") or ""))
        self.password.setText(str(self.settings.value("auth/password", "") or ""))

    def restore_saved_login(self) -> bool:
        if not self.settings.value("auth/remember", True, type=bool):
            return False
        token = str(self.settings.value("auth/token", "") or "")
        if not token:
            return False
        try:
            self.api.token = token
            user = self.api.me()
            user["token"] = token
            self.logged_in.emit(user)
            return True
        except Exception:
            self.clear_saved_login()
            self.api.token = ""
            return False

    def save_login_state(self, user: dict, username: str, password: str) -> None:
        remember = self.remember_check.isChecked()
        self.settings.setValue("auth/remember", remember)
        if not remember:
            self.clear_saved_login()
            return
        self.settings.setValue("auth/username", username)
        self.settings.setValue("auth/password", password)
        self.settings.setValue("auth/token", user.get("token", ""))
        self.settings.setValue("auth/user", json.dumps(user, ensure_ascii=True))

    def clear_saved_login(self) -> None:
        for key in ["auth/username", "auth/password", "auth/token", "auth/user"]:
            self.settings.remove(key)

    def show_register_help(self) -> None:
        try:
            support = self.api.public_support()
        except Exception:
            support = {"name": "官方客服", "qr_code_url": ""}
        dialog = SupportDialog(
            support.get("name") or "官方客服",
            support.get("qr_code_url") or "",
            self,
        )
        dialog.exec()

    def load_support_info(self) -> None:
        try:
            support = self.api.public_support()
        except Exception:
            return
        name = support.get("name") or "官方客服"
        self.support_qr_url = support.get("qr_code_url") or ""
        self.support_label.setText(f"没有账户？请联系{name}开通")
        if self.support_qr_url:
            self.support_qr.show()
            self.load_qr_image(self.support_qr_url)

    def load_qr_image(self, url: str) -> None:
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                self.support_qr.setPixmap(pixmap.scaled(132, 132, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        except Exception:
            pass
        self.support_qr.setText("客服二维码")

class SupportDialog(QDialog):
    def __init__(self, support_name: str, qr_code_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("\u8054\u7cfb\u5ba2\u670d")
        self.setModal(True)
        self.setMinimumWidth(320)

        title = QLabel("\u5f00\u901a\u8d26\u6237\u8bf7\u8054\u7cfb\u5ba2\u670d")
        title.setObjectName("SectionTitle")
        name_label = QLabel(support_name)
        name_label.setObjectName("SubtleText")
        qr_label = QLabel("")
        qr_label.setObjectName("SupportQr")
        qr_label.setFixedSize(210, 210)
        qr_label.setAlignment(Qt.AlignCenter)
        if qr_code_url:
            self.load_qr_image(qr_label, qr_code_url)
        else:
            qr_label.setText("\u6682\u65e0\u5ba2\u670d\u4e8c\u7ef4\u7801")

        close_button = QPushButton("\u77e5\u9053\u4e86")
        close_button.setObjectName("PrimaryButton")
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title, 0, Qt.AlignHCenter)
        layout.addWidget(name_label, 0, Qt.AlignHCenter)
        layout.addWidget(qr_label, 0, Qt.AlignHCenter)
        layout.addWidget(close_button)

    def load_qr_image(self, label: QLabel, url: str) -> None:
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                label.setPixmap(pixmap.scaled(196, 196, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        except Exception:
            pass
        label.setText("\u4e8c\u7ef4\u7801\u52a0\u8f7d\u5931\u8d25")
