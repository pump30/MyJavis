# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Jarvis is a real-time AI voice assistant with a web UI. It uses wake word detection ("Hey Jarvis"), speech-to-text (faster-whisper), an AI agent (Claude via Anthropic SDK with tool use), and text-to-speech (edge-tts). The web UI connects via WebSocket to a FastAPI server.

## Running the Project

```bash
# Prerequisites: Python 3.11+, FFmpeg, venv activated
pip install -r requirements.txt

# Start the AI proxy (required — proxies to SAP AI Core hosting Claude)
docker compose -f docker-compose.proxy.yml up -d

# Start the assistant
python main.py
# Web UI at http://localhost:8088
```

There are no tests or linting configured in this project.

## Architecture

### Threading Model

The system uses a hybrid async + threaded architecture:

- **Main thread (asyncio)**: FastAPI server, WebSocket handling, agent API calls, TTS
- **Audio thread** (`_audio_thread_loop`): Wake word detection, VAD, STT transcription — runs synchronously to avoid blocking the event loop
- Communication between threads uses `asyncio.Queue` and `run_coroutine_threadsafe`

### Pipeline State Machine

`pipeline/state.py` defines four states: `IDLE → LISTENING → PROCESSING → SPEAKING`. The `StateManager` broadcasts state changes to all subscribers (WebSocket clients track state for UI updates).

### Voice Pipeline Flow (Orchestrator)

`pipeline/orchestrator.py` coordinates the full flow:
1. **IDLE**: Audio thread runs wake word detection on each 80ms chunk
2. **LISTENING**: VAD accumulates audio with a 1-second grace period, ends on silence timeout (1500ms) or 30s max
3. **PROCESSING**: Audio thread transcribes via faster-whisper, puts text on `_text_queue`; async `_agent_loop` picks it up and calls the Claude agent
4. **SPEAKING**: TTS synthesizes response, plays audio; wake word interrupt is still active during this phase

### Agent Tool-Use Loop

`agent/client.py` implements an agentic loop: sends messages to Claude, executes any tool calls (`web_search`, `set_alarm`, `play_music`), feeds results back, repeats up to 10 iterations until `end_turn`.

- Tool definitions are in `agent/tools/definitions.py` (Anthropic tool use format)
- Tool dispatch is in `agent/tool_executor.py` — a simple name-to-function router
- Conversation history lives in a global `ConversationManager` singleton (in `agent/client.py`)

### Two Input Paths

1. **System microphone**: Wake word → VAD → STT → Agent → TTS (full pipeline via audio thread)
2. **Browser microphone / text input**: WebSocket → server.py → agent directly (bypasses wake word)

Both paths share the same `agent.client.chat()` function and global conversation state.

### Interrupt Mechanism

During PROCESSING or SPEAKING, the audio thread continues checking for wake word. On detection, it cancels the active asyncio task and interrupts audio playback. The web UI also has a stop button that cancels via WebSocket command.

## Configuration

All settings are in `config.py` as module-level constants. Key ones:
- `ANTHROPIC_BASE_URL`: Points to the local AI proxy at `localhost:6656`
- `MODEL`: Claude model identifier (prefixed with `anthropic:` for the proxy)
- `WHISPER_MODEL_SIZE` / `WHISPER_DEVICE`: STT model selection (cpu/cuda)
- `WAKE_WORD_THRESHOLD` / `VAD_SILENCE_TIMEOUT_MS`: Tuning for voice detection

## Adding a New Tool

1. Add the tool schema to `agent/tools/definitions.py`
2. Create the implementation in `agent/tools/<name>.py`
3. Register the dispatch in `agent/tool_executor.py`

## Development Workflow (Superpowers)

This project uses the Superpowers plugin. Every feature/bugfix must follow the complete flow:

1. **Brainstorming** — align on design before writing any code
2. **Writing plans** — break work into small tasks (2-5 min each), with exact file paths and verification steps
3. **Subagent-driven development** — execute tasks with two-stage auto-review (spec compliance + code quality)
4. **TDD** — RED-GREEN-REFACTOR for all new code

Use git worktrees for feature isolation. Use `dispatching-parallel-agents` for independent tasks (e.g. adding multiple tools, UI + backend changes in parallel).

Do not skip steps even for seemingly simple changes.

### PR Workflow

Each feature/bugfix must follow this delivery flow:
1. Create a feature branch (use git worktree for isolation)
2. Implement with the Superpowers flow above
3. Run `requesting-code-review` to self-review against the plan
4. Fix all issues found in review
5. Verify all tests pass
6. Push branch and create a PR to `main` via `gh pr create`
7. Wait for the user to review and merge — do NOT merge PRs yourself

Use proxy for all git push/PR operations: `http://127.0.0.1:7892`

## Priority Areas

1. Add test coverage, starting from `agent/client.py` (tool-use loop) and `pipeline/orchestrator.py`
2. New agent tools (each follows the 3-step pattern in "Adding a New Tool")
3. Error handling and interrupt mechanism robustness
4. Browser mic path parity with system mic path

## Network

Git proxy for GitHub access: `http://127.0.0.1:7892`
