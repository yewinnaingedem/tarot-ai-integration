# mcp_app/logger.py
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "backend.log")

def _setup() -> logging.Logger:
    logger = logging.getLogger("tarot_backend")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s  {\"file\":\"%(filename)s\",\"line\":%(lineno)d}",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file: 5MB max, keep 7 files
    fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Also print to console
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger

logger = _setup()
