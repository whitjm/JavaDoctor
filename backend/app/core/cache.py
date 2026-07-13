"""缓存层：优先 Redis，未配置时降级为内存缓存。

用于 JWT 黑名单、语义缓存(M7)、限流计数。
"""
from __future__ import annotations

import time

from app.config import settings

_redis_client = None
_redis_failed = False  # 连接失败时置 True，避免每次请求重试超时
_memory_store: dict[str, tuple[str, float | None]] = {}


def _get_redis():
    global _redis_client, _redis_failed
    if _redis_client is not None:
        return _redis_client
    if _redis_failed:  # 之前连过但失败了，不再重试
        return None
    if not settings.redis_url:
        _redis_failed = True
        return None
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return client
    except Exception:
        _redis_failed = True  # 记下失败，后续直接走内存缓存
        return None


def cache_set(key: str, value: str, ttl: int | None = None) -> None:
    client = _get_redis()
    if client:
        client.set(key, value, ex=ttl)
        return
    expire = time.time() + ttl if ttl else None
    _memory_store[key] = (value, expire)


def cache_get(key: str) -> str | None:
    client = _get_redis()
    if client:
        return client.get(key)
    item = _memory_store.get(key)
    if not item:
        return None
    value, expire = item
    if expire and time.time() > expire:
        _memory_store.pop(key, None)
        return None
    return value


def cache_exists(key: str) -> bool:
    return cache_get(key) is not None


def is_redis_available() -> bool:
    return _get_redis() is not None
