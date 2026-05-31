"""Structured logging setup using structlog.

Provides console and rotating file handlers.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import structlog

from agentvoca.utils.errors import ConfigError

_DEFAULT_LOG_DIR = Path.home() / ".agentvoca"
_DEFAULT_LOG_FILE = _DEFAULT_LOG_DIR / "agentvoca.log"
_DEFAULT_LOG_LEVEL = "INFO"


def _get_log_dir() -> Path:
    """Return the log directory, creating it if necessary."""
    log_dir = Path(os.environ.get("agentvoca_LOG_DIR", str(_DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None,
    debug: bool = False,
) -> None:
    """Configure structlog with console and file handlers.

    Args:
        log_level: Override log level string (e.g., "DEBUG", "INFO").
        log_file: Override log file path.
        debug: If True, set log level to DEBUG.

    Raises:
        ConfigError: If the log file path cannot be written to.
    """
    if debug:
        log_level = "DEBUG"
    level = (log_level or _DEFAULT_LOG_LEVEL).upper()

    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ConfigError(f"Invalid log level: {level!r}")

    log_path = log_file or (_get_log_dir() / "agentvoca.log")

    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        log_path.touch(exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"Cannot write to log file {log_path}: {exc}") from exc

    # Remove any pre-existing handlers to avoid duplicates on re-init
    structlog.configure_once(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # File handler (rotating, 10MB max, 3 backups)
    try:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(file_handler)
    except OSError as exc:
        raise ConfigError(f"Cannot open log file {log_path}: {exc}") from exc

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance."""
    return structlog.get_logger(name or __name__)
