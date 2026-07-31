from __future__ import annotations

import logging
import os
from typing import Any

LOG_PATH = os.environ.get("WICKEDYODA_DND_DEBUG_LOG", "/tmp/wickedyoda_dnd_debug.log")


def get_logger(name: str = "dnd") -> logging.Logger:
    logger = logging.getLogger(name)
    if getattr(logger, "_initialized", False):
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger._initialized = True  # type: ignore[attr-defined]
    return logger


def log_command(logger: logging.Logger, interaction: Any, command: str, **fields: Any) -> None:
    user = getattr(getattr(interaction, "user", None), "id", "unknown")
    guild = getattr(getattr(interaction, "guild", None), "id", "dm")
    params = " ".join(f"{k}={v!r}" for k, v in fields.items() if v not in ("", None, 0, False))
    logger.debug("/dnd %s guild=%s user=%s %s", command, guild, user, params)
