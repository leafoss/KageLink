from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Literal


Role = Literal["control", "view"]
AuditHook = Callable[[str, dict], None]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="strict")).hexdigest()


def _safe_name(value: str, limit: int = 64) -> str:
    cleaned = " ".join(str(value or "").replace("\x00", "").split())
    return cleaned[:limit] or "Browser"


def mask_ip(value: str) -> str:
    value = (value or "unknown").strip()
    if ":" in value:
        parts = [part for part in value.split(":") if part]
        if len(parts) >= 3:
            return ":".join(parts[:3]) + ":…"
        return value[:12] + "…" if len(value) > 12 else value
    parts = value.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3] + ["x"])
    return value[:24]


class SecurityError(RuntimeError):
    def __init__(self, code: str, *, retry_after: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> None:
        current = time.monotonic() if now is None else float(now)
        cutoff = current - float(window_seconds)
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= int(limit):
                retry = max(1, int(window_seconds - (current - bucket[0])))
                raise SecurityError("RATE_LIMITED", retry_after=retry)
            bucket.append(current)


@dataclass(slots=True)
class PairRequest:
    request_id: str
    client_nonce_digest: str
    ip: str
    client_name: str
    user_agent: str
    requested_role: Role
    created_at: float
    expires_at: float
    status: str = "pending"
    approved_role: Role | None = None
    session_id: str | None = None
    delivery_token: str | None = None
    decision_reason: str | None = None


@dataclass(slots=True)
class Session:
    session_id: str
    token_digest: str
    ip: str
    client_name: str
    role: Role
    created_at: float
    last_seen_at: float
    idle_expires_at: float
    absolute_expires_at: float
    disconnected: bool = False


@dataclass(slots=True)
class PeerGrant:
    token_digest: str
    session_id: str
    ip: str
    created_at: float
    expires_at: float


class SessionAuthority:
    """Consent-first, memory-only session authority for the remote prototype.

    Long-lived access keys are intentionally not used. A remote browser creates a
    pending request; the local-only Admin UI must approve it. The delivered
    session token is IP-bound, memory-only and expires by idle and absolute TTL.
    Peer grants are single-use and short-lived.
    """

    def __init__(
        self,
        *,
        pair_ttl_seconds: int = 90,
        session_idle_ttl_seconds: int = 30 * 60,
        session_absolute_ttl_seconds: int = 8 * 60 * 60,
        peer_grant_ttl_seconds: int = 30,
        max_sessions: int = 4,
        audit: AuditHook | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.pair_ttl_seconds = max(30, int(pair_ttl_seconds))
        self.session_idle_ttl_seconds = max(60, int(session_idle_ttl_seconds))
        self.session_absolute_ttl_seconds = max(
            self.session_idle_ttl_seconds,
            int(session_absolute_ttl_seconds),
        )
        self.peer_grant_ttl_seconds = max(5, int(peer_grant_ttl_seconds))
        self.max_sessions = max(1, int(max_sessions))
        self._audit_hook = audit
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._pair_limiter = SlidingWindowLimiter()
        self._pending: dict[str, PairRequest] = {}
        self._sessions: dict[str, Session] = {}
        self._session_by_token: dict[str, str] = {}
        self._grants: dict[str, PeerGrant] = {}

    def _now(self) -> float:
        return float(self._clock())

    def _audit(self, event: str, **payload) -> None:
        if self._audit_hook is None:
            return
        safe_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"token", "session_token", "peer_grant", "client_nonce"}
        }
        try:
            self._audit_hook(event, safe_payload)
        except Exception:
            pass

    def _role(self, value: str) -> Role:
        return "view" if str(value).strip().casefold() == "view" else "control"

    def request_pair(
        self,
        *,
        ip: str,
        client_name: str,
        user_agent: str,
        requested_role: str,
        client_nonce: str,
    ) -> PairRequest:
        if len(client_nonce) < 16 or len(client_nonce) > 256:
            raise SecurityError("INVALID_CLIENT_NONCE")
        self._pair_limiter.hit(
            f"pair:{ip}",
            limit=6,
            window_seconds=60,
            now=self._now(),
        )
        now = self._now()
        with self._lock:
            self.sweep(now=now)
            if sum(1 for item in self._pending.values() if item.status == "pending") >= 16:
                raise SecurityError("TOO_MANY_PENDING")
            request_id = secrets.token_urlsafe(24)
            item = PairRequest(
                request_id=request_id,
                client_nonce_digest=_digest(client_nonce),
                ip=ip,
                client_name=_safe_name(client_name),
                user_agent=_safe_name(user_agent, 160),
                requested_role=self._role(requested_role),
                created_at=now,
                expires_at=now + self.pair_ttl_seconds,
            )
            self._pending[request_id] = item
            self._audit(
                "pair_requested",
                request_id=request_id[:10],
                ip=mask_ip(ip),
                client_name=item.client_name,
                requested_role=item.requested_role,
            )
            return item

    def list_pending(self) -> list[dict]:
        now = self._now()
        with self._lock:
            self.sweep(now=now)
            rows: list[dict] = []
            for item in sorted(self._pending.values(), key=lambda row: row.created_at):
                if item.status != "pending":
                    continue
                rows.append(
                    {
                        "request_id": item.request_id,
                        "client_name": item.client_name,
                        "user_agent": item.user_agent,
                        "requested_role": item.requested_role,
                        "ip": mask_ip(item.ip),
                        "expires_in": max(0, int(item.expires_at - now)),
                    }
                )
            return rows

    def _active_sessions_locked(self, now: float) -> list[Session]:
        result: list[Session] = []
        for session in self._sessions.values():
            if session.disconnected:
                continue
            if now >= session.idle_expires_at or now >= session.absolute_expires_at:
                continue
            result.append(session)
        return result

    def approve(self, request_id: str, *, role: str | None = None) -> dict:
        now = self._now()
        with self._lock:
            self.sweep(now=now)
            item = self._pending.get(request_id)
            if item is None or item.status != "pending" or now >= item.expires_at:
                raise SecurityError("PAIR_REQUEST_NOT_PENDING")
            approved_role = self._role(role or item.requested_role)
            active = self._active_sessions_locked(now)
            if len(active) >= self.max_sessions:
                raise SecurityError("SESSION_LIMIT_REACHED")
            if approved_role == "control" and any(row.role == "control" for row in active):
                raise SecurityError("CONTROLLER_BUSY")

            raw_token = secrets.token_urlsafe(32)
            session_id = secrets.token_urlsafe(18)
            session = Session(
                session_id=session_id,
                token_digest=_digest(raw_token),
                ip=item.ip,
                client_name=item.client_name,
                role=approved_role,
                created_at=now,
                last_seen_at=now,
                idle_expires_at=now + self.session_idle_ttl_seconds,
                absolute_expires_at=now + self.session_absolute_ttl_seconds,
            )
            self._sessions[session_id] = session
            self._session_by_token[session.token_digest] = session_id
            item.status = "approved"
            item.approved_role = approved_role
            item.session_id = session_id
            item.delivery_token = raw_token
            self._audit(
                "pair_approved",
                request_id=request_id[:10],
                session_id=session_id[:10],
                role=approved_role,
                client_name=item.client_name,
                ip=mask_ip(item.ip),
            )
            return self._session_summary_locked(session, now)

    def deny(self, request_id: str, *, reason: str = "DENIED_BY_HOST") -> None:
        now = self._now()
        with self._lock:
            item = self._pending.get(request_id)
            if item is None or item.status != "pending" or now >= item.expires_at:
                raise SecurityError("PAIR_REQUEST_NOT_PENDING")
            item.status = "denied"
            item.decision_reason = _safe_name(reason, 80)
            item.expires_at = min(item.expires_at, now + 20)
            self._audit(
                "pair_denied",
                request_id=request_id[:10],
                client_name=item.client_name,
                ip=mask_ip(item.ip),
                reason=item.decision_reason,
            )

    def poll_pair(
        self,
        *,
        ip: str,
        request_id: str,
        client_nonce: str,
    ) -> dict:
        now = self._now()
        with self._lock:
            self.sweep(now=now)
            item = self._pending.get(request_id)
            if item is None:
                raise SecurityError("PAIR_REQUEST_NOT_FOUND")
            if item.ip != ip:
                self._audit("pair_poll_ip_mismatch", request_id=request_id[:10], ip=mask_ip(ip))
                raise SecurityError("PAIR_REQUEST_NOT_FOUND")
            if not hmac.compare_digest(item.client_nonce_digest, _digest(client_nonce)):
                self._audit("pair_poll_nonce_mismatch", request_id=request_id[:10], ip=mask_ip(ip))
                raise SecurityError("PAIR_REQUEST_NOT_FOUND")
            if now >= item.expires_at:
                self._pending.pop(request_id, None)
                raise SecurityError("PAIR_REQUEST_EXPIRED")
            if item.status == "pending":
                return {
                    "status": "pending",
                    "expires_in": max(0, int(item.expires_at - now)),
                }
            if item.status == "denied":
                reason = item.decision_reason or "DENIED_BY_HOST"
                self._pending.pop(request_id, None)
                return {"status": "denied", "reason": reason}
            if item.status == "approved" and item.delivery_token and item.session_id:
                session = self._sessions.get(item.session_id)
                if session is None or session.disconnected:
                    self._pending.pop(request_id, None)
                    raise SecurityError("SESSION_NOT_FOUND")
                raw_token = item.delivery_token
                item.delivery_token = None
                self._pending.pop(request_id, None)
                self._audit(
                    "session_delivered",
                    session_id=session.session_id[:10],
                    role=session.role,
                    ip=mask_ip(ip),
                )
                return {
                    "status": "approved",
                    "session_token": raw_token,
                    "session_id": session.session_id,
                    "role": session.role,
                    "idle_expires_in": max(0, int(session.idle_expires_at - now)),
                    "absolute_expires_in": max(0, int(session.absolute_expires_at - now)),
                }
            raise SecurityError("PAIR_REQUEST_NOT_FOUND")

    def validate_session(
        self,
        token: str,
        *,
        ip: str,
        require_control: bool = False,
        touch: bool = True,
    ) -> Session:
        if not token or len(token) > 512:
            raise SecurityError("INVALID_SESSION")
        now = self._now()
        digest = _digest(token)
        with self._lock:
            self.sweep(now=now)
            session_id = self._session_by_token.get(digest)
            session = self._sessions.get(session_id or "")
            if session is None or session.disconnected:
                raise SecurityError("INVALID_SESSION")
            if session.ip != ip:
                self._audit(
                    "session_ip_mismatch",
                    session_id=session.session_id[:10],
                    expected_ip=mask_ip(session.ip),
                    observed_ip=mask_ip(ip),
                )
                raise SecurityError("INVALID_SESSION")
            if now >= session.idle_expires_at or now >= session.absolute_expires_at:
                self._disconnect_locked(session, "SESSION_EXPIRED")
                raise SecurityError("SESSION_EXPIRED")
            if require_control and session.role != "control":
                raise SecurityError("CONTROL_NOT_GRANTED")
            if touch:
                session.last_seen_at = now
                session.idle_expires_at = min(
                    session.absolute_expires_at,
                    now + self.session_idle_ttl_seconds,
                )
            return session

    def issue_peer_grant(self, token: str, *, ip: str) -> dict:
        now = self._now()
        with self._lock:
            session = self.validate_session(token, ip=ip, touch=True)
            raw_grant = secrets.token_urlsafe(28)
            grant = PeerGrant(
                token_digest=_digest(raw_grant),
                session_id=session.session_id,
                ip=ip,
                created_at=now,
                expires_at=now + self.peer_grant_ttl_seconds,
            )
            self._grants[grant.token_digest] = grant
            self._audit(
                "peer_grant_issued",
                session_id=session.session_id[:10],
                role=session.role,
                ip=mask_ip(ip),
            )
            return {
                "peer_grant": raw_grant,
                "expires_in": self.peer_grant_ttl_seconds,
            }

    def consume_peer_grant(self, grant_token: str, *, ip: str) -> Session:
        if not grant_token or len(grant_token) > 512:
            raise SecurityError("INVALID_PEER_GRANT")
        now = self._now()
        digest = _digest(grant_token)
        with self._lock:
            grant = self._grants.pop(digest, None)
            if grant is None or now >= grant.expires_at or grant.ip != ip:
                self._audit("peer_grant_rejected", ip=mask_ip(ip))
                raise SecurityError("INVALID_PEER_GRANT")
            session = self._sessions.get(grant.session_id)
            if session is None or session.disconnected:
                raise SecurityError("INVALID_SESSION")
            if session.ip != ip:
                raise SecurityError("INVALID_SESSION")
            if now >= session.idle_expires_at or now >= session.absolute_expires_at:
                self._disconnect_locked(session, "SESSION_EXPIRED")
                raise SecurityError("SESSION_EXPIRED")
            session.last_seen_at = now
            session.idle_expires_at = min(
                session.absolute_expires_at,
                now + self.session_idle_ttl_seconds,
            )
            self._audit(
                "peer_grant_consumed",
                session_id=session.session_id[:10],
                role=session.role,
                ip=mask_ip(ip),
            )
            return session

    def touch_session_id(self, session_id: str) -> Session:
        now = self._now()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.disconnected:
                raise SecurityError("INVALID_SESSION")
            if now >= session.idle_expires_at or now >= session.absolute_expires_at:
                self._disconnect_locked(session, "SESSION_EXPIRED")
                raise SecurityError("SESSION_EXPIRED")
            session.last_seen_at = now
            session.idle_expires_at = min(
                session.absolute_expires_at,
                now + self.session_idle_ttl_seconds,
            )
            return session

    def get_session(self, session_id: str) -> Session | None:
        now = self._now()
        with self._lock:
            self.sweep(now=now)
            session = self._sessions.get(session_id)
            if session is None or session.disconnected:
                return None
            return session

    def disconnect(self, session_id: str, *, reason: str = "DISCONNECTED_BY_HOST") -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.disconnected:
                return False
            self._disconnect_locked(session, reason)
            return True

    def disconnect_all(self, *, reason: str = "HOST_EMERGENCY_STOP") -> list[str]:
        with self._lock:
            session_ids: list[str] = []
            for session in self._sessions.values():
                if session.disconnected:
                    continue
                session_ids.append(session.session_id)
                self._disconnect_locked(session, reason)
            return session_ids

    def _disconnect_locked(self, session: Session, reason: str) -> None:
        if session.disconnected:
            return
        session.disconnected = True
        self._session_by_token.pop(session.token_digest, None)
        for digest, grant in list(self._grants.items()):
            if grant.session_id == session.session_id:
                self._grants.pop(digest, None)
        self._audit(
            "session_disconnected",
            session_id=session.session_id[:10],
            role=session.role,
            client_name=session.client_name,
            ip=mask_ip(session.ip),
            reason=_safe_name(reason, 80),
        )

    def _session_summary_locked(self, session: Session, now: float) -> dict:
        return {
            "session_id": session.session_id,
            "client_name": session.client_name,
            "role": session.role,
            "ip": mask_ip(session.ip),
            "age_seconds": max(0, int(now - session.created_at)),
            "idle_seconds": max(0, int(now - session.last_seen_at)),
            "idle_expires_in": max(0, int(session.idle_expires_at - now)),
            "absolute_expires_in": max(0, int(session.absolute_expires_at - now)),
        }

    def list_sessions(self) -> list[dict]:
        now = self._now()
        with self._lock:
            self.sweep(now=now)
            active = self._active_sessions_locked(now)
            return [
                self._session_summary_locked(session, now)
                for session in sorted(active, key=lambda row: row.created_at)
            ]

    def sweep(self, *, now: float | None = None) -> dict:
        current = self._now() if now is None else float(now)
        expired_pairs: list[str] = []
        expired_sessions: list[str] = []
        expired_grants = 0
        with self._lock:
            for request_id, item in list(self._pending.items()):
                if current >= item.expires_at:
                    expired_pairs.append(request_id)
                    self._pending.pop(request_id, None)
            for session in list(self._sessions.values()):
                if session.disconnected:
                    continue
                if current >= session.idle_expires_at or current >= session.absolute_expires_at:
                    expired_sessions.append(session.session_id)
                    self._disconnect_locked(session, "SESSION_EXPIRED")
            for digest, grant in list(self._grants.items()):
                if current >= grant.expires_at:
                    expired_grants += 1
                    self._grants.pop(digest, None)
        return {
            "expired_pairs": expired_pairs,
            "expired_sessions": expired_sessions,
            "expired_grants": expired_grants,
        }
