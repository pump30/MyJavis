"""Core pipeline orchestrator: wake word → listen → transcribe → agent → TTS.

The audio processing (wake word detection, VAD) runs in a dedicated thread
to avoid blocking the asyncio event loop used by FastAPI and the AI agent.
"""

import asyncio
from asyncio import QueueEmpty
import threading
import time
import numpy as np

import config
from pipeline.state import StateManager, PipelineState
from audio.microphone import MicrophoneCapture
from audio.vad import VAD
from audio.browser_audio import decode_browser_chunk
from wakeword.detector import WakeWordDetector
from stt.transcriber import Transcriber
from tts.engine import synthesize
from audio.playback import play_audio_bytes
from agent.client import chat


class Orchestrator:
    def __init__(self, state_manager: StateManager, broadcast_fn):
        self.state = state_manager
        self.broadcast = broadcast_fn

        self._mic = MicrophoneCapture()
        self._vad = VAD()
        self._wakeword = WakeWordDetector()
        self._transcriber = Transcriber()

        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._browser_audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._use_browser_mic = False
        self._browser_recording = False  # True when browser mic button is active
        self._browser_audio_buffer: list = []  # accumulate chunks during browser recording
        self._running = False
        self._loop: asyncio.AbstractEventLoop = None
        self._active_task: asyncio.Task = None  # current agent task (cancellable)

        # Thread-safe queue for passing transcribed text to async handler
        self._text_queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    async def load_models(self):
        """Load all ML models (wake word, VAD, STT). Call once at startup."""
        loop = asyncio.get_event_loop()
        print("[orchestrator] Loading wake word model...")
        await loop.run_in_executor(None, self._wakeword.load)
        print("[orchestrator] Loading VAD model...")
        await loop.run_in_executor(None, self._vad.load)
        print("[orchestrator] Loading STT model...")
        await loop.run_in_executor(None, self._transcriber.load)
        print("[orchestrator] All models loaded.")

    async def start(self):
        """Start the audio capture and pipeline loops."""
        self._running = True
        self._loop = asyncio.get_event_loop()
        await self._mic.start(self._audio_queue)

        # Audio processing thread — handles wake word + VAD + STT
        self._audio_thread = threading.Thread(
            target=self._audio_thread_loop, daemon=True, name="audio-pipeline"
        )
        self._audio_thread.start()

        # Async task — handles agent + TTS (needs event loop)
        asyncio.create_task(self._agent_loop())

    async def stop(self):
        self._running = False
        await self._mic.stop()

    def feed_browser_audio(self, b64_data: str):
        """Feed a base64-encoded audio chunk from the browser."""
        try:
            chunk = decode_browser_chunk(b64_data)
            if self._browser_recording:
                self._browser_audio_buffer.append(chunk)
            else:
                self._browser_audio_queue.put_nowait(chunk)
                self._use_browser_mic = True
        except asyncio.QueueFull:
            pass

    async def browser_mic_start(self):
        """Called when user clicks the mic button — skip wake word, start recording."""
        self._browser_recording = True
        self._browser_audio_buffer.clear()
        await self.state.set_state(PipelineState.LISTENING)

    async def browser_mic_stop(self, voice_reply: bool = True):
        """Called when user clicks mic button again — transcribe and send to agent."""
        self._browser_recording = False
        if not self._browser_audio_buffer:
            await self.state.set_state(PipelineState.IDLE)
            return

        await self.state.set_state(PipelineState.PROCESSING)

        # Transcribe accumulated audio
        full_audio = np.concatenate(self._browser_audio_buffer)
        self._browser_audio_buffer.clear()
        audio_float = full_audio.astype(np.float32) / 32768.0

        loop = asyncio.get_event_loop()
        segments, _ = await loop.run_in_executor(
            None, lambda: self._transcriber._model.transcribe(audio_float, language=None, vad_filter=True)
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(f"[browser-mic] Transcribed: {text}")

        if not text:
            await self.state.set_state(PipelineState.IDLE)
            return

        await self.broadcast({"type": "user_message", "text": text})

        # Send to agent
        try:
            response = await chat(text)
            print(f"[browser-mic] Agent: {response[:100]}")
            await self.broadcast({"type": "assistant_message", "text": response})

            if voice_reply:
                await self.state.set_state(PipelineState.SPEAKING)
                audio_bytes = await synthesize(response)
                await play_audio_bytes(audio_bytes)
        except Exception as e:
            print(f"[browser-mic] Error: {e}")
            await self.broadcast({"type": "error", "text": str(e)})
        finally:
            await self.state.set_state(PipelineState.IDLE)

    def _get_audio_chunk_sync(self) -> np.ndarray | None:
        """Get audio chunk synchronously (for the audio thread)."""
        # Check browser audio first
        try:
            if self._use_browser_mic and not self._browser_audio_queue.empty():
                return self._browser_audio_queue.get_nowait()
        except QueueEmpty:
            pass

        try:
            return self._audio_queue.get_nowait()
        except QueueEmpty:
            return None

    def _set_state_sync(self, state: PipelineState):
        """Set state from the audio thread (thread-safe)."""
        asyncio.run_coroutine_threadsafe(
            self.state.set_state(state), self._loop
        )

    def _broadcast_sync(self, msg: dict):
        """Broadcast from the audio thread (thread-safe)."""
        asyncio.run_coroutine_threadsafe(
            self.broadcast(msg), self._loop
        )

    def _audio_thread_loop(self):
        """Run in a dedicated thread: wake word detection → VAD → STT."""
        print("[audio-thread] Started.")
        while self._running:
            try:
                # Skip when browser mic is handling the session
                if self._browser_recording:
                    time.sleep(0.1)
                    continue
                if self.state.state == PipelineState.IDLE:
                    self._idle_phase_sync()
                elif self.state.state == PipelineState.LISTENING:
                    self._listening_phase_sync()
                else:
                    # PROCESSING or SPEAKING — still listen for wake word to interrupt
                    self._interrupt_detect_sync()
            except Exception as e:
                import traceback
                print(f"[audio-thread] Error: {e}")
                traceback.print_exc()
                self._set_state_sync(PipelineState.IDLE)
                time.sleep(0.5)

    def _interrupt_detect_sync(self):
        """During PROCESSING/SPEAKING, keep listening for wake word to interrupt."""
        chunk = self._get_audio_chunk_sync()
        if chunk is None:
            time.sleep(0.01)
            return

        if self._wakeword.process_chunk(chunk):
            print("[audio-thread] Wake word interrupt detected!")
            # Interrupt playback
            from audio.playback import interrupt_playback
            interrupt_playback()
            # Cancel active task if any
            if self._active_task and not self._active_task.done():
                self._active_task.cancel()
                self._active_task = None
            # Transition to LISTENING
            self._set_state_sync(PipelineState.LISTENING)
            self._broadcast_sync({"type": "wake_detected"})
            self._vad.reset()

    def _idle_phase_sync(self):
        """Wait for wake word — runs in audio thread."""
        chunk = self._get_audio_chunk_sync()
        if chunk is None:
            time.sleep(0.01)
            return

        if self._wakeword.process_chunk(chunk):
            print("[audio-thread] Wake word detected!")
            self._set_state_sync(PipelineState.LISTENING)
            self._broadcast_sync({"type": "wake_detected"})
            self._vad.reset()

    def _listening_phase_sync(self):
        """Accumulate audio until VAD detects end of speech — runs in audio thread."""
        audio_buffer = []
        self._vad.reset()

        # Grace period: ignore VAD for the first 1 second after wake word
        # so the user has time to start speaking
        min_listen_samples = config.SAMPLE_RATE * 1  # 1 second
        total_samples = 0

        while self._running and self.state.state == PipelineState.LISTENING:
            chunk = self._get_audio_chunk_sync()
            if chunk is None:
                time.sleep(0.01)
                continue

            audio_buffer.append(chunk)
            total_samples += len(chunk)
            vad_result = self._vad.process_chunk(chunk)

            # Only allow ending after the grace period
            if vad_result == "end" and total_samples > min_listen_samples:
                break

            # Safety: max 30 seconds
            if total_samples > config.SAMPLE_RATE * 30:
                break

        if not audio_buffer:
            self._set_state_sync(PipelineState.IDLE)
            return

        # Transcribe (CPU-bound, fine in this thread)
        full_audio = np.concatenate(audio_buffer)
        self._set_state_sync(PipelineState.PROCESSING)

        audio_float = full_audio.astype(np.float32) / 32768.0
        segments, _ = self._transcriber._model.transcribe(
            audio_float, language=None, vad_filter=True
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(f"[audio-thread] Transcribed: {text}")

        if not text:
            self._set_state_sync(PipelineState.IDLE)
            return

        self._broadcast_sync({"type": "user_message", "text": text})

        # Pass text to async agent loop
        try:
            self._loop.call_soon_threadsafe(
                self._text_queue.put_nowait, text
            )
        except asyncio.QueueFull:
            self._set_state_sync(PipelineState.IDLE)

    async def _agent_loop(self):
        """Async loop: picks up transcribed text, calls agent, does TTS."""
        while self._running:
            try:
                text = await asyncio.wait_for(self._text_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            task = asyncio.current_task()
            self._active_task = task
            try:
                response = await chat(text)
                print(f"[orchestrator] Agent: {response[:100]}")
                await self.broadcast({"type": "assistant_message", "text": response})

                # TTS
                await self.state.set_state(PipelineState.SPEAKING)
                audio_bytes = await synthesize(response)
                if audio_bytes:
                    await play_audio_bytes(audio_bytes)
            except asyncio.CancelledError:
                print("[orchestrator] Agent/TTS interrupted by wake word.")
            except Exception as e:
                print(f"[orchestrator] Agent/TTS error: {e}")
                await self.broadcast({"type": "error", "text": str(e)})
            finally:
                self._active_task = None
                if self.state.state != PipelineState.LISTENING:
                    await self.state.set_state(PipelineState.IDLE)
