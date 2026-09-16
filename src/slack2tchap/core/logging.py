"""Logging configuration for slack2tchap."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger and formatters."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers if setup is called multiple times
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Ensure uvicorn and application loggers are enabled and output to stdout
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "slack2tchap"):
        u_log = logging.getLogger(logger_name)
        u_log.disabled = False
        u_log.setLevel(numeric_level)
        u_log.handlers.clear()
        u_log.addHandler(handler)
        u_log.propagate = False

    # Silence overly verbose third-party loggers
    logging.getLogger("nio").setLevel(logging.WARNING)
    logging.getLogger("peewee").setLevel(logging.WARNING)
