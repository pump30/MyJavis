"""System microphone capture via sounddevice.

sounddevice is optional — when unavailable (e.g. Docker without audio
devices), the capture simply does nothing and ``available`` stays False.
"""

import asyncio
import numpy as np

import config


class MicrophoneCapture:
    """Continuously captures audio from the system microphone and puts
    chunks (numpy int16 arrays) into an asyncio queue."""

    def __init__(self):
        self._queue: asyncio.Queue = None
        self._stream = None
        self._loop: asyncio.AbstractEventLoop = None
        self._running = False
        self.available = False

    async def start(self, queue: asyncio.Queue):
        self._queue = queue
        self._loop = asyncio.get_event_loop()
        self._running = True

        try:
            import sounddevice as sd
        except (ImportError, OSError) as e:
            print(f"[mic] sounddevice not available: {e}")
            print("[mic] System microphone disabled — use browser mic instead.")
            return

        try:
            self._stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
                dtype="int16",
                blocksize=config.CHUNK_SIZE,
                callback=self._audio_callback,
            )
            self._stream.start()
            self.available = True
        except Exception as e:
            print(f"[mic] Failed to open audio device: {e}")
            print("[mic] System microphone disabled — use browser mic instead.")

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
