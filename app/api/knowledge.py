from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import require_team_member, require_team_roles
from app.connectors.github import GitHubConnector
from app.core.config import settings
from app.db.supabase_client import get_supabase_client
from app.models.connectors import GitHubSyncRequest
from app.services.embeddings import EmbeddingService, chunk_text
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


@router.post("/sources/{source_id}/vectorize")
def vectorize_source(
    team_id: UUID,
    source_id: UUID,
    member=Depends(require_team_roles("ADMIN", "LEAD")),
):
    """Create clearance-filtered, searchable chunks for one source document."""
    client = _client_for(member)
    source_result = (
        client.table("source_documents")
        .select("id, source_url, title, content, metadata")
        .eq("id", str(source_id))
        .eq("team_id", str(team_id))
        .maybe_single()
        .execute()
    )
    source = source_result.data
    if not source:
        raise HTTPException(status_code=404, detail="Source document not found.")
    if not source.get("content"):
        raise HTTPException(
            status_code=422,
            detail="Source document has no content to vectorize.",
        )

    chunks = chunk_text(source["content"])
    try:
        vectors = EmbeddingService(
        ).embed(chunks)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Embedding provider failed while vectorizing the source.",
        ) from error

    client.table("knowledge_embeddings").delete().eq(
        "team_id", str(team_id)
    ).eq("source_document_id", str(source_id)).execute()

    rows = [
        {
            "team_id": str(team_id),
            "source_document_id": str(source_id),
            "content": chunk.content,
            "embedding": vector,
            "source_url": source["source_url"],
            "required_clearance": 1,
            "is_approved": False,
            "metadata": {
                **(source.get("metadata") or {}),
                "source_title": source.get("title"),
                "chunk_index": chunk.index,
                "embedding_model": settings.EMBEDDING_MODEL,
                "embedding_dimension": len(vector),
            },
        }
        for chunk, vector in zip(chunks, vectors)
    ]
    if rows:
        client.table("knowledge_embeddings").insert(rows).execute()

    return {
        "source_document_id": str(source_id),
        "chunks_created": len(rows),
        "embedding_model": settings.EMBEDDING_MODEL,
        "approved": False,
    }


@router.post("/sources/github/sync")
def sync_github(
    team_id: UUID,
    payload: GitHubSyncRequest,
    member=Depends(require_team_roles("ADMIN", "LEAD")),
):
    """Fetch GitHub pull requests and upsert them as raw source documents."""
    try:
        documents = GitHubConnector(token=settings.GITHUB_TOKEN).fetch(
            repository=payload.repository,
            state=payload.state,
            limit=payload.limit,
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API returned HTTP {error.response.status_code}.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail="GitHub could not be reached.",
        ) from error

    client = _client_for(member)
    stored = []
    for document in documents:
        result = client.table("source_documents").upsert({
            "team_id": str(team_id),
            "source_platform": "GITHUB",
            "source_id": document["source_id"],
            "source_url": document["source_url"],
            "title": document["title"],
            "content": document["content"],
            "metadata": document["metadata"],
            "ingested_by": member["user_id"],
        }, on_conflict="team_id,source_platform,source_id").execute()
        stored.extend(result.data or [])

    return {
        "repository": payload.repository,
        "fetched": len(documents),
        "stored": len(stored),
        "documents": stored,
    }


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
