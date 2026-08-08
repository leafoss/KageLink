from __future__ import annotations

import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROTOTYPE_ROOT = HERE.parent
if str(PROTOTYPE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_ROOT))

from security import SecurityError, SessionAuthority, SlidingWindowLimiter


class FakeClock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class SessionAuthorityTests(unittest.TestCase):
    def make_authority(self, *, clock: FakeClock | None = None, audit=None) -> SessionAuthority:
        return SessionAuthority(
            pair_ttl_seconds=30,
            session_idle_ttl_seconds=60,
            session_absolute_ttl_seconds=180,
            peer_grant_ttl_seconds=10,
            max_sessions=4,
            audit=audit,
            clock=clock,
        )

    def pair_and_approve(
        self,
        authority: SessionAuthority,
        *,
        ip: str = "192.168.1.20",
        role: str = "control",
        nonce: str = "nonce-1234567890-abcdef",
        client_name: str = "Test Browser",
    ) -> dict:
        request = authority.request_pair(
            ip=ip,
            client_name=client_name,
            user_agent="UnitTest/1.0",
            requested_role=role,
            client_nonce=nonce,
        )
        authority.approve(request.request_id, role=role)
        return authority.poll_pair(
            ip=ip,
            request_id=request.request_id,
            client_nonce=nonce,
        )

    def test_pair_request_requires_strong_nonce(self) -> None:
        authority = self.make_authority()
        with self.assertRaisesRegex(SecurityError, "INVALID_CLIENT_NONCE"):
            authority.request_pair(
                ip="192.168.1.20",
                client_name="Browser",
                user_agent="UnitTest",
                requested_role="control",
                client_nonce="short",
            )

    def test_approved_pair_delivers_memory_session_once(self) -> None:
        authority = self.make_authority()
        nonce = "nonce-1234567890-abcdef"
        request = authority.request_pair(
            ip="192.168.1.20",
            client_name="Browser",
            user_agent="UnitTest",
            requested_role="control",
            client_nonce=nonce,
        )
        authority.approve(request.request_id)
        result = authority.poll_pair(
            ip="192.168.1.20",
            request_id=request.request_id,
            client_nonce=nonce,
        )
        self.assertEqual("approved", result["status"])
        self.assertEqual("control", result["role"])
        self.assertGreater(len(result["session_token"]), 20)
        with self.assertRaisesRegex(SecurityError, "PAIR_REQUEST_NOT_FOUND"):
            authority.poll_pair(
                ip="192.168.1.20",
                request_id=request.request_id,
                client_nonce=nonce,
            )

    def test_pair_poll_is_bound_to_ip_and_nonce(self) -> None:
        authority = self.make_authority()
        nonce = "nonce-1234567890-abcdef"
        request = authority.request_pair(
            ip="192.168.1.20",
            client_name="Browser",
            user_agent="UnitTest",
            requested_role="view",
            client_nonce=nonce,
        )
        with self.assertRaisesRegex(SecurityError, "PAIR_REQUEST_NOT_FOUND"):
            authority.poll_pair(
                ip="192.168.1.21",
                request_id=request.request_id,
                client_nonce=nonce,
            )
        with self.assertRaisesRegex(SecurityError, "PAIR_REQUEST_NOT_FOUND"):
            authority.poll_pair(
                ip="192.168.1.20",
                request_id=request.request_id,
                client_nonce="nonce-wrong-1234567890",
            )

    def test_only_one_controller_but_view_session_can_coexist(self) -> None:
        authority = self.make_authority()
        self.pair_and_approve(authority, ip="192.168.1.20", role="control")

        second = authority.request_pair(
            ip="192.168.1.21",
            client_name="Second",
            user_agent="UnitTest",
            requested_role="control",
            client_nonce="nonce-second-1234567890",
        )
        with self.assertRaisesRegex(SecurityError, "CONTROLLER_BUSY"):
            authority.approve(second.request_id, role="control")

        viewer = self.pair_and_approve(
            authority,
            ip="192.168.1.22",
            role="view",
            nonce="nonce-viewer-1234567890",
            client_name="Viewer",
        )
        self.assertEqual("view", viewer["role"])
        self.assertEqual(2, len(authority.list_sessions()))

    def test_session_token_is_bound_to_original_ip(self) -> None:
        authority = self.make_authority()
        approved = self.pair_and_approve(authority)
        token = approved["session_token"]
        session = authority.validate_session(token, ip="192.168.1.20")
        self.assertEqual("control", session.role)
        with self.assertRaisesRegex(SecurityError, "INVALID_SESSION"):
            authority.validate_session(token, ip="192.168.1.99")

    def test_view_session_cannot_be_validated_as_control(self) -> None:
        authority = self.make_authority()
        approved = self.pair_and_approve(authority, role="view")
        with self.assertRaisesRegex(SecurityError, "CONTROL_NOT_GRANTED"):
            authority.validate_session(
                approved["session_token"],
                ip="192.168.1.20",
                require_control=True,
            )

    def test_peer_grant_is_single_use_and_ip_bound(self) -> None:
        authority = self.make_authority()
        approved = self.pair_and_approve(authority)
        grant = authority.issue_peer_grant(approved["session_token"], ip="192.168.1.20")
        consumed = authority.consume_peer_grant(grant["peer_grant"], ip="192.168.1.20")
        self.assertEqual("control", consumed.role)
        with self.assertRaisesRegex(SecurityError, "INVALID_PEER_GRANT"):
            authority.consume_peer_grant(grant["peer_grant"], ip="192.168.1.20")

        second = authority.issue_peer_grant(approved["session_token"], ip="192.168.1.20")
        with self.assertRaisesRegex(SecurityError, "INVALID_PEER_GRANT"):
            authority.consume_peer_grant(second["peer_grant"], ip="192.168.1.21")

    def test_idle_session_expires_and_is_revoked(self) -> None:
        clock = FakeClock()
        authority = self.make_authority(clock=clock)
        approved = self.pair_and_approve(authority)
        token = approved["session_token"]
        clock.advance(61)
        with self.assertRaisesRegex(SecurityError, "INVALID_SESSION|SESSION_EXPIRED"):
            authority.validate_session(token, ip="192.168.1.20")
        self.assertEqual([], authority.list_sessions())

    def test_disconnect_all_revokes_every_active_token(self) -> None:
        authority = self.make_authority()
        controller = self.pair_and_approve(authority, ip="192.168.1.20")
        viewer = self.pair_and_approve(
            authority,
            ip="192.168.1.21",
            role="view",
            nonce="nonce-viewer-1234567890",
        )
        revoked = authority.disconnect_all(reason="UNIT_TEST_STOP")
        self.assertEqual(2, len(revoked))
        for token, ip in (
            (controller["session_token"], "192.168.1.20"),
            (viewer["session_token"], "192.168.1.21"),
        ):
            with self.assertRaisesRegex(SecurityError, "INVALID_SESSION"):
                authority.validate_session(token, ip=ip)

    def test_rate_limiter_rejects_burst(self) -> None:
        limiter = SlidingWindowLimiter()
        for _ in range(3):
            limiter.hit("same-client", limit=3, window_seconds=10, now=100.0)
        with self.assertRaisesRegex(SecurityError, "RATE_LIMITED") as raised:
            limiter.hit("same-client", limit=3, window_seconds=10, now=100.0)
        self.assertGreaterEqual(raised.exception.retry_after or 0, 1)

    def test_audit_hook_never_receives_session_secrets(self) -> None:
        events: list[tuple[str, dict]] = []
        authority = self.make_authority(audit=lambda event, payload: events.append((event, payload)))
        approved = self.pair_and_approve(authority)
        grant = authority.issue_peer_grant(approved["session_token"], ip="192.168.1.20")
        authority.consume_peer_grant(grant["peer_grant"], ip="192.168.1.20")
        forbidden = {"token", "session_token", "peer_grant", "client_nonce", "text", "key"}
        self.assertTrue(events)
        for _, payload in events:
            self.assertTrue(forbidden.isdisjoint(payload.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
