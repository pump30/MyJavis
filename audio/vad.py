"""Voice Activity Detection using openwakeword's built-in silero VAD (ONNX)."""

import numpy as np
import config


class VAD:
    """Lightweight VAD using energy-based detection.

    Uses a simple energy threshold approach to avoid heavy torch dependency.
    Works well enough for detecting speech end after wake word triggers.
    """

    def __init__(self):
        self._silence_samples = 0
        self._speech_detected = False
        self._silence_limit = int(
            config.SAMPLE_RATE * config.VAD_SILENCE_TIMEOUT_MS / 1000
        )
        self._energy_threshold = 300  # int16 RMS threshold

    def load(self):
        """No-op: energy-based VAD needs no model loading."""
        pass

    def reset(self):
        """Reset VAD state for a new utterance."""
        self._silence_samples = 0
        self._speech_detected = False

    def process_chunk(self, chunk: np.ndarray) -> str:
        """Process an audio chunk (int16) and return state.

        Returns:
            "speech"  — speech is ongoing
            "silence" — brief silence but speech was detected before
            "end"     — speech ended (silence exceeded threshold)
            "none"    — no speech detected yet
        """
        rms = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
        is_speech = rms > self._energy_threshold

        if is_speech:
            self._speech_detected = True
            self._silence_samples = 0
            return "speech"
        elif self._speech_detected:
            self._silence_samples += len(chunk)
            if self._silence_samples >= self._silence_limit:
                return "end"
            return "silence"
        else:
            return "none"
