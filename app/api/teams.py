from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import CurrentUser, require_team_member, require_team_roles
from app.db.supabase_client import get_supabase_client
from app.models.schema import TeamBase, TeamMemberCreate

router = APIRouter(prefix="/teams", tags=["Teams"])


def _client_for(user: dict[str, str | None]):
    client = get_supabase_client()
    client.postgrest.auth(user["access_token"])
    return client


@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamBase, user: CurrentUser):
    result = _client_for(user).rpc("create_team", {
        "p_name": payload.name,
        "p_description": payload.description,
    }).execute()
    if not result.data:
        raise HTTPException(status_code=502, detail="Team could not be created.")
    return result.data[0] if isinstance(result.data, list) else result.data


@router.get("/list")
def list_my_teams(user: CurrentUser):
    result = (
        _client_for(user)
        .table("team_members")
        .select("team_id, role, clearance_level, teams(id, name, description, created_at)")
        .eq("auth_user_id", user["user_id"])
        .execute()
    )
    return result.data


@router.get("/get/{team_id}")
def get_team(team_id: UUID, member=Depends(require_team_member)):
    result = (
        _client_for(member)
        .table("teams")
        .select("id, name, description, created_by, created_at, updated_at")
        .eq("id", str(team_id))
        .single()
        .execute()
    )
    return result.data


@router.get("/{team_id}/members")
def list_members(team_id: UUID, member=Depends(require_team_member)):
    result = (
        _client_for(member)
        .table("team_members")
        .select("id, auth_user_id, name, role, clearance_level, created_at")
        .eq("team_id", str(team_id))
        .order("created_at")
        .execute()
    )
    return result.data


@router.post("/{team_id}/add_member", status_code=status.HTTP_201_CREATED)
def add_member(
    team_id: UUID,
    payload: TeamMemberCreate,
    member=Depends(require_team_roles("ADMIN", "LEAD")),
):
    result = _client_for(member).table("team_members").insert({
        "team_id": str(team_id),
        "auth_user_id": str(payload.auth_user_id),
        "name": payload.name,
        "role": payload.role.value,
        "clearance_level": payload.clearance_level,
    }).execute()
    if not result.data:
        raise HTTPException(status_code=502, detail="Team member could not be added.")
    return result.data[0]
