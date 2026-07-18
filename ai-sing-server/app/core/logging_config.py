import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_file: str | Path = Path("logs/server.log"), level: str = "INFO", force: bool = False) -> None:
    target = Path(log_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        target,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logging.basicConfig(
        level=numeric_level,
        handlers=[console_handler, file_handler],
        force=force,
    )
