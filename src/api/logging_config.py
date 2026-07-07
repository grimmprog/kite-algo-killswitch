"""Logging configuration for the Multi-User Web Trading Platform.

Provides a consistent log format and configurable log level/output.

Requirements covered:
- 2.3.7: Log all errors with full context
- 5.3.1: Log all errors to file
- 2.6.3: Include comprehensive logging
"""

import logging
import os
import sys


def configure_logging() -> None:
    """Configure application-wide logging.

    Reads configuration from environment variables:
    - LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO
    - LOG_FILE: Optional file path to write logs to. If not set, logs go to stdout only.
    """
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Optional file handler
    log_file = os.environ.get("LOG_FILE")
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    root_logger.info(
        "Logging configured: level=%s, file=%s",
        log_level_name,
        log_file or "stdout only",
    )
