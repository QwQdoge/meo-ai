-- Mirrors the additive schema deployed to Supabase project meo-cloud-core.
-- This file is the repository source of truth for recreating the Meo AI cloud tables.

create extension if not exists pgcrypto;

create table if not exists public.ai_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists ai_conversations_user_updated_idx on public.ai_conversations(user_id, updated_at desc);

create table if not exists public.ai_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.ai_conversations(id) on delete cascade,
  role text not null check (role in ('user','assistant','system','tool')),
  executor text not null default 'chat',
  content jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists ai_messages_conversation_created_idx on public.ai_messages(conversation_id, created_at, id);
create index if not exists ai_messages_user_idx on public.ai_messages(user_id);

create table if not exists public.ai_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  device_id text not null,
  display_name text not null,
  platform text not null default '',
  capabilities text[] not null default '{}',
  last_seen_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, device_id)
);
create index if not exists ai_devices_user_seen_idx on public.ai_devices(user_id, last_seen_at desc nulls last);

create table if not exists public.ai_device_credentials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  device_id text not null,
  token_hash text not null unique,
  scopes text[] not null default '{}',
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (user_id, device_id) references public.ai_devices(user_id, device_id) on delete cascade,
  check (expires_at > issued_at),
  check (cardinality(scopes) > 0)
);
create index if not exists ai_device_credentials_device_idx on public.ai_device_credentials(user_id, device_id, expires_at desc);

create table if not exists public.ai_agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid references public.ai_conversations(id) on delete set null,
  device_id text not null,
  project_id uuid,
  workspace_ref text,
  executor text not null default 'agent',
  status text not null check (status in ('queued','dispatching','running','awaiting_approval','cancel_requested','completed','cancelled','failed')),
  local_request_id text,
  last_event_seq bigint not null default -1 check (last_event_seq >= -1),
  error_code text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null default now(),
  foreign key (user_id, device_id) references public.ai_devices(user_id, device_id) on delete restrict
);
create index if not exists ai_agent_runs_user_created_idx on public.ai_agent_runs(user_id, created_at desc);
create index if not exists ai_agent_runs_conversation_idx on public.ai_agent_runs(conversation_id);
create index if not exists ai_agent_runs_device_active_idx on public.ai_agent_runs(user_id, device_id, status) where status not in ('completed','cancelled','failed');

create table if not exists public.ai_agent_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid not null references public.ai_agent_runs(id) on delete cascade,
  seq bigint not null check (seq >= 0),
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_id, seq)
);
create index if not exists ai_agent_events_run_seq_idx on public.ai_agent_events(run_id, seq);
create index if not exists ai_agent_events_user_idx on public.ai_agent_events(user_id);

create table if not exists public.ai_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  slug text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, slug)
);

create table if not exists public.ai_project_locations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.ai_projects(id) on delete cascade,
  device_id text not null,
  workspace_ref text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, device_id),
  foreign key (user_id, device_id) references public.ai_devices(user_id, device_id) on delete cascade
);
create index if not exists ai_project_locations_user_device_idx on public.ai_project_locations(user_id, device_id);
create index if not exists ai_project_locations_user_idx on public.ai_project_locations(user_id);

alter table public.ai_conversations enable row level security;
alter table public.ai_messages enable row level security;
alter table public.ai_devices enable row level security;
alter table public.ai_device_credentials enable row level security;
alter table public.ai_agent_runs enable row level security;
alter table public.ai_agent_events enable row level security;
alter table public.ai_projects enable row level security;
alter table public.ai_project_locations enable row level security;

create policy "Users can read their AI conversations" on public.ai_conversations for select to authenticated using ((select auth.uid()) = user_id);
create policy "Users can create their AI conversations" on public.ai_conversations for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "Users can update their AI conversations" on public.ai_conversations for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "Users can delete their AI conversations" on public.ai_conversations for delete to authenticated using ((select auth.uid()) = user_id);

create policy "Users can read their AI messages" on public.ai_messages for select to authenticated using ((select auth.uid()) = user_id);
create policy "Users can create their AI messages" on public.ai_messages for insert to authenticated with check ((select auth.uid()) = user_id and exists (select 1 from public.ai_conversations c where c.id = conversation_id and c.user_id = (select auth.uid())));

create policy "Users can read their AI devices" on public.ai_devices for select to authenticated using ((select auth.uid()) = user_id);
create policy "Service role manages AI devices" on public.ai_devices for all to service_role using (true) with check (true);
create policy "Service role manages AI device credentials" on public.ai_device_credentials for all to service_role using (true) with check (true);

create policy "Users can read their AI agent runs" on public.ai_agent_runs for select to authenticated using ((select auth.uid()) = user_id);
create policy "Service role manages AI agent runs" on public.ai_agent_runs for all to service_role using (true) with check (true);
create policy "Users can read their AI agent events" on public.ai_agent_events for select to authenticated using ((select auth.uid()) = user_id);
create policy "Service role manages AI agent events" on public.ai_agent_events for all to service_role using (true) with check (true);

create policy "Users can read their AI projects" on public.ai_projects for select to authenticated using ((select auth.uid()) = user_id);
create policy "Users can create their AI projects" on public.ai_projects for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "Users can update their AI projects" on public.ai_projects for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "Users can delete their AI projects" on public.ai_projects for delete to authenticated using ((select auth.uid()) = user_id);

create policy "Users can read their AI project locations" on public.ai_project_locations for select to authenticated using ((select auth.uid()) = user_id);
create policy "Users can create their AI project locations" on public.ai_project_locations for insert to authenticated with check ((select auth.uid()) = user_id and exists (select 1 from public.ai_projects p where p.id = project_id and p.user_id = (select auth.uid())));
create policy "Users can update their AI project locations" on public.ai_project_locations for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "Users can delete their AI project locations" on public.ai_project_locations for delete to authenticated using ((select auth.uid()) = user_id);
