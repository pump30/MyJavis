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

Tests: `python -m pytest tests/ -v` (activate venv first: `source venv/Scripts/activate`).

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

每次功能开发必须遵循以下完整流程：

1. **Worktree 隔离开发**：用 `git worktree` 创建独立工作目录进行开发。
2. **自审代码**：开发完成后用 `requesting-code-review` 自审。
3. **创建 PR**：用 `gh pr create` 向 `main` 提交 PR。如有冲突，先 rebase 或 merge 解决冲突后再继续。
4. **Docker 部署测试**：确保 proxy 已启动（`docker compose -f docker-compose.proxy.yml up -d`），然后构建并启动应用。**必须使用非默认端口**，避免与主分支或其他分支的容器冲突：
   ```bash
   # 构建（需要代理参数）
   docker compose build --build-arg http_proxy=http://host.docker.internal:7892 --build-arg https_proxy=http://host.docker.internal:7892
   # 启动 — 每个分支必须用不同端口（不要用 8088，那是主分支的）
   PORT=8090 docker compose up -d
   ```
   > **重要**：每次开分支测试时，先用 `docker ps` 或 `curl` 检查目标端口是否已被占用，选择一个空闲端口。
5. **截图贴到 PR**：测试通过后，截图测试结果并用 `gh pr comment` 附到 PR 上作为验证证据。

- **Git Proxy**: Use `http://127.0.0.1:7892` for all `git push` and `gh` commands.
- **Docker Build Proxy**: Use `--build-arg http_proxy=http://host.docker.internal:7890` for `docker compose build`.
- **Resolve conflicts before merging**: After creating a PR, always `git fetch origin main && git rebase origin/main` to resolve any conflicts, then force-push the branch. PRs must be conflict-free before requesting merge.

### Smoke Testing & PR Screenshots
Every PR that changes UI or user-facing behavior **must** include a smoke test:
1. Start the app: `source venv/Scripts/activate && python main.py`
2. Open `http://localhost:8088` in Playwright browser.
3. Walk through the relevant test scenarios (tab switching, task creation, etc.).
4. **Take screenshots** of each key step using `browser_take_screenshot` and attach them to the PR body as evidence.
5. Never skip smoke tests — they catch integration bugs that unit tests miss.

### Docker Deployment After Testing
Smoke test 完成后，必须将应用部署到 Docker 容器中验证：
1. 构建镜像：`docker compose build`（需要代理参数，见上方 Docker Build Proxy）
2. 启动容器：**必须用不同端口**，先检查端口占用再启动：`PORT=<空闲端口> docker compose up -d`
3. 用 Playwright 打开对应端口的 URL（如 `http://localhost:8090`）再次验证核心功能。
4. **截图**容器内运行的结果，附到 PR body 中。
5. 验证通过后停止容器：`docker compose down`

## Priority Areas

1.  Add test coverage, starting with `agent/client.py` and `pipeline/orchestrator.py`.
2.  Implement new agent tools.
3.  Improve error handling and the interrupt mechanism.
4.  Achieve feature parity between the browser and system microphone paths.