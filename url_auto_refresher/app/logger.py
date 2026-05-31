from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from utils import logs_dir


LOGGER_NAME = "url_auto_refresher"


def get_runtime_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = logs_dir() / "runtime.log"
    existing_paths = {
        getattr(handler, "baseFilename", None)
        for handler in logger.handlers
        if isinstance(handler, RotatingFileHandler)
    }
    if str(log_path) not in existing_paths:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)

    return logger
