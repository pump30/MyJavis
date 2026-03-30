# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Jarvis is a real-time AI voice assistant with a web UI. It uses wake word detection ("Hey Jarvis"), speech-to-text (faster-whisper), an AI agent (Claude with tool use), and text-to-speech (edge-tts). The web UI connects via WebSocket to a FastAPI server.

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

The system uses a hybrid async/threaded model. The main `asyncio` thread runs the FastAPI server and agent logic, while a separate thread handles audio processing (wake word, VAD, STT) to avoid blocking.

A state machine in `pipeline/state.py` manages the flow: `IDLE → LISTENING → PROCESSING → SPEAKING`. The agent in `agent/client.py` uses a tool-use loop, with tool definitions in `agent/tools/definitions.py`. Input comes from either the system microphone (full pipeline) or the browser (bypasses wake word). The wake word can interrupt the agent at any time.

## Configuration

All settings are module-level constants in `config.py`. Key settings include `ANTHROPIC_BASE_URL` (points to the local AI proxy) and `MODEL`.

## Key Workflows

### Adding a New Tool
1.  Add the tool schema to `agent/tools/definitions.py`.
2.  Create the implementation in `agent/tools/<name>.py`.
3.  Register the function in `agent/tool_executor.py`.

### Development & PRs
This project uses the Superpowers plugin workflow: **Brainstorm → Plan → Develop (TDD) → Review**.
- Use `git worktree` for feature isolation.
- Self-review changes with `requesting-code-review` before creating a PR.
- Create PRs to `main` using `gh pr create`.
- **Git Proxy**: Use `http://127.0.0.1:7892` for all `git push` and `gh` commands.

## Priority Areas

1.  Add test coverage, starting with `agent/client.py` and `pipeline/orchestrator.py`.
2.  Implement new agent tools.
3.  Improve error handling and the interrupt mechanism.
4.  Achieve feature parity between the browser and system microphone paths.