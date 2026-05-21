"""Centralized logging configuration for MAYA."""
import logging
import os
import sys
from collections import deque
from datetime import datetime

import config

# In-memory log buffer for Streamlit UI
_log_buffer = deque(maxlen=1000)


class BufferHandler(logging.Handler):
    """Handler that writes log records to an in-memory deque for UI display."""

    def emit(self, record):
        try:
            msg = self.format(record)
            _log_buffer.append(msg)
        except Exception:
            self.handleError(record)


def get_log_buffer():
    """Return the in-memory log buffer contents as a list."""
    return list(_log_buffer)


def setup_logging(level=None):
    """Configure logging with file (in logs/<year>/runs/), console, and memory buffer handlers."""
    level = level or config.LOG_LEVEL
    runs_path = config.runs_dir()
    os.makedirs(runs_path, exist_ok=True)

    log_file = os.path.join(
        runs_path,
        'maya_{}.log'.format(datetime.now().strftime('%Y%m%d'))
    )

    fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

    root = logging.getLogger('maya')
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return root

    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # Memory buffer handler (for Streamlit UI)
    bh = BufferHandler()
    bh.setFormatter(formatter)
    root.addHandler(bh)

    return root


def get_logger(name):
    """Get a named logger under the maya namespace."""
    return logging.getLogger('maya.{}'.format(name))
