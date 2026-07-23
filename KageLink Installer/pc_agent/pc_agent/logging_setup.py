from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import PROJECT_DIR


class SecretFilter(logging.Filter):
    _token = re.compile(r"(?i)(token\s*[=:]\s*)([^\s,;]+)")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = self._token.sub(lambda m: m.group(1) + self._mask(m.group(2)), message)
        record.args = ()
        return True

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) <= 8:
            return "********"
        return value[:4] + "..." + value[-4:]


def configure_logging() -> logging.Logger:
    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("kagelink")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_dir / "kagelink.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"))
    handler.addFilter(SecretFilter())
    logger.addHandler(handler)
    return logger
