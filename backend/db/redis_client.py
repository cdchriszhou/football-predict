import json
import time
from typing import Optional
import redis.asyncio as aioredis
from config import REDIS_URL
from utils.logger import logger

redis_pool: Optional[aioredis.Redis] = None
_cache_mode: str = "none"  # "redis" | "memory" | "none"

# In-memory cache fallback when Redis is unavailable
_mem_cache: dict = {}
_mem_ttl: dict = {}


async def init_redis():
    global redis_pool, _cache_mode
    try:
        redis_pool = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await redis_pool.ping()
        _cache_mode = "redis"
        logger.info("Redis connected — cache enabled")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}, using in-memory cache")
        redis_pool = None
        _cache_mode = "memory"


async def close_redis():
    global redis_pool, _cache_mode
    if redis_pool:
        await redis_pool.close()
        redis_pool = None
    _mem_cache.clear()
    _mem_ttl.clear()
    _cache_mode = "none"


def cache_mode() -> str:
    return _cache_mode


async def cache_get(key: str) -> Optional[dict]:
    # Try Redis first
    if redis_pool:
        try:
            data = await redis_pool.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass

    # Fallback to in-memory cache
    if key in _mem_cache:
        if time.monotonic() < _mem_ttl.get(key, 0):
            return _mem_cache[key]
        else:
            del _mem_cache[key]
            _mem_ttl.pop(key, None)
    return None


async def cache_set(key: str, value: dict, ttl: int = 3600):
    # Try Redis first
    if redis_pool:
        try:
            await redis_pool.setex(key, ttl, json.dumps(value, ensure_ascii=False))
            return
        except Exception:
            pass

    # Fallback to in-memory cache
    _mem_cache[key] = value
    _mem_ttl[key] = time.monotonic() + ttl

    # Prevent unbounded memory growth (keep max 1000 entries)
    if len(_mem_cache) > 1000:
        oldest = min(_mem_ttl.items(), key=lambda x: x[1])
        _mem_cache.pop(oldest[0], None)
        _mem_ttl.pop(oldest[0], None)


async def cache_delete(key: str):
    if redis_pool:
        try:
            await redis_pool.delete(key)
            return
        except Exception:
            pass

    _mem_cache.pop(key, None)
    _mem_ttl.pop(key, None)


async def get_redis() -> Optional[aioredis.Redis]:
    return redis_pool
