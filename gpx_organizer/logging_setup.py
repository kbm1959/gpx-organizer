"""Application logging setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_app_paths


LOGGER_NAME = "gpx_organizer"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure console + rotating file logging and return app logger."""
    paths = get_app_paths()
    paths.base_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        filename=paths.log_file,
        maxBytes=1_000_000,
        backupCount=3,
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
