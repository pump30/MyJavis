"""FastAPI web server with WebSocket support."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from pipeline.state import StateManager, PipelineState

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Jarvis Voice Assistant")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Shared state — set by main.py before starting
state_manager: StateManager = None
agent_handler = None  # async callable(text) -> str
scheduler_manager = None  # SchedulerManager — set by main.py
orchestrator = None  # set by main.py — Orchestrator instance
connected_clients: list[WebSocket] = []


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


async def broadcast(msg: dict):
    """Send a JSON message to all connected WebSocket clients."""
    data = json.dumps(msg, ensure_ascii=False)
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)

    # Send current state
    await ws.send_text(json.dumps({
        "type": "state_change",
        "state": state_manager.state.value if state_manager else "idle",
    }))

    # Send current task list
    if scheduler_manager:
        await ws.send_text(json.dumps({
            "type": "tasks_updated",
            "tasks": scheduler_manager.list_tasks(),
        }, ensure_ascii=False))

    # Subscribe to state changes
    state_queue = state_manager.subscribe() if state_manager else None

    async def forward_state():
        if not state_queue:
            return
        try:
            while True:
                new_state = await state_queue.get()
                await ws.send_text(json.dumps({
                    "type": "state_change",
                    "state": new_state.value,
                }))
        except Exception:
            pass

    state_task = asyncio.create_task(forward_state())
    active_task: asyncio.Task = None  # currently running agent/TTS task

    async def _handle_text(text: str, voice_reply: bool):
        """Process text input in a cancellable task."""
        try:
            response = await agent_handler(text)
            await broadcast({"type": "assistant_message", "text": response})
            if voice_reply:
                from tts.engine import synthesize
                from audio.playback import play_audio_bytes
                if state_manager:
                    await state_manager.set_state(PipelineState.SPEAKING)
                audio_bytes = await synthesize(response)
                if audio_bytes:
                    import base64
                    await broadcast({
                        "type": "audio",
                        "data": base64.b64encode(audio_bytes).decode("ascii"),
                    })
                    await play_audio_bytes(audio_bytes)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await broadcast({"type": "error", "text": str(e)})
        finally:
            if state_manager:
                await state_manager.set_state(PipelineState.IDLE)

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "text_input" and agent_handler:
                text = msg.get("text", "").strip()
                if not text:
                    continue
                voice_reply = msg.get("voice_reply", True)
                await broadcast({"type": "user_message", "text": text})
                if state_manager:
                    await state_manager.set_state(PipelineState.PROCESSING)
                active_task = asyncio.create_task(_handle_text(text, voice_reply))

            elif msg_type == "audio_chunk":
                if orchestrator:
                    orchestrator.feed_browser_audio(msg.get("data", ""))

            elif msg_type == "mic_start":
                if orchestrator:
                    await orchestrator.browser_mic_start()

            elif msg_type == "mic_stop":
                if orchestrator:
                    voice_reply = msg.get("voice_reply", True)
                    await orchestrator.browser_mic_stop(voice_reply=voice_reply)

            elif msg_type == "task_toggle":
                task_id = msg.get("task_id")
                action = msg.get("action")  # "cancel" | "reactivate"
                if scheduler_manager:
                    if action == "cancel":
                        await scheduler_manager.cancel_task(task_id)
                    elif action == "reactivate":
                        result = await scheduler_manager.reactivate_task(task_id)
                        if result:  # error message for expired one-time
                            await ws.send_text(json.dumps({"type": "error", "text": result}))
                    tasks = scheduler_manager.list_tasks()
                    await broadcast({"type": "tasks_updated", "tasks": tasks})

            elif msg_type == "command":
                action = msg.get("action")
                if action == "stop":
                    from audio.playback import interrupt_playback
                    interrupt_playback()
                    # Cancel the running agent/TTS task
                    if active_task and not active_task.done():
                        active_task.cancel()
                        active_task = None
                    if state_manager:
                        await state_manager.set_state(PipelineState.IDLE)

    except WebSocketDisconnect:
        pass
    finally:
        state_task.cancel()
        if state_queue and state_manager:
            state_manager.unsubscribe(state_queue)
        if ws in connected_clients:
            connected_clients.remove(ws)
