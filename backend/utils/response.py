import time
from typing import Any

def success(data: Any = None, message: str = "success") -> dict:
    return {
        "code": 200,
        "message": message,
        "data": data,
        "timestamp": int(time.time())
    }

def error(code: int = 500, message: str = "error", data: Any = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": data,
        "timestamp": int(time.time())
    }

def paginate(items: list, total: int, page: int, size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size > 0 else 0
    }
