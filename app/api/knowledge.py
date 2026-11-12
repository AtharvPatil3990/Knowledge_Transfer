from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import require_team_member, require_team_roles
from app.db.supabase_client import get_supabase_client
from app.models.schema import (
    DecisionCreate,
    DecisionUpdate,
    SourceDocumentCreate,
    TaskCreate,
    TaskUpdate,
)

router = APIRouter(prefix="/teams/{team_id}", tags=["Knowledge"])


def _client_for(member: dict):
    client = get_supabase_client()
    client.postgrest.auth(member["access_token"])
    return client


def _raise_if_empty(data, detail: str):
    if not data:
        raise HTTPException(status_code=404, detail=detail)
    return data[0] if isinstance(data, list) else data


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def ingest_source(
    team_id: UUID,
    payload: SourceDocumentCreate,
    member=Depends(require_team_roles("ADMIN", "LEAD")),
):
    data = {
        "team_id": str(team_id),
        "source_platform": payload.source_platform.value,
        "source_id": payload.source_id,
        "source_url": payload.source_url,
        "title": payload.title,
        "content": payload.content,
        "metadata": payload.metadata,
        "ingested_by": member["user_id"],
    }
    result = _client_for(member).table("source_documents").upsert(
        data, on_conflict="team_id,source_platform,source_id"
    ).execute()
    return _raise_if_empty(result.data, "Source document could not be stored.")


@router.get("/sources")
def list_sources(
    team_id: UUID,
    member=Depends(require_team_member),
    source_platform: str | None = Query(default=None),
):
    query = (
        _client_for(member)
        .table("source_documents")
        .select("*")
        .eq("team_id", str(team_id))
        .order("created_at", desc=True)
    )
    if source_platform:
        query = query.eq("source_platform", source_platform.upper())
    return query.execute().data


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    team_id: UUID,
    payload: TaskCreate,
    member=Depends(require_team_roles("ADMIN", "LEAD", "DEVELOPER")),
):
    data = payload.model_dump(mode="json", exclude_none=True)
    data.update({
        "team_id": str(team_id),
        "source_platform": payload.source_platform.value,
        "status": payload.status.value,
    })
    if payload.source_document_id:
        data["source_document_id"] = str(payload.source_document_id)
    result = _client_for(member).table("tasks").insert(data).execute()
    return _raise_if_empty(result.data, "Task could not be created.")


@router.get("/tasks")
def list_tasks(
    team_id: UUID,
    member=Depends(require_team_member),
    task_status: str | None = Query(default=None, alias="status"),
):
    query = (
        _client_for(member).table("tasks").select("*")
        .eq("team_id", str(team_id)).order("created_at", desc=True)
    )
    if task_status:
        query = query.eq("status", task_status.upper())
    return query.execute().data


@router.get("/tasks/{task_id}")
def get_task(team_id: UUID, task_id: UUID, member=Depends(require_team_member)):
    result = (
        _client_for(member).table("tasks").select("*")
        .eq("team_id", str(team_id)).eq("id", str(task_id)).execute()
    )
    return _raise_if_empty(result.data, "Task not found.")


@router.patch("/tasks/{task_id}")
def update_task(
    team_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    member=Depends(require_team_roles("ADMIN", "LEAD", "DEVELOPER")),
):
    data = payload.model_dump(mode="json", exclude_none=True)
    if "status" in data:
        data["status"] = payload.status.value
    result = (
        _client_for(member).table("tasks").update(data)
        .eq("team_id", str(team_id)).eq("id", str(task_id)).execute()
    )
    return _raise_if_empty(result.data, "Task not found.")


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    team_id: UUID,
    task_id: UUID,
    member=Depends(require_team_roles("ADMIN", "LEAD", "DEVELOPER")),
):
    _client_for(member).table("tasks").delete().eq(
        "team_id", str(team_id)
    ).eq("id", str(task_id)).execute()


@router.post("/decisions", status_code=status.HTTP_201_CREATED)
def create_decision(
    team_id: UUID,
    payload: DecisionCreate,
    member=Depends(require_team_roles("ADMIN", "LEAD", "DEVELOPER")),
):
    data = payload.model_dump(mode="json", exclude_none=True)
    data.update({
        "team_id": str(team_id),
        "decision_type": payload.decision_type.value,
    })
    for field in ("source_document_id",):
        if field in data:
            data[field] = str(data[field])
    result = _client_for(member).table("decisions").insert(data).execute()
    return _raise_if_empty(result.data, "Decision could not be created.")


@router.get("/decisions")
def list_decisions(team_id: UUID, member=Depends(require_team_member)):
    return (
        _client_for(member).table("decisions").select("*")
        .eq("team_id", str(team_id)).order("created_at", desc=True)
        .execute().data
    )


@router.get("/decisions/{decision_id}")
def get_decision(
    team_id: UUID,
    decision_id: UUID,
    member=Depends(require_team_member),
):
    result = (
        _client_for(member).table("decisions").select("*")
        .eq("team_id", str(team_id)).eq("id", str(decision_id)).execute()
    )
    return _raise_if_empty(result.data, "Decision not found.")


@router.patch("/decisions/{decision_id}")
def update_decision(
    team_id: UUID,
    decision_id: UUID,
    payload: DecisionUpdate,
    member=Depends(require_team_roles("ADMIN", "LEAD", "DEVELOPER")),
):
    data = payload.model_dump(mode="json", exclude_none=True)
    if "decision_type" in data:
        data["decision_type"] = payload.decision_type.value
    result = (
        _client_for(member).table("decisions").update(data)
        .eq("team_id", str(team_id)).eq("id", str(decision_id)).execute()
    )
    return _raise_if_empty(result.data, "Decision not found.")


@router.delete("/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(
    team_id: UUID,
    decision_id: UUID,
    member=Depends(require_team_roles("ADMIN", "LEAD", "DEVELOPER")),
):
    _client_for(member).table("decisions").delete().eq(
        "team_id", str(team_id)
    ).eq("id", str(decision_id)).execute()
