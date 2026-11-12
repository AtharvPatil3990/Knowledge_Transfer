from pydantic import BaseModel, Field


class GitHubSyncRequest(BaseModel):
    repository: str = Field(
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
        description="GitHub repository in owner/name format.",
    )
    state: str = Field(default="open", pattern=r"^(open|closed|all)$")
    limit: int = Field(default=20, ge=1, le=100)
