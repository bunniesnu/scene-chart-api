import logging
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)


def archive_log(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        log_dir = Path("/app/logs/archive")
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%d_%H%M%S"
        )

        file_handler = logging.FileHandler(
            log_dir / f"{timestamp}.log",
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root_logger.addHandler(file_handler)

        try:
            return func(*args, **kwargs)
        finally:
            root_logger.removeHandler(file_handler)
            file_handler.close()

    return wrapper