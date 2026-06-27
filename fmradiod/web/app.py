"""Starlette app — retro UI, audio stream, control API, live SSE, album art.

The daemon is the single source of truth: control endpoints call the tuner; the
UI reads `/api/state` and subscribes to `/api/events` so it mirrors daemon state
(including preset changes that later come from physical buttons).
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

# build_state lives in a web-agnostic module so the TFT renderer can share it;
# re-exported here so existing imports (and tests) keep working.
from fmradiod.viewstate import build_state

log = logging.getLogger("fmradiod.bluetooth")


def format_sse(event) -> str:
    return f"data: {json.dumps(event)}\n\n"


def create_app(tuner, fanout, metadata, bus, static_dir: str, renderer=None,
               button_input=None, bluetooth=None) -> Starlette:
    def _state() -> dict:
        return build_state(tuner, metadata, bluetooth)

    async def index(request):
        return FileResponse(os.path.join(static_dir, "index.html"))

    async def stream(request):
        return StreamingResponse(
            fanout.stream(), media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache"},
        )

    async def state(request):
        return JSONResponse(_state())

    async def tune(request):
        index = request.path_params["index"]
        if not (0 <= index < len(tuner.ring)):
            return JSONResponse({"error": "preset index out of range"}, status_code=404)
        await tuner.tune(index)
        return JSONResponse(_state())

    async def next_preset(request):
        await tuner.next()
        return JSONResponse(_state())

    async def prev_preset(request):
        await tuner.prev()
        return JSONResponse(_state())

    async def set_output(request):
        mode = request.path_params["mode"]
        try:
            await tuner.set_output(mode)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        bus.publish({"type": "output"})
        return JSONResponse(_state())

    # ----- Bluetooth control -----
    def _require_bt():
        return bluetooth is not None

    async def bt_scan(request):
        if not _require_bt():
            return JSONResponse({"error": "bluetooth unavailable"}, status_code=409)
        on = request.path_params["state"] == "on"
        await (bluetooth.start_discovery() if on else bluetooth.stop_discovery())
        bus.publish({"type": "bluetooth"})
        return JSONResponse(_state())

    async def bt_action(request):
        if not _require_bt():
            return JSONResponse({"error": "bluetooth unavailable"}, status_code=409)
        action = request.path_params["action"]
        mac = request.path_params["mac"]
        if action not in ("pair", "connect", "disconnect", "forget"):
            return JSONResponse({"error": "unknown action"}, status_code=404)
        try:
            await getattr(bluetooth, action)(mac)
        except Exception as exc:
            return JSONResponse({"error": f"{action} failed: {exc}"}, status_code=502)
        # Selecting a speaker routes audio to it; dropping it returns to the web.
        if action == "connect":
            tuner.set_bt_sink(mac)
            tuner.state.save_device(mac)
            await tuner.set_output("bluetooth")
        elif action in ("disconnect", "forget"):
            if tuner.output == "bluetooth":
                await tuner.set_output("web")
            tuner.set_bt_sink(None)
        bus.publish({"type": "bluetooth"})
        return JSONResponse(_state())

    async def events(request):
        async def gen():
            # Every event re-pushes the full state so the browser has one code
            # path; bus events are just "something changed" triggers.
            yield format_sse(_state())
            async for _ in bus.events():
                yield format_sse(_state())

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def art(request):
        path = metadata.art_path
        if not path or not os.path.exists(path):
            return Response(status_code=404)
        return FileResponse(path)

    async def _start_bluetooth():
        """Power on, register the agent, and restore the last speaker + output —
        fail-soft: any failure logs and leaves the daemon on the web output."""
        bluetooth.set_on_change(lambda: bus.publish({"type": "bluetooth"}))
        try:
            await bluetooth.start()
        except Exception:
            log.warning("bluetooth enabled but failed to start; web output only", exc_info=True)
            return
        last = tuner.state.load_device()
        if last and tuner.state.load_output("web") == "bluetooth":
            try:
                await bluetooth.connect(last)
                tuner.set_bt_sink(last)
                await tuner.set_output("bluetooth")
            except Exception:
                log.warning("could not auto-reconnect %s; staying on web", last, exc_info=True)

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
        if bluetooth is not None:
            await _start_bluetooth()
        try:
            yield
        finally:
            if bluetooth is not None:
                try:
                    await bluetooth.stop()
                except Exception:
                    log.warning("bluetooth stop failed", exc_info=True)
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
        Route("/api/output/{mode:str}", set_output, methods=["POST"]),
        Route("/api/bt/scan/{state:str}", bt_scan, methods=["POST"]),
        Route("/api/bt/{action:str}/{mac:str}", bt_action, methods=["POST"]),
        Route("/api/events", events),
        Route("/art/current", art),
        Mount("/static", app=StaticFiles(directory=static_dir), name="static"),
    ]
    return Starlette(routes=routes, lifespan=lifespan)
