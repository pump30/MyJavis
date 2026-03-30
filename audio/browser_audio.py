"""Decode audio chunks received from the browser via WebSocket."""

import base64
import numpy as np


def decode_browser_chunk(b64_data: str) -> np.ndarray:
    """Decode a base64-encoded int16 PCM chunk from the browser.

    Returns a numpy int16 array.
    """
    raw = base64.b64decode(b64_data)
    return np.frombuffer(raw, dtype=np.int16)
