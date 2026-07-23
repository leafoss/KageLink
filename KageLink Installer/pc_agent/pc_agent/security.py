from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Query, status


class TokenSecurity:
    def __init__(self, token: str) -> None:
        if not token or len(token) < 16:
            raise ValueError("Defina um access_token com pelo menos 16 caracteres em config.json.")
        self.token = token

    def valid(self, candidate: str | None) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate, self.token)

    def require_authorization(self, authorization: str | None = Header(default=None)) -> None:
        prefix = "Bearer "
        candidate = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else None
        if not self.valid(candidate):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido.",
            )

    def require_websocket(self, token: str | None = Query(default=None)) -> None:
        if not self.valid(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido.",
            )
