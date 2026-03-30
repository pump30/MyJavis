# Jarvis Voice Assistant

A full-featured AI voice assistant with web UI, powered by Claude and real-time speech processing.

## Features

- **Wake Word Detection** — Say "Hey Jarvis" to activate, works even during AI response to interrupt
- **Speech-to-Text** — Real-time transcription via faster-whisper (supports Chinese & English)
- **Text-to-Speech** — Natural voice replies via edge-tts with auto language detection
- **Browser Microphone** — Click-to-talk from the web UI (no wake word needed)
- **AI Agent with Tools**:
  - Web search (Tavily)
  - Alarm / timer
  - Music playback (YouTube via yt-dlp)
- **Interrupt Support** — Stop button or re-trigger wake word to interrupt anytime
- **Voice Reply Toggle** — Switch between voice + text or text-only responses
- **Markdown Rendering** — AI responses displayed with rich formatting
- **Speech Error Tolerance** — AI auto-corrects common speech recognition mistakes

## Architecture

```
Browser (Web UI)
    │
    ├── WebSocket ──► FastAPI Server (web/server.py)
    │                       │
    │                       ├── Text Input ──► Agent (Claude API)
    │                       │                      │
    │                       │                      ├── web_search (Tavily)
    │                       │                      ├── set_alarm
    │                       │                      └── play_music (yt-dlp)
    │                       │
    │                       └── Audio Input ──► Orchestrator
    │                                               │
    │                                               ├── Wake Word (openwakeword)
    │                                               ├── VAD (energy-based)
    │                                               ├── STT (faster-whisper)
    │                                               └── TTS (edge-tts)
    │
System Microphone ──► Audio Pipeline (same as above)
```

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg (for music playback and audio processing)
- AI proxy running on `localhost:6656` (see `docker-compose.proxy.yml`)

### Install

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### Run

```bash
# Start the AI proxy first
docker compose -f docker-compose.proxy.yml up -d

# Start the assistant
python main.py
```

Open **http://localhost:8088** in your browser.

## Usage

| Action | How |
|---|---|
| Text chat | Type in the input box and press Enter |
| Voice (system mic) | Say "Hey Jarvis", wait for the beep, then speak |
| Voice (browser mic) | Click the microphone button, speak, click again to send |
| Interrupt | Click the red "Stop" button, or say "Hey Jarvis" again |
| Toggle voice reply | Click the speaker icon in the bottom-left corner |

## Configuration

All settings are in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `WEB_PORT` | 8088 | Web server port |
| `MODEL` | claude-sonnet-4-20250514 | LLM model |
| `WHISPER_MODEL_SIZE` | base | STT model (tiny/base/small/medium/large) |
| `WHISPER_DEVICE` | cpu | cpu or cuda |
| `WAKE_WORD_THRESHOLD` | 0.5 | Wake word sensitivity (0-1) |
| `VAD_SILENCE_TIMEOUT_MS` | 1500 | Silence duration to end utterance |
| `TTS_VOICE_ZH` | zh-CN-XiaoxiaoNeural | Chinese TTS voice |
| `TTS_VOICE_EN` | en-US-AriaNeural | English TTS voice |

## Project Structure

```
├── main.py                 # Entry point
├── config.py               # Configuration
├── agent/                  # AI agent (Claude API + tool use)
│   ├── client.py           # Anthropic SDK client with tool loop
│   ├── conversation.py     # Conversation history manager
│   ├── tool_executor.py    # Tool dispatcher
│   └── tools/              # Tool implementations
│       ├── web_search.py   # Tavily web search
│       ├── alarm.py        # Timer / alarm
│       └── music.py        # YouTube music playback
├── audio/                  # Audio I/O
│   ├── microphone.py       # System mic capture
│   ├── browser_audio.py    # Browser mic decoder
│   ├── playback.py         # Audio playback (interruptible)
│   └── vad.py              # Voice activity detection
├── pipeline/               # Orchestration
│   ├── orchestrator.py     # Wake word → VAD → STT → Agent → TTS
│   └── state.py            # State machine (idle/listening/processing/speaking)
├── stt/                    # Speech-to-text (faster-whisper)
├── tts/                    # Text-to-speech (edge-tts)
├── wakeword/               # Wake word detection (openwakeword)
└── web/                    # Web UI
    ├── server.py           # FastAPI + WebSocket
    ├── templates/           # HTML
    └── static/             # CSS + JS
```

## License

MIT
