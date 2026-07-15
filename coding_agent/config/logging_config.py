"""Lightweight logging: everything to a file, warnings (or more) to the console."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_file: Path, verbose: bool = False) -> None:
    """Configure the root logger once at startup.

    DEBUG and above go to ``log_file``; the console shows WARNING and above
    (INFO and above with ``verbose``) so it never drowns the chat UI.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    root.handlers = [file_handler, console_handler]

    # Third-party HTTP libraries are extremely chatty at DEBUG level.
    for noisy in ("openai", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.INFO)
