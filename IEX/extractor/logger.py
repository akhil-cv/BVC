"""
Structured JSON logging for Extractor agent.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "name", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info"
            }:
                log_data[key] = value

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


def setup_logger(
    name: str,
    log_file: str,
    level: str = "INFO",
    json_format: bool = True,
    rotate_daily: bool = True,
    keep_days: int = 7,
) -> logging.Logger:
    """Set up a logger with file and console handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    logger.handlers.clear()

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if rotate_daily:
        handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=keep_days,
            encoding="utf-8",
        )
    else:
        handler = logging.FileHandler(log_file, encoding="utf-8")

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))

    logger.addHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(console)

    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)