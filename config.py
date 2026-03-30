"""Voice Assistant configuration."""

import os

# ---------------------------------------------------------------------------
# AI Proxy
# ---------------------------------------------------------------------------
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "http://localhost:6656")
ANTHROPIC_API_KEY = "placeholder"
MODEL = "anthropic:claude-sonnet-4-20250514"
MAX_TOKENS = 4096
SYSTEM_PROMPT = (
    "You are Jarvis, a helpful voice assistant. "
    "You can search the web, schedule tasks (reminders, actions, recurring jobs), "
    "and play music. "
    "Keep responses concise and conversational — they will be spoken aloud. "
    "Respond in the same language the user speaks (Chinese or English). "
    "The user is located in Shanghai, China. "
    "The user input comes from speech recognition which may contain errors. "
    "Infer the intended meaning from context — for example 'cloud code' likely means 'Claude Code', "
    "'check GPT' might mean 'ChatGPT', etc. Do not ask for clarification on obvious misrecognitions."
)

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION_MS = 80  # openwakeword expects 80ms frames
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # 1280 samples

# ---------------------------------------------------------------------------
# Wake Word
# ---------------------------------------------------------------------------
WAKE_WORD_MODEL = "hey_jarvis"  # built-in openwakeword model
WAKE_WORD_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# VAD
# ---------------------------------------------------------------------------
VAD_SILENCE_TIMEOUT_MS = 1500  # silence duration to end utterance
VAD_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# STT (faster-whisper)
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZE = "base"
WHISPER_DEVICE = "cpu"        # "cpu" or "cuda"
WHISPER_COMPUTE_TYPE = "int8"  # "int8" for CPU, "float16" for CUDA

# ---------------------------------------------------------------------------
# TTS (edge-tts)
# ---------------------------------------------------------------------------
TTS_VOICE_ZH = "zh-CN-XiaoxiaoNeural"
TTS_VOICE_EN = "en-US-AriaNeural"
TTS_FALLBACK_OFFLINE = True

# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------
WEB_HOST = "0.0.0.0"
WEB_PORT = 8088

# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------
MUSIC_LOCAL_DIR = None  # set to a path to enable local music search

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
MEMORY_DIR = "data/memory"
