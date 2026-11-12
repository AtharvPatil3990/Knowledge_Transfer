from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from enum import Enum
from datetime import datetime
from uuid import UUID

# ------------------------------------------------------------------------
# 1. Enums (Mapping exactly to PostgreSQL custom types)
# ------------------------------------------------------------------------
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    LEAD = "LEAD"
    DEVELOPER = "DEVELOPER"
    VIEWER = "VIEWER"

class PlatformSource(str, Enum):
    GITHUB = "GITHUB"
    JIRA = "JIRA"
    WEBHOOK = "WEBHOOK"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"

class TaskStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CLOSED = "CLOSED"

class DecisionCategory(str, Enum):
    ARCHITECTURE = "ARCHITECTURE"
    TRADE_OFF = "TRADE_OFF"
    BLOCKER = "BLOCKER"

class TaskAssignment(str, Enum):
    ASSIGNEE = "ASSIGNEE"
    REVIEWER = "REVIEWER"
    REPORTER = "REPORTER"

# ------------------------------------------------------------------------
# 2. Base Models & Schemas
# ------------------------------------------------------------------------

class TeamBase(BaseModel):
    name: str = Field(..., description="The name of the project team.")
    description: Optional[str] = None

class TeamMemberBase(BaseModel):
    name: str = Field(..., description="Full name of the team member.")
    role: UserRole = Field(default=UserRole.DEVELOPER)
    clearance_level: int = Field(default=1, description="Clearance level for the Role-Based Authorization Filter.")

class TeamMemberCreate(TeamMemberBase):
    auth_user_id: UUID

class TaskBase(BaseModel):
    source_platform: PlatformSource
    source_id: str = Field(..., description="The original ID from the source platform (e.g., PR-42 or JIRA-101).")
    source_url: str = Field(..., min_length=1, description="The direct URL to the task for 100% traceability.")
    title: str
    status: TaskStatus
    description: Optional[str] = None

class DecisionBase(BaseModel):
    decision_type: DecisionCategory
    summary: str = Field(..., description="A concise summary of the architectural trade-off or blocker.")
    confidence_score: Optional[float] = Field(None, description="AI confidence score for the extracted decision.")
    is_uncertain: bool = Field(default=False, description="Flagged true if conflicting information is found in the sources.")
    source_url: str = Field(..., min_length=1, description="The URL of the chat thread or PR comment where the decision was made.")

class SourceDocumentCreate(BaseModel):
    source_platform: PlatformSource
    source_id: str = Field(min_length=1)
    source_url: str
    title: Optional[str] = None
    content: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

class TaskCreate(TaskBase):
    source_document_id: Optional[UUID] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    due_at: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    status: Optional[TaskStatus] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    due_at: Optional[datetime] = None

class DecisionCreate(DecisionBase):
    source_document_id: Optional[UUID] = None
    rationale: Optional[str] = None
    uncertainty_reason: Optional[str] = None

class DecisionUpdate(BaseModel):
    decision_type: Optional[DecisionCategory] = None
    summary: Optional[str] = Field(default=None, min_length=1)
    rationale: Optional[str] = None
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    is_uncertain: Optional[bool] = None
    uncertainty_reason: Optional[str] = None

# ------------------------------------------------------------------------
# 3. Extraction Schemas (Specifically for LangChain Output Parsers)
# ------------------------------------------------------------------------
# When orchestrating the LLM to analyze a noisy PR thread, pass this model 
# to LangChain's with_structured_output() to enforce the schema.

class ExtractedDecision(DecisionBase):
    """Schema used by the LLM Discussion Analyzer to output structured JSON."""
    related_task_ids: List[str] = Field(
        default_factory=list, 
        description="A list of source_ids (like JIRA-102) that this decision impacts."
    )

# ------------------------------------------------------------------------
# 4. Database Response Models (Include UUIDs and Timestamps)
# ------------------------------------------------------------------------
class DBModel(BaseModel):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True) # Allows parsing directly from Supabase dict responses

class TaskResponse(TaskBase, DBModel):
    team_id: UUID

class DecisionResponse(DecisionBase, DBModel):
    team_id: UUID