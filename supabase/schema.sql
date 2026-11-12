-- Knowledge Handover
-- Supabase/PostgreSQL schema
--
-- Run this in the Supabase SQL editor on a new project. The statements are
-- intentionally idempotent where practical so the file can also be used as a
-- migration foundation.

create extension if not exists pgcrypto;
create extension if not exists vector;

do $$ begin
  create type public.user_role as enum ('ADMIN', 'LEAD', 'DEVELOPER', 'VIEWER');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.source_platform as enum ('GITHUB', 'JIRA', 'WEBHOOK', 'MANUAL_UPLOAD');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.source_document_status as enum ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.task_status as enum ('OPEN', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'CLOSED');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.decision_type as enum ('ARCHITECTURE', 'TRADE_OFF', 'BLOCKER');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.task_assignment as enum ('ASSIGNEE', 'REVIEWER', 'REPORTER');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.handover_status as enum ('DRAFT', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'ARCHIVED');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.review_status as enum ('PENDING', 'APPROVED', 'REJECTED', 'CHANGES_REQUESTED');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.knowledge_item_type as enum ('SUMMARY', 'TASK', 'DECISION', 'RISK', 'DEPENDENCY', 'QUESTION', 'NEXT_ACTION');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.audit_action as enum ('CREATED', 'UPDATED', 'DELETED', 'VIEWED', 'APPROVED', 'REJECTED', 'EXPORTED');
exception when duplicate_object then null;
end $$;

create table if not exists public.teams (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) > 0),
  description text,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.team_members (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  auth_user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (length(trim(name)) > 0),
  role public.user_role not null default 'DEVELOPER',
  clearance_level smallint not null default 1 check (clearance_level between 1 and 5),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (team_id, auth_user_id)
);

create table if not exists public.source_documents (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  source_platform public.source_platform not null,
  source_id text not null,
  source_url text not null,
  title text,
  content text,
  metadata jsonb not null default '{}'::jsonb,
  status public.source_document_status not null default 'PENDING',
  error_message text,
  ingested_by uuid references auth.users(id) on delete set null,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (team_id, source_platform, source_id)
);

create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  source_document_id uuid references public.source_documents(id) on delete set null,
  source_platform public.source_platform not null,
  source_id text not null,
  source_url text not null,
  title text not null check (length(trim(title)) > 0),
  status public.task_status not null default 'OPEN',
  description text,
  priority smallint check (priority between 1 and 5),
  due_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (team_id, source_platform, source_id)
);

create table if not exists public.decisions (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  source_document_id uuid references public.source_documents(id) on delete set null,
  decision_type public.decision_type not null,
  summary text not null,
  rationale text,
  confidence_score double precision check (confidence_score between 0 and 1),
  is_uncertain boolean not null default false,
  uncertainty_reason text,
  source_url text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (not is_uncertain or uncertainty_reason is not null)
);

create table if not exists public.member_tasks (
  member_id uuid not null references public.team_members(id) on delete cascade,
  task_id uuid not null references public.tasks(id) on delete cascade,
  assignment_type public.task_assignment not null default 'ASSIGNEE',
  created_at timestamptz not null default now(),
  primary key (member_id, task_id, assignment_type)
);

create table if not exists public.task_decisions (
  task_id uuid not null references public.tasks(id) on delete cascade,
  decision_id uuid not null references public.decisions(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (task_id, decision_id)
);

create table if not exists public.member_decisions (
  member_id uuid not null references public.team_members(id) on delete cascade,
  decision_id uuid not null references public.decisions(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (member_id, decision_id)
);

create table if not exists public.handover_drafts (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  version integer not null default 1 check (version > 0),
  status public.handover_status not null default 'DRAFT',
  title text not null default 'Project handover',
  summary text,
  generated_by uuid references auth.users(id) on delete set null,
  approved_by uuid references auth.users(id) on delete set null,
  approved_at timestamptz,
  rejection_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (team_id, version),
  check ((status = 'APPROVED') = (approved_at is not null and approved_by is not null))
);

create table if not exists public.handover_items (
  id uuid primary key default gen_random_uuid(),
  handover_id uuid not null references public.handover_drafts(id) on delete cascade,
  item_type public.knowledge_item_type not null,
  title text not null,
  content text not null,
  source_url text,
  source_document_id uuid references public.source_documents(id) on delete set null,
  confidence_score double precision check (confidence_score between 0 and 1),
  is_uncertain boolean not null default false,
  uncertainty_reason text,
  required_clearance smallint not null default 1 check (required_clearance between 1 and 5),
  position integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (source_url is not null or is_uncertain),
  check (not is_uncertain or uncertainty_reason is not null)
);

create table if not exists public.handover_item_tasks (
  item_id uuid not null references public.handover_items(id) on delete cascade,
  task_id uuid not null references public.tasks(id) on delete cascade,
  primary key (item_id, task_id)
);

create table if not exists public.handover_item_decisions (
  item_id uuid not null references public.handover_items(id) on delete cascade,
  decision_id uuid not null references public.decisions(id) on delete cascade,
  primary key (item_id, decision_id)
);

create table if not exists public.reviews (
  id uuid primary key default gen_random_uuid(),
  handover_id uuid not null references public.handover_drafts(id) on delete cascade,
  reviewer_id uuid not null references auth.users(id) on delete restrict,
  status public.review_status not null,
  comment text,
  created_at timestamptz not null default now()
);

create table if not exists public.knowledge_embeddings (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  handover_item_id uuid references public.handover_items(id) on delete cascade,
  source_document_id uuid references public.source_documents(id) on delete cascade,
  content text not null,
  embedding vector(1536) not null,
  source_url text not null,
  required_clearance smallint not null default 1 check (required_clearance between 1 and 5),
  is_approved boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (handover_item_id is not null)
);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams(id) on delete cascade,
  actor_id uuid references auth.users(id) on delete set null,
  action public.audit_action not null,
  entity_type text not null,
  entity_id uuid,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function public.add_team_owner()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.team_members (team_id, auth_user_id, name, role, clearance_level)
  select new.id, auth.uid(), coalesce(
    nullif(raw_user_meta_data->>'full_name', ''),
    nullif(raw_user_meta_data->>'name', ''),
    coalesce(email, 'Team owner')
  ), 'ADMIN', 5
  from auth.users
  where id = auth.uid()
  on conflict (team_id, auth_user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists teams_add_owner on public.teams;
create trigger teams_add_owner after insert on public.teams
for each row execute function public.add_team_owner();

create or replace function public.create_team(
  p_name text,
  p_description text default null
)
returns setof public.teams
language plpgsql
security definer
set search_path = public
as $$
declare
  created_team public.teams;
begin
  if auth.uid() is null then
    raise exception 'An authenticated user is required to create a team';
  end if;

  if p_name is null or length(trim(p_name)) = 0 then
    raise exception 'Team name cannot be empty';
  end if;

  insert into public.teams (name, description, created_by)
  values (trim(p_name), p_description, auth.uid())
  returning * into created_team;

  return next created_team;
end;
$$;

revoke all on function public.create_team(text, text) from public;
grant execute on function public.create_team(text, text) to authenticated;

drop trigger if exists teams_set_updated_at on public.teams;
create trigger teams_set_updated_at before update on public.teams
for each row execute function public.set_updated_at();

drop trigger if exists team_members_set_updated_at on public.team_members;
create trigger team_members_set_updated_at before update on public.team_members
for each row execute function public.set_updated_at();

drop trigger if exists source_documents_set_updated_at on public.source_documents;
create trigger source_documents_set_updated_at before update on public.source_documents
for each row execute function public.set_updated_at();

drop trigger if exists tasks_set_updated_at on public.tasks;
create trigger tasks_set_updated_at before update on public.tasks
for each row execute function public.set_updated_at();

drop trigger if exists decisions_set_updated_at on public.decisions;
create trigger decisions_set_updated_at before update on public.decisions
for each row execute function public.set_updated_at();

drop trigger if exists handover_drafts_set_updated_at on public.handover_drafts;
create trigger handover_drafts_set_updated_at before update on public.handover_drafts
for each row execute function public.set_updated_at();

drop trigger if exists handover_items_set_updated_at on public.handover_items;
create trigger handover_items_set_updated_at before update on public.handover_items
for each row execute function public.set_updated_at();

create or replace function public.is_team_member(target_team_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.team_members
    where team_id = target_team_id
      and auth_user_id = auth.uid()
  );
$$;

create or replace function public.has_team_role(target_team_id uuid, allowed_roles public.user_role[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.team_members
    where team_id = target_team_id
      and auth_user_id = auth.uid()
      and role = any(allowed_roles)
  );
$$;

create or replace function public.current_clearance(target_team_id uuid)
returns smallint
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(max(clearance_level), 0)::smallint
  from public.team_members
  where team_id = target_team_id
    and auth_user_id = auth.uid();
$$;

alter table public.teams enable row level security;
alter table public.team_members enable row level security;
alter table public.source_documents enable row level security;
alter table public.tasks enable row level security;
alter table public.decisions enable row level security;
alter table public.member_tasks enable row level security;
alter table public.task_decisions enable row level security;
alter table public.member_decisions enable row level security;
alter table public.handover_drafts enable row level security;
alter table public.handover_items enable row level security;
alter table public.handover_item_tasks enable row level security;
alter table public.handover_item_decisions enable row level security;
alter table public.reviews enable row level security;
alter table public.knowledge_embeddings enable row level security;
alter table public.audit_logs enable row level security;

drop policy if exists teams_select on public.teams;
create policy teams_select on public.teams for select using (public.is_team_member(id));
drop policy if exists teams_insert on public.teams;
create policy teams_insert on public.teams for insert with check (created_by = auth.uid());
drop policy if exists teams_update on public.teams;
create policy teams_update on public.teams for update using (public.has_team_role(id, array['ADMIN', 'LEAD']::public.user_role[]));

drop policy if exists team_members_select on public.team_members;
create policy team_members_select on public.team_members for select using (public.is_team_member(team_id));
drop policy if exists team_members_manage on public.team_members;
create policy team_members_manage on public.team_members for all
using (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]))
with check (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]));

drop policy if exists source_documents_select on public.source_documents;
create policy source_documents_select on public.source_documents for select
using (public.is_team_member(team_id))
;
drop policy if exists source_documents_manage on public.source_documents;
create policy source_documents_manage on public.source_documents for all
using (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]))
with check (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]));

drop policy if exists tasks_select on public.tasks;
create policy tasks_select on public.tasks for select
using (public.is_team_member(team_id))
;
drop policy if exists tasks_manage on public.tasks;
create policy tasks_manage on public.tasks for all
using (public.has_team_role(team_id, array['ADMIN', 'LEAD', 'DEVELOPER']::public.user_role[]))
with check (public.has_team_role(team_id, array['ADMIN', 'LEAD', 'DEVELOPER']::public.user_role[]));

drop policy if exists decisions_select on public.decisions;
create policy decisions_select on public.decisions for select
using (public.is_team_member(team_id))
;
drop policy if exists decisions_manage on public.decisions;
create policy decisions_manage on public.decisions for all
using (public.has_team_role(team_id, array['ADMIN', 'LEAD', 'DEVELOPER']::public.user_role[]))
with check (public.has_team_role(team_id, array['ADMIN', 'LEAD', 'DEVELOPER']::public.user_role[]));

drop policy if exists handovers_access on public.handover_drafts;
create policy handovers_access on public.handover_drafts for select
using (public.is_team_member(team_id));
drop policy if exists handovers_manage on public.handover_drafts;
create policy handovers_manage on public.handover_drafts for all
using (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]))
with check (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]));

drop policy if exists handover_items_access on public.handover_items;
create policy handover_items_access on public.handover_items for select
using (
  exists (
    select 1 from public.handover_drafts h
    where h.id = handover_id
      and public.is_team_member(h.team_id)
      and public.current_clearance(h.team_id) >= required_clearance
  )
);
drop policy if exists handover_items_manage on public.handover_items;
create policy handover_items_manage on public.handover_items for all
using (
  exists (
    select 1 from public.handover_drafts h
    where h.id = handover_id
      and public.has_team_role(h.team_id, array['ADMIN', 'LEAD']::public.user_role[])
  )
)
with check (
  exists (
    select 1 from public.handover_drafts h
    where h.id = handover_id
      and public.has_team_role(h.team_id, array['ADMIN', 'LEAD']::public.user_role[])
  )
);

drop policy if exists reviews_access on public.reviews;
create policy reviews_access on public.reviews for select
using (
  exists (
    select 1 from public.handover_drafts h
    where h.id = handover_id and public.is_team_member(h.team_id)
  )
);
drop policy if exists reviews_insert on public.reviews;
create policy reviews_insert on public.reviews for insert
with check (
  reviewer_id = auth.uid()
  and exists (
    select 1 from public.handover_drafts h
    where h.id = handover_id
      and public.has_team_role(h.team_id, array['ADMIN', 'LEAD']::public.user_role[])
  )
);

drop policy if exists embeddings_access on public.knowledge_embeddings;
create policy embeddings_access on public.knowledge_embeddings for select
using (is_approved and public.is_team_member(team_id) and public.current_clearance(team_id) >= required_clearance);
drop policy if exists embeddings_manage on public.knowledge_embeddings;
create policy embeddings_manage on public.knowledge_embeddings for all
using (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]))
with check (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]));

drop policy if exists audit_logs_select on public.audit_logs;
create policy audit_logs_select on public.audit_logs for select
using (public.has_team_role(team_id, array['ADMIN', 'LEAD']::public.user_role[]));
drop policy if exists audit_logs_insert on public.audit_logs;
create policy audit_logs_insert on public.audit_logs for insert
with check (public.is_team_member(team_id) and actor_id = auth.uid());

-- Join tables inherit access from their parent entities.
drop policy if exists member_tasks_access on public.member_tasks;
create policy member_tasks_access on public.member_tasks for all
using (exists (
  select 1 from public.tasks t
  where t.id = task_id and public.is_team_member(t.team_id)
))
with check (exists (
  select 1 from public.tasks t
  where t.id = task_id and public.is_team_member(t.team_id)
));

drop policy if exists task_decisions_access on public.task_decisions;
create policy task_decisions_access on public.task_decisions for all
using (exists (
  select 1 from public.tasks t
  where t.id = task_id and public.is_team_member(t.team_id)
))
with check (exists (
  select 1 from public.tasks t
  where t.id = task_id and public.is_team_member(t.team_id)
));

drop policy if exists member_decisions_access on public.member_decisions;
create policy member_decisions_access on public.member_decisions for all
using (exists (
  select 1 from public.decisions d
  where d.id = decision_id and public.is_team_member(d.team_id)
))
with check (exists (
  select 1 from public.decisions d
  where d.id = decision_id and public.is_team_member(d.team_id)
));

drop policy if exists handover_item_tasks_access on public.handover_item_tasks;
create policy handover_item_tasks_access on public.handover_item_tasks for all
using (exists (
  select 1
  from public.handover_items i
  join public.handover_drafts h on h.id = i.handover_id
  where i.id = item_id and public.is_team_member(h.team_id)
))
with check (exists (
  select 1
  from public.handover_items i
  join public.handover_drafts h on h.id = i.handover_id
  where i.id = item_id and public.is_team_member(h.team_id)
));

drop policy if exists handover_item_decisions_access on public.handover_item_decisions;
create policy handover_item_decisions_access on public.handover_item_decisions for all
using (exists (
  select 1
  from public.handover_items i
  join public.handover_drafts h on h.id = i.handover_id
  where i.id = item_id and public.is_team_member(h.team_id)
))
with check (exists (
  select 1
  from public.handover_items i
  join public.handover_drafts h on h.id = i.handover_id
  where i.id = item_id and public.is_team_member(h.team_id)
));

create index if not exists source_documents_team_status_idx
  on public.source_documents(team_id, status);
create index if not exists tasks_team_status_idx
  on public.tasks(team_id, status);
create index if not exists decisions_team_type_idx
  on public.decisions(team_id, decision_type);
create index if not exists handovers_team_status_idx
  on public.handover_drafts(team_id, status);
create index if not exists audit_logs_team_created_idx
  on public.audit_logs(team_id, created_at desc);
create index if not exists knowledge_embeddings_team_clearance_idx
  on public.knowledge_embeddings(team_id, required_clearance);
create index if not exists knowledge_embeddings_vector_idx
  on public.knowledge_embeddings using hnsw (embedding vector_cosine_ops);

grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;
