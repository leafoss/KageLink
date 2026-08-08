from __future__ import annotations

import argparse
import asyncio
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# This prototype lives under pc_agent/prototypes. Add the pc_agent project root
# so the canonical game capture/window helpers remain the source of truth.
HERE = Path(__file__).resolve().parent
PC_AGENT_ROOT = HERE.parents[1]
if str(PC_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PC_AGENT_ROOT))

import numpy as np
import uvicorn
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from av import VideoFrame
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from capture import DesktopFrameSource, FrameHub, GameFrameSource
from input_win32 import InputError, SafeInputController, start_kill_switch
from security import SecurityError, Session, SessionAuthority, SlidingWindowLimiter, mask_ip


VERSION = "0.3.1-security"
DEFAULT_GAME_TITLE = "Shinobi Story Online"
WEB_DIR = HERE / "web"
RUNTIME_DIR = HERE / "runtime"
AUDIT_PATH = RUNTIME_DIR / "audit.jsonl"
EXTERNAL_ADDRESS_PATH = HERE / "ENDERECO_EXTERNO_KAGELINK.txt"
QUICK_TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


class AuditLogger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"kagelink.remote.audit.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = RotatingFileHandler(
            path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.handlers[:] = [handler]

    def __call__(self, event: str, payload: dict) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": str(event)[:80],
            **payload,
        }
        # Defense in depth: audit never stores authentication material or user
        # input content, even if a future caller accidentally passes it.
        for forbidden in (
            "token",
            "session_token",
            "peer_grant",
            "client_nonce",
            "text",
            "key",
            "message",
            "clipboard",
        ):
            record.pop(forbidden, None)
        self.logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


class ControlGate:
    def __init__(self, *, cli_allowed: bool) -> None:
        self.cli_allowed = bool(cli_allowed)
        self._enabled = bool(cli_allowed)
        self._emergency_latched = False
        self._reason = ""
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def emergency_latched(self) -> bool:
        with self._lock:
            return self._emergency_latched

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def trip(self, reason: str) -> None:
        with self._lock:
            self._enabled = False
            self._emergency_latched = True
            self._reason = str(reason)[:80]

    def enable_locally(self) -> None:
        with self._lock:
            if not self.cli_allowed:
                raise SecurityError("CONTROL_DISABLED_BY_HOST")
            self._enabled = True
            self._emergency_latched = False
            self._reason = ""


class QuickTunnel:
    def __init__(self, *, port: int) -> None:
        self.port = int(port)
        self.process: subprocess.Popen[str] | None = None
        self.url = ""
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _find_binary(self) -> str | None:
        candidates = [
            HERE / "cloudflared.exe",
            PC_AGENT_ROOT / "cloudflared.exe",
            PC_AGENT_ROOT / "runtime" / "cloudflared.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("cloudflared") or shutil.which("cloudflared.exe")

    def start(self) -> None:
        binary = self._find_binary()
        if not binary:
            print("[Tunnel] cloudflared.exe not found. Local host remains available.")
            print("[Tunnel] Install/use the verified KageLink cloudflared binary, then restart.")
            return
        try:
            EXTERNAL_ADDRESS_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        command = [
            binary,
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{self.port}",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        self._thread = threading.Thread(target=self._reader, name="KageLinkRemoteTunnel", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            if self._stop.is_set():
                break
            match = QUICK_TUNNEL_PATTERN.search(line)
            if match and not self.url:
                self.url = match.group(0)
                try:
                    EXTERNAL_ADDRESS_PATH.write_text(self.url + "\n", encoding="utf-8")
                except Exception:
                    pass
                print(f"[Tunnel] External address: {self.url}")
                print("[Tunnel] No permanent access key exists; approve each device locally.")

    def stop(self) -> None:
        self._stop.set()
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self.process = None


def _safe_json_string(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text[:limit]


def _json_error(code: str, *, status: int, retry_after: int | None = None) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if retry_after:
        headers["Retry-After"] = str(int(retry_after))
    return JSONResponse(
        {"ok": False, "error": code},
        status_code=status,
        headers=headers,
    )


def _security_status(error: SecurityError) -> int:
    if error.code == "RATE_LIMITED":
        return 429
    if error.code in {
        "INVALID_SESSION",
        "SESSION_EXPIRED",
        "INVALID_PEER_GRANT",
    }:
        return 401
    if error.code in {
        "CONTROL_NOT_GRANTED",
        "CONTROL_DISABLED_BY_HOST",
    }:
        return 403
    if error.code in {
        "PAIR_REQUEST_NOT_FOUND",
        "SESSION_NOT_FOUND",
    }:
        return 404
    if error.code in {
        "CONTROLLER_BUSY",
        "SESSION_LIMIT_REACHED",
        "PAIR_REQUEST_NOT_PENDING",
    }:
        return 409
    return 400


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin", "").strip()
    host = request.headers.get("host", "").strip().casefold()
    if not origin or not host:
        raise SecurityError("ORIGIN_REQUIRED")
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() != host:
        raise SecurityError("ORIGIN_REJECTED")


def _bearer_token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0].casefold() != "bearer" or not parts[1].strip():
        raise SecurityError("INVALID_SESSION")
    return parts[1].strip()


def _is_loopback_host(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value.casefold() in {"localhost"}


@dataclass(slots=True)
class PeerContext:
    session_id: str
    role: str
    client_ip: str
    pc: RTCPeerConnection
    channel: Any = None
    last_heartbeat: float = field(default_factory=time.monotonic)
    watchdog_released: bool = False
    event_limiter: SlidingWindowLimiter = field(default_factory=SlidingWindowLimiter)


class HubVideoTrack(VideoStreamTrack):
    def __init__(self, hub: FrameHub) -> None:
        super().__init__()
        self.hub = hub
        self._last_sequence = -1

    async def recv(self) -> VideoFrame:
        latest = await asyncio.to_thread(
            self.hub.wait_for_new,
            self._last_sequence,
            timeout=1.0,
        )
        if latest is None:
            await asyncio.sleep(0.05)
            latest = self.hub.get_latest()
            if latest is None:
                image = np.zeros((360, 640, 3), dtype=np.uint8)
            else:
                image = np.asarray(latest.image, dtype=np.uint8)
        else:
            self._last_sequence = latest.sequence
            image = np.asarray(latest.image, dtype=np.uint8)
        frame = VideoFrame.from_ndarray(image, format="rgb24")
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        return frame


class RemoteRuntime:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.audit = AuditLogger(AUDIT_PATH)
        self.authority = SessionAuthority(
            pair_ttl_seconds=args.pair_ttl,
            session_idle_ttl_seconds=args.session_idle_minutes * 60,
            session_absolute_ttl_seconds=args.session_max_hours * 60 * 60,
            peer_grant_ttl_seconds=30,
            max_sessions=4,
            audit=self.audit,
        )
        self.gate = ControlGate(cli_allowed=args.allow_control)
        self.admin_token = secrets.token_urlsafe(32)
        self.api_limiter = SlidingWindowLimiter()
        self.peers: dict[str, PeerContext] = {}
        self._peer_lock = asyncio.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event = threading.Event()
        self.tunnel = QuickTunnel(port=args.port) if args.tunnel == "cloudflare-quick" else None

        if args.mode == "game":
            output_width = max(640, int(args.max_width))
            output_height = max(360, int(round(output_width * 9 / 16)))
            source = GameFrameSource(
                game_title=args.game_title,
                output_width=output_width,
                output_height=output_height,
                jpeg_quality=args.jpeg_quality,
            )
        else:
            source = DesktopFrameSource(monitor=args.monitor, max_width=args.max_width)
        self.frame_hub = FrameHub(source, fps=args.fps)
        self.input = SafeInputController(
            mode=args.mode,
            game_title=args.game_title,
            pointer_mapper=self.frame_hub.map_pointer,
            desktop_authorized=args.allow_desktop_control,
        )

    def client_ip(self, request: Request) -> str:
        direct = request.client.host if request.client else "unknown"
        if not self.args.trust_cloudflare_proxy:
            return direct
        candidate = request.headers.get("cf-connecting-ip", "").strip()
        if not candidate:
            return direct
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return direct

    def ice_servers_public(self) -> list[dict]:
        rows: list[dict] = []
        if self.args.stun:
            rows.append({"urls": [self.args.stun]})
        if self.args.turn_url:
            item: dict[str, Any] = {"urls": [self.args.turn_url]}
            if self.args.turn_username:
                item["username"] = self.args.turn_username
            if self.args.turn_credential:
                item["credential"] = self.args.turn_credential
            rows.append(item)
        return rows

    def rtc_configuration(self) -> RTCConfiguration:
        servers: list[RTCIceServer] = []
        if self.args.stun:
            servers.append(RTCIceServer(urls=[self.args.stun]))
        if self.args.turn_url:
            servers.append(
                RTCIceServer(
                    urls=[self.args.turn_url],
                    username=self.args.turn_username or None,
                    credential=self.args.turn_credential or None,
                )
            )
        return RTCConfiguration(iceServers=servers)

    async def ensure_input_active(self) -> None:
        if not self.gate.enabled:
            raise SecurityError("CONTROL_DISABLED_BY_HOST")
        if not self.input.enabled:
            await asyncio.to_thread(self.input.activate)

    async def close_peer(self, session_id: str, *, release_input: bool = True) -> None:
        context: PeerContext | None = None
        async with self._peer_lock:
            context = self.peers.pop(session_id, None)
        if context is None:
            return
        if release_input and context.role == "control":
            await asyncio.to_thread(self.input.release_all)
        try:
            await context.pc.close()
        except Exception:
            pass

    async def close_all_peers(self) -> None:
        async with self._peer_lock:
            ids = list(self.peers)
        for session_id in ids:
            await self.close_peer(session_id)

    async def emergency_stop(self, reason: str) -> None:
        self.gate.trip(reason)
        await asyncio.to_thread(self.input.deactivate)
        self.authority.disconnect_all(reason=reason)
        await self.close_all_peers()
        self.audit("emergency_stop", {"reason": str(reason)[:80]})

    def emergency_stop_from_thread(self, reason: str) -> None:
        self.gate.trip(reason)
        try:
            self.input.deactivate()
        except Exception:
            pass
        self.authority.disconnect_all(reason=reason)
        self.audit("emergency_stop", {"reason": str(reason)[:80]})
        loop = self.loop
        if loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.close_all_peers(), loop)
            except Exception:
                pass

    async def handle_message(self, context: PeerContext, raw: str) -> None:
        if not isinstance(raw, str) or len(raw) > 4096:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        kind = str(payload.get("type", "")).strip().casefold()
        now = time.monotonic()

        try:
            context.event_limiter.hit(
                f"dc:{context.session_id}",
                limit=500,
                window_seconds=1.0,
                now=now,
            )
            session = self.authority.get_session(context.session_id)
            if session is None:
                await self.close_peer(context.session_id)
                return

            if kind == "heartbeat":
                context.last_heartbeat = now
                context.watchdog_released = False
                self.authority.touch_session_id(context.session_id)
                return
            if kind == "ping":
                context.last_heartbeat = now
                self.authority.touch_session_id(context.session_id)
                if context.channel and context.channel.readyState == "open":
                    context.channel.send(
                        json.dumps(
                            {"type": "pong", "t": payload.get("t")},
                            separators=(",", ":"),
                        )
                    )
                return
            if kind == "release_all":
                await asyncio.to_thread(self.input.release_all)
                return
            if context.role != "control":
                raise SecurityError("CONTROL_NOT_GRANTED")
            if not self.gate.enabled:
                raise SecurityError("CONTROL_DISABLED_BY_HOST")
            await self.ensure_input_active()

            if kind == "key":
                key_name = _safe_json_string(payload.get("key"), limit=24)
                down = bool(payload.get("down"))
                await asyncio.to_thread(self.input.send_key, key_name, down)
            elif kind == "text":
                text = str(payload.get("text", ""))
                context.event_limiter.hit(
                    f"text:{context.session_id}",
                    limit=30,
                    window_seconds=1.0,
                    now=now,
                )
                accepted = await asyncio.to_thread(self.input.send_text, text)
                if context.channel and context.channel.readyState == "open":
                    context.channel.send(json.dumps({"type": "text_ack", "length": accepted}))
            elif kind == "pointer":
                await asyncio.to_thread(
                    self.input.pointer,
                    x=payload.get("x"),
                    y=payload.get("y"),
                    action=_safe_json_string(payload.get("action"), limit=12),
                    button=_safe_json_string(payload.get("button", "left"), limit=12),
                )
        except SecurityError as exc:
            if context.channel and context.channel.readyState == "open":
                context.channel.send(json.dumps({"type": "error", "error": exc.code}))
        except InputError as exc:
            if context.channel and context.channel.readyState == "open":
                context.channel.send(json.dumps({"type": "error", "error": str(exc)[:80]}))
        except Exception:
            if context.channel and context.channel.readyState == "open":
                context.channel.send(json.dumps({"type": "error", "error": "INPUT_FAILED"}))

    async def register_peer(self, session: Session, pc: RTCPeerConnection) -> PeerContext:
        async with self._peer_lock:
            existing = self.peers.get(session.session_id)
            if existing is not None and existing.pc.connectionState not in {"closed", "failed"}:
                raise SecurityError("PEER_ALREADY_ACTIVE")
            context = PeerContext(
                session_id=session.session_id,
                role=session.role,
                client_ip=session.ip,
                pc=pc,
            )
            self.peers[session.session_id] = context
            return context

    async def maintenance(self) -> None:
        while not self.stop_event.is_set():
            await asyncio.sleep(1.0)
            sweep = self.authority.sweep()
            for session_id in sweep["expired_sessions"]:
                await self.close_peer(session_id)
            now = time.monotonic()
            async with self._peer_lock:
                contexts = list(self.peers.values())
            for context in contexts:
                silence = now - context.last_heartbeat
                if context.role == "control" and silence >= 5.0 and not context.watchdog_released:
                    context.watchdog_released = True
                    await asyncio.to_thread(self.input.release_all)
                    self.audit(
                        "input_watchdog_release",
                        {"session_id": context.session_id[:10], "silence_seconds": round(silence, 1)},
                    )
                if silence >= 15.0:
                    await self.close_peer(context.session_id)


def create_public_app(runtime: RemoteRuntime) -> FastAPI:
    app = FastAPI(title="KageLink Remote", version=VERSION, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), usb=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'"
        )
        return response

    @app.exception_handler(SecurityError)
    async def security_error_handler(_: Request, exc: SecurityError):
        return _json_error(exc.code, status=_security_status(exc), retry_after=exc.retry_after)

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "client.html")

    @app.get("/healthz")
    async def healthz():
        return {
            "ok": True,
            "version": VERSION,
            "mode": runtime.args.mode,
            "control_available": runtime.args.allow_control,
        }

    @app.post("/api/pair")
    async def pair(request: Request):
        _require_same_origin(request)
        ip = runtime.client_ip(request)
        runtime.api_limiter.hit(f"pair-api:{ip}", limit=8, window_seconds=60)
        try:
            body = await request.json()
        except Exception:
            raise SecurityError("INVALID_JSON") from None
        if not isinstance(body, dict):
            raise SecurityError("INVALID_JSON")
        item = runtime.authority.request_pair(
            ip=ip,
            client_name=_safe_json_string(body.get("client_name"), limit=64),
            user_agent=_safe_json_string(request.headers.get("user-agent"), limit=160),
            requested_role=_safe_json_string(body.get("role", "control"), limit=12),
            client_nonce=_safe_json_string(body.get("client_nonce"), limit=256),
        )
        return {
            "ok": True,
            "request_id": item.request_id,
            "expires_in": runtime.authority.pair_ttl_seconds,
        }

    @app.post("/api/pair/status")
    async def pair_status(request: Request):
        _require_same_origin(request)
        ip = runtime.client_ip(request)
        runtime.api_limiter.hit(f"pair-poll:{ip}", limit=150, window_seconds=60)
        try:
            body = await request.json()
        except Exception:
            raise SecurityError("INVALID_JSON") from None
        if not isinstance(body, dict):
            raise SecurityError("INVALID_JSON")
        result = runtime.authority.poll_pair(
            ip=ip,
            request_id=_safe_json_string(body.get("request_id"), limit=128),
            client_nonce=_safe_json_string(body.get("client_nonce"), limit=256),
        )
        return {"ok": True, **result}

    @app.post("/api/peer-grant")
    async def peer_grant(request: Request):
        _require_same_origin(request)
        ip = runtime.client_ip(request)
        token = _bearer_token(request)
        session = runtime.authority.validate_session(token, ip=ip, touch=True)
        runtime.api_limiter.hit(
            f"grant:{session.session_id}",
            limit=30,
            window_seconds=60,
        )
        grant = runtime.authority.issue_peer_grant(token, ip=ip)
        return {
            "ok": True,
            **grant,
            "role": session.role,
            "iceServers": runtime.ice_servers_public(),
            "mode": runtime.args.mode,
            "control_enabled": runtime.gate.enabled,
        }

    @app.post("/api/rtc/offer")
    async def rtc_offer(request: Request):
        _require_same_origin(request)
        ip = runtime.client_ip(request)
        runtime.api_limiter.hit(f"offer:{ip}", limit=30, window_seconds=60)
        try:
            body = await request.json()
        except Exception:
            raise SecurityError("INVALID_JSON") from None
        if not isinstance(body, dict):
            raise SecurityError("INVALID_JSON")
        grant_token = _safe_json_string(body.get("peer_grant"), limit=512)
        sdp = str(body.get("sdp", ""))
        offer_type = _safe_json_string(body.get("type"), limit=16)
        if not sdp or len(sdp) > 300_000 or offer_type != "offer":
            raise SecurityError("INVALID_RTC_OFFER")
        session = runtime.authority.consume_peer_grant(grant_token, ip=ip)
        pc = RTCPeerConnection(configuration=runtime.rtc_configuration())
        context = await runtime.register_peer(session, pc)
        pc.addTrack(HubVideoTrack(runtime.frame_hub))

        @pc.on("datachannel")
        def on_datachannel(channel):
            if channel.label != "kagelink-control":
                try:
                    channel.close()
                except Exception:
                    pass
                return
            context.channel = channel
            context.last_heartbeat = time.monotonic()

            @channel.on("message")
            def on_message(message):
                if isinstance(message, str):
                    asyncio.create_task(runtime.handle_message(context, message))

            @channel.on("close")
            def on_close():
                if context.role == "control":
                    try:
                        runtime.input.release_all()
                    except Exception:
                        pass

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState in {"failed", "closed"}:
                await runtime.close_peer(session.session_id)

        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=offer_type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            local = pc.localDescription
            if local is None:
                raise SecurityError("RTC_ANSWER_FAILED")
            return {
                "ok": True,
                "sdp": local.sdp,
                "type": local.type,
                "session_id": session.session_id,
                "role": session.role,
            }
        except Exception:
            await runtime.close_peer(session.session_id)
            raise

    return app


def create_admin_app(runtime: RemoteRuntime) -> FastAPI:
    app = FastAPI(title="KageLink Remote Local Admin", version=VERSION, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.middleware("http")
    async def admin_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(SecurityError)
    async def security_error_handler(_: Request, exc: SecurityError):
        return _json_error(exc.code, status=_security_status(exc), retry_after=exc.retry_after)

    def require_admin(request: Request, *, origin: bool = False) -> None:
        host = request.client.host if request.client else ""
        if not _is_loopback_host(host):
            raise SecurityError("ADMIN_LOCAL_ONLY")
        token = request.headers.get("x-kagelink-admin", "")
        if not token or not hmac.compare_digest(token, runtime.admin_token):
            raise SecurityError("ADMIN_UNAUTHORIZED")
        if origin:
            _require_same_origin(request)

    @app.get("/")
    async def admin_index():
        return FileResponse(WEB_DIR / "admin.html")

    @app.get("/api/state")
    async def state(request: Request):
        require_admin(request)
        return {
            "ok": True,
            "version": VERSION,
            "mode": runtime.args.mode,
            "control_allowed_by_cli": runtime.gate.cli_allowed,
            "control_enabled": runtime.gate.enabled,
            "emergency_latched": runtime.gate.emergency_latched,
            "emergency_reason": runtime.gate.reason,
            "pending": runtime.authority.list_pending(),
            "sessions": runtime.authority.list_sessions(),
            "capture": runtime.frame_hub.diagnostics(),
            "external_url": runtime.tunnel.url if runtime.tunnel else "",
            "local_url": f"http://127.0.0.1:{runtime.args.port}",
        }

    @app.post("/api/approve")
    async def approve(request: Request):
        require_admin(request, origin=True)
        body = await request.json()
        request_id = _safe_json_string(body.get("request_id"), limit=128) if isinstance(body, dict) else ""
        role = _safe_json_string(body.get("role"), limit=12) if isinstance(body, dict) else ""
        if role == "control" and not runtime.gate.cli_allowed:
            raise SecurityError("CONTROL_DISABLED_BY_HOST")
        session = runtime.authority.approve(request_id, role=role or None)
        return {"ok": True, "session": session}

    @app.post("/api/deny")
    async def deny(request: Request):
        require_admin(request, origin=True)
        body = await request.json()
        request_id = _safe_json_string(body.get("request_id"), limit=128) if isinstance(body, dict) else ""
        runtime.authority.deny(request_id)
        return {"ok": True}

    @app.post("/api/disconnect")
    async def disconnect(request: Request):
        require_admin(request, origin=True)
        body = await request.json()
        session_id = _safe_json_string(body.get("session_id"), limit=128) if isinstance(body, dict) else ""
        runtime.authority.disconnect(session_id, reason="DISCONNECTED_BY_HOST")
        await runtime.close_peer(session_id)
        return {"ok": True}

    @app.post("/api/emergency-stop")
    async def emergency_stop(request: Request):
        require_admin(request, origin=True)
        await runtime.emergency_stop("LOCAL_ADMIN_EMERGENCY_STOP")
        return {"ok": True}

    @app.post("/api/enable-input")
    async def enable_input(request: Request):
        require_admin(request, origin=True)
        runtime.gate.enable_locally()
        runtime.audit("remote_input_enabled_locally", {"mode": runtime.args.mode})
        return {"ok": True}

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KageLink Remote Control consent-first prototype")
    parser.add_argument("--bind", default="127.0.0.1", help="Public/signaling bind address")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--admin-port", type=int, default=8766)
    parser.add_argument("--mode", choices=("game", "desktop"), default="game")
    parser.add_argument("--game-title", default=DEFAULT_GAME_TITLE)
    parser.add_argument("--allow-control", action="store_true", help="Allow locally approved input sessions")
    parser.add_argument(
        "--allow-desktop-control",
        action="store_true",
        help="Explicitly authorize full-desktop input; required with --mode desktop --allow-control",
    )
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--max-width", type=int, default=1600)
    parser.add_argument("--jpeg-quality", type=int, default=82)
    parser.add_argument("--monitor", type=int, default=1)
    parser.add_argument("--pair-ttl", type=int, default=90)
    parser.add_argument("--session-idle-minutes", type=int, default=30)
    parser.add_argument("--session-max-hours", type=int, default=8)
    parser.add_argument("--tunnel", choices=("none", "cloudflare-quick"), default="none")
    parser.add_argument("--trust-cloudflare-proxy", action="store_true")
    parser.add_argument("--stun", default="stun:stun.l.google.com:19302")
    parser.add_argument("--turn-url", default=os.environ.get("KAGELINK_TURN_URL", ""))
    parser.add_argument("--turn-username", default=os.environ.get("KAGELINK_TURN_USERNAME", ""))
    parser.add_argument("--turn-credential", default=os.environ.get("KAGELINK_TURN_CREDENTIAL", ""))
    args = parser.parse_args()

    if not (1024 <= args.port <= 65535 and 1024 <= args.admin_port <= 65535):
        parser.error("ports must be between 1024 and 65535")
    if args.port == args.admin_port:
        parser.error("public and admin ports must be different")
    if args.mode == "desktop" and args.allow_control and not args.allow_desktop_control:
        parser.error("desktop control requires --allow-desktop-control as an explicit local authorization")
    if args.trust_cloudflare_proxy and not _is_loopback_host(args.bind):
        parser.error("--trust-cloudflare-proxy is allowed only while the public server binds to loopback")
    if args.tunnel == "cloudflare-quick" and not _is_loopback_host(args.bind):
        parser.error("Cloudflare tunnel mode must bind the KageLink public server to loopback")
    return args


async def run(args: argparse.Namespace) -> None:
    if not WEB_DIR.exists():
        raise SystemExit(f"Missing web assets: {WEB_DIR}")
    runtime = RemoteRuntime(args)
    runtime.loop = asyncio.get_running_loop()
    runtime.frame_hub.start()
    start_kill_switch(
        lambda: runtime.emergency_stop_from_thread("LOCAL_CTRL_ALT_F12"),
        stop_event=runtime.stop_event,
    )

    public_app = create_public_app(runtime)
    admin_app = create_admin_app(runtime)
    public_server = uvicorn.Server(
        uvicorn.Config(
            public_app,
            host=args.bind,
            port=args.port,
            log_level="warning",
            access_log=False,
        )
    )
    admin_server = uvicorn.Server(
        uvicorn.Config(
            admin_app,
            host="127.0.0.1",
            port=args.admin_port,
            log_level="warning",
            access_log=False,
        )
    )

    admin_url = f"http://127.0.0.1:{args.admin_port}/#{runtime.admin_token}"
    public_url = f"http://127.0.0.1:{args.port}"
    print("=" * 72)
    print(f"KageLink Remote {VERSION}")
    print(f"Mode: {args.mode.upper()}")
    print(f"Remote input: {'ALLOWED' if args.allow_control else 'VIEW ONLY'}")
    if args.mode == "desktop":
        print("Desktop control: EXPLICITLY AUTHORIZED" if args.allow_desktop_control else "Desktop control: VIEW ONLY")
    print(f"Local client: {public_url}")
    print(f"Local Admin: {admin_url}")
    print("Emergency stop: CTRL + ALT + F12 on the host PC")
    print("No shell, file transfer, clipboard, audio, key logging or hidden startup exists.")
    print("=" * 72)

    if runtime.tunnel:
        runtime.tunnel.start()

    maintenance_task = asyncio.create_task(runtime.maintenance())
    public_task = asyncio.create_task(public_server.serve())
    admin_task = asyncio.create_task(admin_server.serve())

    async def open_admin_later() -> None:
        await asyncio.sleep(1.0)
        try:
            webbrowser.open(admin_url)
        except Exception:
            pass

    asyncio.create_task(open_admin_later())

    try:
        done, pending = await asyncio.wait(
            {public_task, admin_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        public_server.should_exit = True
        admin_server.should_exit = True
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass
        for task in done:
            exc = task.exception()
            if exc:
                raise exc
    finally:
        runtime.stop_event.set()
        maintenance_task.cancel()
        try:
            await maintenance_task
        except asyncio.CancelledError:
            pass
        await runtime.emergency_stop("HOST_SHUTDOWN")
        runtime.frame_hub.stop()
        if runtime.tunnel:
            runtime.tunnel.stop()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
