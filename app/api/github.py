import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import require_team_roles
from app.db.supabase_client import get_supabase_client
from app.models.schema import GitHubTokenExchangeRequest

router = APIRouter(prefix="/github", tags=["GitHub"])


@router.post("/exchange")
async def exchange_github_token(
    payload: GitHubTokenExchangeRequest,
    member=Depends(require_team_roles("ADMIN", "LEAD")),
):
    """Exchange a temporary GitHub OAuth code and store the team token."""
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth credentials are not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": payload.code,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub OAuth returned HTTP {error.response.status_code}.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub OAuth could not be reached.",
        ) from error

    try:
        github_response = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub OAuth returned an invalid response.",
        ) from error

    if not isinstance(github_response, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub OAuth returned an unexpected response.",
        )

    access_token = github_response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=github_response.get(
                "error_description",
                "GitHub OAuth did not return an access token.",
            ),
        )

    client = get_supabase_client()
    client.postgrest.auth(member["access_token"])
    result = (
        client.table("teams")
        .update({"github_access_token": access_token})
        .eq("id", str(payload.team_id))
        .select("id")
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub access token could not be stored for the team.",
        )

    return {"team_id": str(payload.team_id), "connected": True}
