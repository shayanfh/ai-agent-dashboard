import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.database import engine

ResultT = TypeVar("ResultT")


def run_async(factory: Callable[[], Awaitable[ResultT]]) -> ResultT:
    """Run one async Celery task and close its loop-bound SQLAlchemy pool."""

    async def runner() -> ResultT:
        try:
            return await factory()
        finally:
            # Celery invokes the synchronous task function repeatedly in the same worker
            # process. asyncio.run() creates a new event loop each time, so pooled asyncpg
            # connections must not survive into the next invocation.
            await engine.dispose()

    return asyncio.run(runner())
