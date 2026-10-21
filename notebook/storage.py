"""Portable local storage: reject redirected cache paths and serialize writers."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat


def safe_cache(workspace: Path, *parts: str) -> Path:
    root = workspace.resolve()
    current = root
    for part in (".claude-notebook", *parts):
        if not part or part in (".", "..") or "/" in part or "\\" in part:
            raise ValueError("Invalid cache path.")
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            pass
        else:
            # Path.is_junction() only exists on Python 3.12+. lstat exposes
            # reparse points on older supported Windows interpreters too.
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise ValueError("Notebook cache must not contain symbolic links or junctions.")
        if not current.resolve().is_relative_to(root):
            raise ValueError("Notebook cache escaped the workspace.")
    return current


@contextmanager
def file_lock(path: Path, *, wait=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError as error:
            raise ValueError("Notebook is busy in another session. Wait and refresh.") from error
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
