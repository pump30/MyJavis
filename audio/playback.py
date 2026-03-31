"""Audio playback via sounddevice (optional).

When sounddevice is not available (e.g. Docker), playback is a no-op.
The caller is responsible for sending audio to the browser via broadcast.
"""

import io
import asyncio
import threading

# Global interrupt flag — set to stop current playback
_interrupt = threading.Event()

# Whether local audio playback is available
_has_sounddevice = False
try:
    import sounddevice as sd
    _has_sounddevice = True
except (ImportError, OSError):
    sd = None


def interrupt_playback():
    """Signal the current playback to stop immediately."""
    _interrupt.set()
    if _has_sounddevice:
        sd.stop()


async def play_audio_bytes(audio_bytes: bytes, sample_rate: int = 24000):
    """Play raw audio bytes (MP3) using sounddevice. Can be interrupted.

    Returns silently if sounddevice is not available.
    """
    if not _has_sounddevice:
        return
    _interrupt.clear()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _play_sync, audio_bytes, sample_rate)


def _play_sync(audio_bytes: bytes, sample_rate: int):
    """Synchronous audio playback. Tries to decode MP3 via mini decoder."""
    import numpy as np
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        samples = np.array(seg.get_array_of_samples(), dtype=np.int16)
        if seg.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1).astype(np.int16)
        sd.play(samples, samplerate=seg.frame_rate)
        # Poll so we can respond to interrupt
        while sd.get_stream().active:
            if _interrupt.is_set():
                sd.stop()
                return
            _interrupt.wait(timeout=0.05)
    except ImportError:
        import tempfile
        import subprocess
        import shutil
        if shutil.which("ffplay"):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_bytes)
                f.flush()
                proc = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", f.name],
                )
                while proc.poll() is None:
                    if _interrupt.is_set():
                        proc.terminate()
                        return
                    _interrupt.wait(timeout=0.05)
