from __future__ import annotations

from logging.handlers import RotatingFileHandler
import logging

from services.runtime_paths import LOGS_DIR


LOG_PATH = LOGS_DIR / "checkfiscal.log"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("checkfiscal")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = configure_logging()
