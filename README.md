# Knowledge Handover

## Database setup

The Supabase database design is in [`supabase/schema.sql`](./supabase/schema.sql).
Run it in the Supabase SQL Editor on a new project.

The schema provides:

- Teams, members, roles, and clearance levels
- Source ingestion and traceable tasks/decisions
- Versioned handover drafts and evidence-backed handover items
- Lead review, approval, rejection, and audit records
- `pgvector` embeddings restricted to approved content
- Row Level Security for team membership, roles, and clearance

The script enables `pgcrypto` and `vector`. The embedding column is currently `vector(384)` for the local
`BAAI/bge-small-en-v1.5` model through FastEmbed.

When a signed-in user creates a team, a database trigger automatically creates
that user as an `ADMIN` team member with clearance level 5.

## Authentication flow

The API uses Supabase Auth. The frontend sends the returned access token with
every protected request:

```http
Authorization: Bearer <access_token>
```

Available endpoints:

- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`

`get_authenticated_user` validates the bearer token with Supabase Auth on every
request. Expired, malformed, or revoked tokens receive `401 Unauthorized`.
Use it in a route with `user: CurrentUser`.

For team authorization, use `require_team_member(team_id)` or
`require_team_roles("ADMIN", "LEAD")`. These dependencies query `team_members`
using the same bearer token, so Supabase RLS remains active. Authentication
proves who the user is; team membership, role, and clearance prove what they
may access.

```python
@router.post("/teams/{team_id}/handover")
def create_handover(
    team_id: UUID,
    member=Depends(require_team_roles("ADMIN", "LEAD")),
):
    return {"created_by": member["user_id"], "team_id": team_id}
```

## Team endpoints

The first protected resource flow is implemented in
[`app/api/teams.py`](./app/api/teams.py):

- `POST /teams` — create a team; the database trigger adds the creator as an
  `ADMIN`
- `GET /teams` — list teams for the signed-in user
- `GET /teams/{team_id}` — view a team after membership validation
- `GET /teams/{team_id}/members` — list members after membership validation
- `POST /teams/{team_id}/members` — add a member; requires `ADMIN` or `LEAD`

Use the Supabase Auth user's UUID as `auth_user_id` when adding an existing
user. The endpoint does not accept a password or create Auth users.

If team creation returns `new row violates row-level security policy for table
"teams"`, run [`supabase/fix_team_creation.sql`](./supabase/fix_team_creation.sql)
in the Supabase SQL Editor. The API creates teams through the authenticated
`create_team` RPC, which assigns ownership from `auth.uid()` and lets the
database trigger create the initial `ADMIN` member atomically.

## Knowledge endpoints

The ingestion and normalized knowledge endpoints are implemented in
[`app/api/knowledge.py`](./app/api/knowledge.py). All routes require a bearer
token and team membership.

- `POST /teams/{team_id}/sources` — store or update a raw source document;
  requires `ADMIN` or `LEAD`
- `GET /teams/{team_id}/sources` — list source documents
- `POST /teams/{team_id}/tasks` — create a normalized task
- `GET /teams/{team_id}/tasks` — list tasks, optionally filtered by `status`
- `GET /teams/{team_id}/tasks/{task_id}` — get a task
- `PATCH /teams/{team_id}/tasks/{task_id}` — update a task
- `DELETE /teams/{team_id}/tasks/{task_id}` — delete a task
- `POST /teams/{team_id}/decisions` — create a normalized decision
- `GET /teams/{team_id}/decisions` — list decisions
- `GET /teams/{team_id}/decisions/{decision_id}` — get a decision
- `PATCH /teams/{team_id}/decisions/{decision_id}` — update a decision
- `DELETE /teams/{team_id}/decisions/{decision_id}` — delete a decision

The source endpoint is the connector boundary: GitHub/Jira adapters should
write raw data there first, then the LangChain extraction worker should create
tasks and decisions with the returned `source_document_id`.

### GitHub connector

GitHub pull requests can be synchronized into `source_documents` with:

```http
POST /teams/{team_id}/sources/github/sync
Authorization: Bearer <admin_or_lead_access_token>
Content-Type: application/json
```

```json
{
  "repository": "owner/repository",
  "state": "open",
  "limit": 20
}
```

Set `GITHUB_TOKEN` in the backend `.env` for private repositories or higher
rate limits. Never send that token from the frontend. The connector stores the
pull request description and issue comments as one traceable GitHub source
document; LangChain processing can consume those documents afterward.

## Vectorization

Before vectorizing source documents, run
[`supabase/fix_source_embeddings.sql`](./supabase/fix_source_embeddings.sql)
against an existing database. It allows embeddings to reference a
`source_document_id` before a handover item exists.

The MVP uses a local embedding model, so no OpenAI key is required. Configure
the backend optionally:

```env
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

Then call:

```http
POST /teams/{team_id}/sources/{source_id}/vectorize
Authorization: Bearer <admin_or_lead_access_token>
```

The endpoint normalizes and chunks the source content, creates
384-dimensional FastEmbed embeddings, deletes older chunks for that source, and
stores the replacements in `knowledge_embeddings`. New vectors are
`is_approved = false`; they are not visible to the RAG search policy until a
reviewed handover approves them.

For an existing database, run
[`supabase/migrate_local_embeddings.sql`](./supabase/migrate_local_embeddings.sql)
before vectorizing. It removes only derived vectors and changes the pgvector
column from 1536 to 384 dimensions. Source documents remain intact and can be
embedded again.