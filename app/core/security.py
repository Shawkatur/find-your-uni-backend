"""
JWT verification via Supabase-issued tokens.
Supabase signs JWTs with HS256 using SUPABASE_JWT_SECRET.
"""
from typing import Annotated
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

bearer_scheme = HTTPBearer()


def verify_token(token: str) -> dict:
    """Decode and verify a Supabase JWT. Returns the payload dict."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> dict:
    """FastAPI dependency — returns the JWT payload for the authenticated user."""
    return verify_token(credentials.credentials)


def require_role(role: str):
    """
    Dependency factory: require the JWT to carry a specific app_metadata.role.
    Usage:  Depends(require_role("consultant"))
    """
    def _check(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        user_role = (user.get("app_metadata") or {}).get("role", "student")
        if user_role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{role}', got '{user_role}'",
            )
        return user
    return _check
