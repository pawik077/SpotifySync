import logging
from logging.handlers import RotatingFileHandler


def setup_logger(log_file: str = "sync.log") -> logging.Logger:
    logger = logging.getLogger("SpotifySync")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(file_handler)
    return logger
