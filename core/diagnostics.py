from __future__ import annotations

import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOGGER_NAME = "astrbot_plugin_anime"
LOG_FILENAME = "anime.log"


class AstrBotForwardHandler(logging.Handler):
    """Forward plugin diagnostics to AstrBot while retaining the file log."""

    def __init__(self, astrbot_logger: object):
        super().__init__()
        self.astrbot_logger = astrbot_logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            if record.levelno >= logging.ERROR:
                method = "error"
            elif record.levelno >= logging.WARNING:
                method = "warning"
            else:
                method = "info"
            getattr(self.astrbot_logger, method)(message)
        except Exception:
            self.handleError(record)


def _remove_old_log_files(path: Path, retention_days: int) -> None:
    cutoff = time.time() - max(1, retention_days) * 24 * 60 * 60
    for rotated in path.parent.glob(f"{path.name}.*"):
        try:
            if rotated.is_file() and rotated.stat().st_mtime < cutoff:
                rotated.unlink()
        except OSError:
            continue


def configure_plugin_logging(data_dir: Path, retention_days: int = 7, astrbot_logger: object | None = None) -> Path:
    """Configure the plugin log and remove rotated files past retention."""
    path = Path(data_dir) / LOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", "") == str(path) or isinstance(handler, AstrBotForwardHandler):
            logger.removeHandler(handler)
            handler.close()

    handler = TimedRotatingFileHandler(
        path,
        when="midnight",
        interval=1,
        backupCount=max(1, retention_days),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    if astrbot_logger is not None:
        forwarder = AstrBotForwardHandler(astrbot_logger)
        forwarder.setFormatter(logging.Formatter("[anime] %(message)s"))
        logger.addHandler(forwarder)
    _remove_old_log_files(path, retention_days)
    return path


def get_plugin_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
