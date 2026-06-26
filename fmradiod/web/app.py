"""Starlette app — retro UI, audio stream, control API, live SSE, album art.

The daemon is the single source of truth: control endpoints call the tuner; the
UI reads `/api/state` and subscribes to `/api/events` so it mirrors daemon state
(including preset changes that later come from physical buttons).
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

# build_state lives in a web-agnostic module so the TFT renderer can share it;
# re-exported here so existing imports (and tests) keep working.
from fmradiod.viewstate import build_state


def format_sse(event) -> str:
    return f"data: {json.dumps(event)}\n\n"


def create_app(tuner, fanout, metadata, bus, static_dir: str, renderer=None,
               button_input=None) -> Starlette:
    async def index(request):
        return FileResponse(os.path.join(static_dir, "index.html"))

    async def stream(request):
        return StreamingResponse(
            fanout.stream(), media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache"},
        )

    async def state(request):
        return JSONResponse(build_state(tuner, metadata))

    async def tune(request):
        index = request.path_params["index"]
        if not (0 <= index < len(tuner.ring)):
            return JSONResponse({"error": "preset index out of range"}, status_code=404)
        await tuner.tune(index)
        return JSONResponse(build_state(tuner, metadata))

    async def next_preset(request):
        await tuner.next()
        return JSONResponse(build_state(tuner, metadata))

    async def prev_preset(request):
        await tuner.prev()
        return JSONResponse(build_state(tuner, metadata))

    async def events(request):
        async def gen():
            # Every event re-pushes the full state so the browser has one code
            # path; bus events are just "something changed" triggers.
            yield format_sse(build_state(tuner, metadata))
            async for _ in bus.events():
                yield format_sse(build_state(tuner, metadata))

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def art(request):
        path = metadata.art_path
        if not path or not os.path.exists(path):
            return Response(status_code=404)
        return FileResponse(path)

    @asynccontextmanager
    async def lifespan(app):
        await tuner.start()
        # Start peripherals after the tuner so they reflect the tuned station;
        # tear them down before the tuner so their hardware releases cleanly
        # (reverse order of startup).
        if renderer is not None:
            renderer.start()
        if button_input is not None:
            button_input.start()
        try:
            yield
        finally:
            if button_input is not None:
                await button_input.stop()
            if renderer is not None:
                await renderer.stop()
            await tuner.stop()

    routes = [
        Route("/", index),
        Route("/stream.mp3", stream),
        Route("/api/state", state),
        Route("/api/tune/{index:int}", tune, methods=["POST"]),
        Route("/api/next", next_preset, methods=["POST"]),
        Route("/api/prev", prev_preset, methods=["POST"]),
        Route("/api/events", events),
        Route("/art/current", art),
        Mount("/static", app=StaticFiles(directory=static_dir), name="static"),
    ]
    return Starlette(routes=routes, lifespan=lifespan)
