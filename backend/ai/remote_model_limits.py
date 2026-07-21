"""Process-local admission control for outbound model requests."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import threading
from typing import AsyncIterator
from weakref import WeakKeyDictionary

from backend.config import (
    REMOTE_MODEL_MAX_CONCURRENCY,
    REMOTE_MODEL_MAX_QUEUE,
    REMOTE_MODEL_QUEUE_TIMEOUT_SECONDS,
)


class RemoteModelCapacityError(RuntimeError):
    """The remote model queue is full or took too long to admit a request."""


@dataclass(slots=True)
class _LoopState:
    condition: asyncio.Condition
    active: int = 0
    waiting: int = 0


class RemoteModelConcurrencyLimiter:
    """Bound concurrent model calls and queue growth within each event loop."""

    def __init__(
        self,
        *,
        max_concurrency: int,
        max_queue: int,
        queue_timeout_seconds: float,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if max_queue < 0:
            raise ValueError("max_queue cannot be negative")
        if queue_timeout_seconds <= 0:
            raise ValueError("queue_timeout_seconds must be positive")
        self.max_concurrency = int(max_concurrency)
        self.max_queue = int(max_queue)
        self.queue_timeout_seconds = float(queue_timeout_seconds)
        self._states: WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopState] = (
            WeakKeyDictionary()
        )
        self._states_lock = threading.Lock()

    def _state(self) -> _LoopState:
        loop = asyncio.get_running_loop()
        with self._states_lock:
            state = self._states.get(loop)
            if state is None:
                state = _LoopState(asyncio.Condition())
                self._states[loop] = state
            return state

    async def _acquire(self, state: _LoopState) -> None:
        async with state.condition:
            if state.active < self.max_concurrency and state.waiting == 0:
                state.active += 1
                return
            if state.waiting >= self.max_queue:
                raise RemoteModelCapacityError("Remote model queue is full")
            state.waiting += 1
            acquired = False
            try:
                async with asyncio.timeout(self.queue_timeout_seconds):
                    await state.condition.wait_for(
                        lambda: state.active < self.max_concurrency
                    )
                state.active += 1
                acquired = True
            except TimeoutError as exc:
                raise RemoteModelCapacityError(
                    "Timed out waiting for remote model capacity"
                ) from exc
            finally:
                state.waiting -= 1
                if (
                    not acquired
                    and state.waiting
                    and state.active < self.max_concurrency
                ):
                    state.condition.notify(1)

    @staticmethod
    async def _release(state: _LoopState) -> None:
        async with state.condition:
            if state.active < 1:
                raise RuntimeError("Remote model limiter released without a slot")
            state.active -= 1
            state.condition.notify(1)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Reserve one outbound model slot for the duration of a request."""
        state = self._state()
        await self._acquire(state)
        try:
            yield
        finally:
            await self._release(state)


REMOTE_MODEL_LIMITER = RemoteModelConcurrencyLimiter(
    max_concurrency=REMOTE_MODEL_MAX_CONCURRENCY,
    max_queue=REMOTE_MODEL_MAX_QUEUE,
    queue_timeout_seconds=REMOTE_MODEL_QUEUE_TIMEOUT_SECONDS,
)
