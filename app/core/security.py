import logging
from typing import Annotated, Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
token_auth_scheme = HTTPBearer(auto_error=True)


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(token_auth_scheme),
) -> dict[str, str | None]:
    """Validate the bearer token with Supabase Auth."""
    token = credentials.credentials
    scoped_client: Client = get_supabase_client()

    try:
        user_response = scoped_client.auth.get_user(token)
        if not user_response.user:
            raise ValueError("Token parsed but user object is null.")
    except Exception as error:
        logger.warning("Supabase rejected the bearer token.", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return {
        "user_id": str(user_response.user.id),
        "email": user_response.user.email,
        "role": user_response.user.role,
        "access_token": token,
    }


CurrentUser = Annotated[dict[str, str | None], Depends(get_authenticated_user)]


def require_team_member(
    team_id: UUID,
    user: CurrentUser,
) -> dict[str, str | None]:
    """Require that the authenticated user belongs to the requested team."""
    client = get_supabase_client()
    client.postgrest.auth(user["access_token"])
    result = (
        client.table("team_members")
        .select("id, role, clearance_level")
        .eq("team_id", str(team_id))
        .eq("auth_user_id", user["user_id"])
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team.",
        )

    return {
        **user,
        "team_member_id": result.data["id"],
        "team_role": result.data["role"],
        "clearance_level": result.data["clearance_level"],
    }


def require_team_roles(*allowed_roles: str) -> Callable:
    """Return a dependency enforcing membership and one of the given roles."""
    def dependency(
        team_id: UUID,
        user: CurrentUser,
    ) -> dict[str, str | None]:
        member = require_team_member(team_id, user)
        if member["team_role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission for this team operation.",
            )
        return member

    return dependency
