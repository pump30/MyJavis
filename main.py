"""Jarvis Voice Assistant — entry point."""

import sys

# Fix Windows GBK console encoding — must run before any print() call
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import config
from pipeline.state import StateManager
from pipeline.orchestrator import Orchestrator
from agent.tools.alarm import set_broadcast
import web.server as web_module
from agent.client import chat

_orchestrator = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    global _orchestrator
    sm = StateManager()
    web_module.state_manager = sm

    async def agent_handler(text: str) -> str:
        return await chat(text)

    web_module.agent_handler = agent_handler
    set_broadcast(web_module.broadcast)

    _orchestrator = Orchestrator(sm, web_module.broadcast)
    web_module.orchestrator = _orchestrator

    print("=" * 50)
    print("  Jarvis Voice Assistant")
    print("=" * 50)

    try:
        await _orchestrator.load_models()
        await _orchestrator.start()
        print("[main] Voice pipeline started.")
    except Exception as e:
        print(f"[main] Voice pipeline unavailable: {e}")
        print("[main] Running in text-only mode (Web UI still works).")

    print(f"[main] Web UI: http://localhost:{config.WEB_PORT}")
    print("=" * 50)

    yield

    if _orchestrator:
        await _orchestrator.stop()


# Reconfigure the app with lifespan
web_module.app.router.lifespan_context = lifespan
app = web_module.app


def main():
    uvicorn.run(
        "main:app",
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
