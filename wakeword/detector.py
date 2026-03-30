"""Wake word detection using openwakeword."""

import numpy as np
import config


class WakeWordDetector:
    """Detects the wake word 'Hey Jarvis' in audio chunks."""

    def __init__(self):
        self._model = None

    def load(self):
        """Load the openwakeword model."""
        from openwakeword.model import Model
        self._model = Model(
            wakeword_models=[config.WAKE_WORD_MODEL],
            inference_framework="onnx",
        )

    def process_chunk(self, chunk: np.ndarray) -> bool:
        """Process an audio chunk (int16, 16kHz) and return True if wake word detected."""
        if self._model is None:
            return False

        # openwakeword expects int16 numpy arrays
        prediction = self._model.predict(chunk)

        # Check all model scores
        for model_name, score in prediction.items():
            if score > config.WAKE_WORD_THRESHOLD:
                self._model.reset()
                return True
        return False

    def reset(self):
        """Reset detector state."""
        if self._model:
            self._model.reset()
