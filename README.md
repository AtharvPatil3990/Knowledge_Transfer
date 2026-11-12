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

The script enables `pgcrypto` and `vector`. The embedding column is currently
`vector(1536)`; change that dimension if the selected embedding model uses a
different output size.

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