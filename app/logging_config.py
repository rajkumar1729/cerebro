"""
Logging configuration for Cerebro.

Sets up logging for all modules with:
  • Consistent formatting (timestamp, level, module, message)
  • File and console output
  • Docker-aware configuration
  • Structured logging support
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
    in_docker: bool | None = None,
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path. If None, logs only to console.
                  If "auto", creates logs/ directory with dated file.
        in_docker: If True, format for container logging (no file by default).
                   If None, auto-detect from environment.

    Returns:
        Configured logger instance.
    """
    # Auto-detect Docker environment
    if in_docker is None:
        in_docker = os.getenv("DOCKER_CONTAINER") == "true" or os.path.exists("/.dockerenv")

    # Parse log level
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers
    root_logger.handlers.clear()

    # Format: timestamp | level | logger_name | message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if requested)
    if log_file:
        if log_file == "auto":
            # Create logs directory with timestamped file
            log_dir = Path("/data/logs") if in_docker else Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = log_dir / f"cerebro_{timestamp}.log"
        else:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

        # Use rotating file handler to prevent huge files
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,  # Keep 5 backups
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        logging.getLogger("cerebro").info(
            "File logging enabled: %s", log_path
        )

    # Get cerebro logger
    cerebro_logger = logging.getLogger("cerebro")
    cerebro_logger.info("Logging initialized | level=%s | docker=%s", log_level, in_docker)

    return cerebro_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(f"cerebro.{name}")
