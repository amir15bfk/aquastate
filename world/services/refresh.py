"""Single-flight refresh lock shared by the page button and the scheduler."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings


@contextmanager
def refresh_lock(max_age_seconds: int = 7200):
    path = Path(settings.WORLD_DATA_DIR) / ".refresh.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    acquired = False
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}".encode())
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0
            if age > max_age_seconds:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            break
    try:
        yield acquired
    finally:
        if acquired:
            try:
                path.unlink()
            except OSError:
                pass
