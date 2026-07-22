import asyncio
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as redis

from src.config import settings

_LIMIT = 16
_KEY = "product-media:image-generation:inflight"
_ACQUIRE = """
local n = redis.call('GET', KEYS[1]) or '0'
if tonumber(n) < tonumber(ARGV[1]) then
  redis.call('INCR', KEYS[1])
  redis.call('EXPIRE', KEYS[1], ARGV[2])
  return 1
end
return 0
"""


@asynccontextmanager
async def image_generation_slot():
    """Cross-worker image limiter with a lease expiry for crashed workers."""
    client = redis.from_url(settings.celery_broker_url, decode_responses=True)
    try:
        while not await client.eval(_ACQUIRE, 1, _KEY, _LIMIT, 900):
            await asyncio.sleep(0.25)
        try:
            yield
        finally:
            await client.decr(_KEY)
    finally:
        await client.aclose()
