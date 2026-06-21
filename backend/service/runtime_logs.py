"""Read production runtime log files (backend.log / frontend.log) for admin UI."""
from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAX_READ_BYTES = 512_000

LOG_SOURCES: dict[str, Path] = {
    "backend": _PROJECT_ROOT / "backend.log",
    "frontend": _PROJECT_ROOT / "frontend.log",
}


def tail_log_file(source: str, lines: int) -> dict:
    """Return last N lines from a whitelisted log file."""
    key = (source or "backend").lower()
    path = LOG_SOURCES.get(key)
    if not path:
        return {
            "source": key,
            "path": "",
            "exists": False,
            "size_bytes": 0,
            "lines_requested": lines,
            "lines_returned": 0,
            "truncated": False,
            "content": "",
            "message": f"Unknown log source: {source}",
        }

    if not path.is_file():
        return {
            "source": key,
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "lines_requested": lines,
            "lines_returned": 0,
            "truncated": False,
            "content": "",
            "message": "Log file not found",
        }

    size = path.stat().st_size
    read_size = min(size, _MAX_READ_BYTES)
    truncated = size > read_size

    with path.open("rb") as f:
        if read_size < size:
            f.seek(-read_size, 2)
        raw = f.read()

    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    if truncated and text and not text.startswith("\n"):
        text = text.split("\n", 1)[-1]

    all_lines = text.split("\n")
    if all_lines and all_lines[-1] == "":
        all_lines.pop()
    tail = all_lines[-lines:] if lines > 0 else all_lines

    return {
        "source": key,
        "path": str(path),
        "exists": True,
        "size_bytes": size,
        "lines_requested": lines,
        "lines_returned": len(tail),
        "truncated": truncated,
        "content": "\n".join(tail),
        "message": None,
    }
