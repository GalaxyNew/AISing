from pathlib import Path
import sys


APP_NAME = "妙唱"
APP_DISPLAY_NAME = "妙唱"


def resource_path(relative_path: str) -> Path:
    if getattr(sys, "_MEIPASS", None):
        base_path = Path(sys._MEIPASS) / "aising_client"
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


APP_ICON_PATH = resource_path("resources/miaochang.png")
APP_ICON_ICO_PATH = resource_path("resources/miaochang.ico")
DELETE_ICON_PATH = resource_path("resources/delete.png")
