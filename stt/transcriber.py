"""Speech-to-text using faster-whisper."""

import numpy as np
import config


class Transcriber:
    """Wraps faster-whisper for speech-to-text."""

    def __init__(self):
        self._model = None

    def load(self):
        """Load the faster-whisper model."""
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            config.WHISPER_MODEL_SIZE,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )

    async def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio (int16, 16kHz) to text.

        Returns the transcribed text.
        """
        import asyncio

        # faster-whisper expects float32 in [-1, 1]
        audio_float = audio.astype(np.float32) / 32768.0

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, self._transcribe_sync, audio_float)
        return text

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        """Synchronous transcription."""
        segments, info = self._model.transcribe(
            audio,
            language=None,  # auto-detect (supports zh and en)
            vad_filter=True,
        )
        parts = [seg.text.strip() for seg in segments]
        return " ".join(parts)
