"""System microphone capture via sounddevice."""

import asyncio
import numpy as np
import sounddevice as sd

import config


class MicrophoneCapture:
    """Continuously captures audio from the system microphone and puts
    chunks (numpy int16 arrays) into an asyncio queue."""

    def __init__(self):
        self._queue: asyncio.Queue = None
        self._stream: sd.InputStream = None
        self._loop: asyncio.AbstractEventLoop = None
        self._running = False

    async def start(self, queue: asyncio.Queue):
        self._queue = queue
        self._loop = asyncio.get_event_loop()
        self._running = True

        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=config.CHUNK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _safe_put(self, chunk):
        """Put chunk into queue, silently dropping if full."""
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            pass

    def _audio_callback(self, indata: np.ndarray, frames, time_info, status):
        """Called from a PortAudio thread — must not block."""
        if not self._running:
            return
        chunk = indata[:, 0].copy()
        self._loop.call_soon_threadsafe(self._safe_put, chunk)

    async def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
