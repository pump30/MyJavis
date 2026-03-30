"""Shared state machine for the voice assistant pipeline."""

import asyncio
from enum import Enum


class PipelineState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class StateManager:
    def __init__(self):
        self._state = PipelineState.IDLE
        self._listeners: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    @property
    def state(self) -> PipelineState:
        return self._state

    async def set_state(self, new_state: PipelineState):
        async with self._lock:
            if self._state != new_state:
                self._state = new_state
                for q in self._listeners:
                    try:
                        q.put_nowait(new_state)
                    except asyncio.QueueFull:
                        pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._listeners:
            self._listeners.remove(q)
