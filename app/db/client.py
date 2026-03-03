"""
Supabase async client — singleton pattern.
Always use the service-role key on the backend so RLS bypasses work for
admin operations; individual RLS enforcement happens via Postgres policies
checked against the JWT sub (user_id) in SQL filters.
"""
from functools import lru_cache
from supabase import AsyncClient, acreate_client

from app.core.config import get_settings

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    """Return (and lazily initialise) the global Supabase async client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = await acreate_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _client


async def get_user_client(access_token: str) -> AsyncClient:
    """
    Return a Supabase client scoped to the user's JWT.
    Use this when you want Postgres RLS to enforce per-user policies.
    """
    settings = get_settings()
    client = await acreate_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    await client.auth.set_session(access_token, "")
    return client
