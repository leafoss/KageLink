from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pc_agent.chat_channels import (
    ChatChannelParser,
    drop_replayed_prefix,
    find_new_text,
    unfinished_ic_suffix,
)
from pc_agent.chat_reader import ChatReader
from pc_agent.chat_sender import ChatSender
from pc_agent.config import RESOURCE_DIR, load_config, update_input_preference
from pc_agent.history import HistoryStore
from pc_agent.game_protocol import parse_control_message, normalize_view_mode
from pc_agent.game_runtime import GameRuntime
from pc_agent.runtime import ConnectionManager, RuntimeStatus
from pc_agent.security import TokenSecurity
from pc_agent.windows import find_game_window, input_candidates, is_game_window_foreground, window_scan_snapshot


APP_VERSION = "3.3.0"

config = load_config()
security = TokenSecurity(config.access_token)
history = HistoryStore(config.database_path)
reader = ChatReader(config.game_title, config.chat_class)
sender = ChatSender(
    game_title=config.game_title,
    input_class=config.input_class,
    preferences=dict(config.input_controls),
    min_interval_seconds=config.min_send_interval_seconds,
)
manager = ConnectionManager()
runtime_status = RuntimeStatus()
game_runtime = GameRuntime("Shinobi Story Online")
monitor_task: asyncio.Task | None = None
WEB_DIR = RESOURCE_DIR / "web"


class AuthRequest(BaseModel):
    token: str = Field(min_length=1, max_length=500)


class SendRequest(BaseModel):
    message: str = Field(min_length=1)
    channel: Literal["ooc", "ic"] = "ooc"


class InputPreferenceRequest(BaseModel):
    channel: Literal["ooc", "ic"] = "ooc"
    width: int = Field(ge=20, le=4000)
    height: int = Field(ge=10, le=1000)
    relative_left: int | None = Field(default=None, ge=-10000, le=10000)
    relative_top: int | None = Field(default=None, ge=-10000, le=10000)
    candidate_index: int | None = Field(default=None, ge=0, le=10000)
    parent_class: str = Field(default="", max_length=200)


async def monitor_chat_loop() -> None:
    stored_snapshot, stored_pending = await asyncio.to_thread(history.monitor_state)
    if stored_snapshot is None:
        stored = await asyncio.to_thread(history.recent_incoming_texts, 800)
        previous_text = "\n".join(stored)
        stored_pending = unfinished_ic_suffix(previous_text)
    else:
        previous_text = stored_snapshot
    channel_parser = ChatChannelParser(stored_pending)
    last_status_broadcast = 0.0
    last_window_scan = 0.0
    logger = logging.getLogger("kagelink")

    while True:
        try:
            game_hwnd = await asyncio.to_thread(find_game_window, config.game_title)
            runtime_status.game_online = game_hwnd is not None
            runtime_status.game_foreground = await asyncio.to_thread(
                is_game_window_foreground,
                game_hwnd,
            )

            now_monotonic = time.monotonic()
            if game_hwnd is None and now_monotonic - last_window_scan >= 15.0:
                snapshot = await asyncio.to_thread(
                    window_scan_snapshot,
                    config.game_title,
                    30,
                )
                logger.warning(
                    "Game window not located. Configured title=%r. Window scan=%s",
                    config.game_title,
                    json.dumps(snapshot, ensure_ascii=False),
                )
                last_window_scan = now_monotonic

            current = await asyncio.to_thread(reader.read_current)
            runtime_status.chat_hwnd = reader.hwnd
            runtime_status.chat_found = bool(reader.hwnd and current is not None)

            _, located_inputs = await asyncio.to_thread(sender.locate_channels)
            ooc_input = located_inputs.get("ooc")
            ic_input = located_inputs.get("ic")
            runtime_status.ooc_input_found = ooc_input is not None
            runtime_status.ic_input_found = ic_input is not None
            runtime_status.ooc_input_hwnd = ooc_input.hwnd if ooc_input else None
            runtime_status.ic_input_hwnd = ic_input.hwnd if ic_input else None

            addition, resynchronized = find_new_text(previous_text, current)
            if resynchronized:
                channel_parser.reset()

            parsed_messages = channel_parser.feed(addition)
            if resynchronized and parsed_messages:
                recent_records = await asyncio.to_thread(
                    history.recent_incoming_records,
                    500,
                )
                parsed_messages = drop_replayed_prefix(
                    parsed_messages,
                    recent_records,
                )

            for parsed in parsed_messages:
                record = await asyncio.to_thread(
                    history.add,
                    "incoming",
                    parsed.text,
                    resynchronized,
                    parsed.channel,
                )
                runtime_status.last_chat_update = time.time()
                await manager.broadcast({"type": "message", "message": record})

            if current:
                previous_text = current
                await asyncio.to_thread(
                    history.save_monitor_state,
                    current,
                    channel_parser.pending_text,
                )

            now = time.monotonic()
            if now - last_status_broadcast >= 5.0:
                await manager.broadcast({"type": "status", "status": runtime_status.to_dict()})
                last_status_broadcast = now
            runtime_status.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as error:
            runtime_status.last_error = str(error)
            await manager.broadcast({"type": "error", "message": str(error)})
        await asyncio.sleep(config.poll_interval_seconds)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global monitor_task
    monitor_task = asyncio.create_task(monitor_chat_loop(), name="shinobi-chat-monitor")
    try:
        yield
    finally:
        if monitor_task:
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task
        await asyncio.to_thread(game_runtime.close)


app = FastAPI(
    title="KageLink PC Agent",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/api/health", include_in_schema=False)
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "application": "KageLink PC Agent",
        "version": APP_VERSION,
    }


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest() -> FileResponse:
    return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(
        WEB_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.post("/api/auth")
async def authenticate(request: AuthRequest) -> dict[str, Any]:
    if not security.valid(request.token):
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")
    return {"ok": True}


@app.get("/api/status", dependencies=[Depends(security.require_authorization)])
async def get_status() -> dict[str, Any]:
    return runtime_status.to_dict()


@app.get("/api/history", dependencies=[Depends(security.require_authorization)])
async def get_history(limit: int = Query(default=500, ge=1, le=2000)) -> dict[str, Any]:
    return {"messages": await asyncio.to_thread(history.recent, limit)}


@app.get("/api/input-candidates", dependencies=[Depends(security.require_authorization)])
async def get_input_candidates() -> dict[str, Any]:
    game_hwnd, candidates = await asyncio.to_thread(
        input_candidates,
        config.game_title,
        config.input_class,
    )
    ooc_preference = sender.preference("ooc")
    ic_preference = sender.preference("ic")
    return {
        "game_hwnd": game_hwnd,
        "preferred_width": ooc_preference.preferred_width,
        "preferred_height": ooc_preference.preferred_height,
        "preferences": {
            "ooc": ooc_preference.to_dict(),
            "ic": ic_preference.to_dict(),
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
    }


@app.post("/api/input-preference", dependencies=[Depends(security.require_authorization)])
async def set_input_preference(request: InputPreferenceRequest) -> dict[str, Any]:
    preference = await asyncio.to_thread(
        update_input_preference,
        request.channel,
        width=request.width,
        height=request.height,
        relative_left=request.relative_left,
        relative_top=request.relative_top,
        candidate_index=request.candidate_index,
        parent_class=request.parent_class,
    )
    sender.update_preference(request.channel, preference)
    return {
        "ok": True,
        "channel": request.channel,
        "preference": preference.to_dict(),
        "preferred_width": preference.preferred_width,
        "preferred_height": preference.preferred_height,
    }


@app.post("/api/send", dependencies=[Depends(security.require_authorization)])
async def send_message(request: SendRequest) -> dict[str, Any]:
    message = request.message.replace("\r", " ").replace("\n", " ").strip()
    if not message:
        raise HTTPException(status_code=400, detail="EMPTY_MESSAGE")
    if len(message) > config.max_message_length:
        raise HTTPException(status_code=400, detail="MESSAGE_TOO_LONG")

    runtime_status.send_state = f"preparing_{request.channel}"
    await manager.broadcast({"type": "status", "status": runtime_status.to_dict()})
    try:
        result = await asyncio.to_thread(sender.send, message, request.channel)
    except (ValueError, RuntimeError) as error:
        runtime_status.send_state = "failed"
        runtime_status.last_error = str(error)
        await manager.broadcast({"type": "status", "status": runtime_status.to_dict()})
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        runtime_status.send_state = "failed"
        runtime_status.last_error = str(error)
        raise HTTPException(status_code=500, detail="SEND_FAILED") from error

    record = await asyncio.to_thread(
        history.add,
        "outgoing",
        message,
        False,
        request.channel,
    )
    runtime_status.last_send = time.time()
    runtime_status.last_error = None
    runtime_status.send_state = "sent"
    await manager.broadcast({"type": "message", "message": record})
    await manager.broadcast({"type": "status", "status": runtime_status.to_dict()})
    runtime_status.send_state = "idle"
    return {
        "ok": True,
        "message": record,
        "channel": request.channel,
        "input": result["input"],
        "focus": result["focus"],
    }


@app.get("/api/game/status", dependencies=[Depends(security.require_authorization)])
async def get_game_status() -> dict[str, Any]:
    return await asyncio.to_thread(game_runtime.status)


@app.websocket("/ws/game/stream")
async def game_stream_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    mode: str = Query(default="full"),
) -> None:
    if not security.valid(token):
        await websocket.close(code=1008, reason="INVALID_TOKEN")
        return

    safe_mode = normalize_view_mode(mode)
    await websocket.accept()
    frame_interval = 0.1
    last_metadata_at = 0.0
    last_state = ""
    try:
        while True:
            started = time.monotonic()
            try:
                frame, metadata = await asyncio.to_thread(
                    game_runtime.capture_frame,
                    safe_mode,
                )
                now = time.monotonic()
                if now - last_metadata_at >= 1.0 or last_state != "live":
                    await websocket.send_json(metadata)
                    last_metadata_at = now
                    last_state = "live"
                await websocket.send_bytes(frame)
            except Exception as error:
                message = str(error)
                state = (
                    "not_found"
                    if "GAME_NOT_FOUND" in message
                    else "minimized"
                    if "GAME_MINIMIZED" in message
                    else "error"
                )
                if state != last_state or time.monotonic() - last_metadata_at >= 1.0:
                    await websocket.send_json(
                        {
                            "type": "stream_status",
                            "state": state,
                            "mode": safe_mode,
                            "message": message,
                            "timestamp": time.time(),
                        }
                    )
                    last_state = state
                    last_metadata_at = time.monotonic()
                await asyncio.sleep(0.5)

            elapsed = time.monotonic() - started
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)
    except WebSocketDisconnect:
        pass
    except Exception:
        logging.getLogger("kagelink.game").exception("Game stream disconnected")
    finally:
        await asyncio.to_thread(game_runtime.release_all)


@app.websocket("/ws/game/control")
async def game_control_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    if not security.valid(token):
        await websocket.close(code=1008, reason="INVALID_TOKEN")
        return


    await websocket.accept()
    last_signal = time.monotonic()
    activated = False
    try:
        await websocket.send_json(
            {"type": "control_status", "state": "connected", "timestamp": time.time()}
        )
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                if time.monotonic() - last_signal > 4.0:
                    await asyncio.to_thread(game_runtime.release_all)
                    await websocket.send_json(
                        {"type": "control_status", "state": "heartbeat_timeout"}
                    )
                    await websocket.close(code=1011, reason="HEARTBEAT_TIMEOUT")
                    return
                continue

            last_signal = time.monotonic()
            try:
                payload = json.loads(raw)
                command = parse_control_message(payload)
                if command.kind == "active":
                    if command.active:
                        await asyncio.to_thread(game_runtime.activate_control)
                        activated = True
                        pressed: list[str] = []
                        state = "active"
                    else:
                        await asyncio.to_thread(game_runtime.deactivate_control)
                        activated = False
                        pressed = []
                        state = "inactive"
                    await websocket.send_json(
                        {
                            "type": "control_status",
                            "state": state,
                            "pressed": pressed,
                            "timestamp": time.time(),
                        }
                    )
                    continue

                if not activated:
                    raise ValueError("GAME_CONTROL_INACTIVE")

                if command.kind == "focus_click":
                    try:
                        await asyncio.to_thread(game_runtime.click_game_center)
                        await websocket.send_json(
                            {
                                "type": "focus_status",
                                "state": "clicked",
                                "timestamp": time.time(),
                            }
                        )
                    except Exception as error:
                        await websocket.send_json(
                            {
                                "type": "focus_status",
                                "state": "error",
                                "message": str(error),
                                "timestamp": time.time(),
                            }
                        )
                    continue

                pressed = await asyncio.to_thread(
                    game_runtime.apply_keys,
                    command.pressed,
                )
                if command.kind == "heartbeat":
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "timestamp": command.timestamp,
                            "server_time": time.time(),
                            "pressed": pressed,
                        }
                    )
            except Exception as error:
                activated = False
                await asyncio.to_thread(game_runtime.release_all)
                await websocket.send_json(
                    {
                        "type": "control_error",
                        "message": str(error),
                        "timestamp": time.time(),
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logging.getLogger("kagelink.game").exception("Game control disconnected")
    finally:
        await asyncio.to_thread(game_runtime.deactivate_control)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    if not security.valid(token):
        await websocket.close(code=1008, reason="INVALID_TOKEN")
        return
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "status", "status": runtime_status.to_dict()})
        while True:
            await websocket.receive_text()
            await websocket.send_json({"type": "pong", "timestamp": time.time()})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
