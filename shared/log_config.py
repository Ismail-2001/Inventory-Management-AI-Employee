import json
import logging
import logging.config
import sys
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }, default=str)


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter,
        },
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console_json": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "json",
        },
        "console_std": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console_json"],
    },
    "loggers": {
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console_json"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["console_json"],
            "propagate": False,
        },
    },
}


def configure_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)
