-- Shared Meo AI account state for Web and Desktop.
--
-- This migration deliberately keeps secrets out of Meo AI-owned tables. Provider
-- credentials remain Account-owned; this table stores only portable preferences.
-- It also adds soft-delete metadata required for deterministic offline history sync.

create table if not exists public.ai_user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  schema_version integer not null default 1 check (schema_version between 1 and 1000),
  settings jsonb not null default '{
    "model_roles": {},
    "agent": {"coordinator": true, "judge": true},
    "memory": {"enabled": true},
    "sync": {"history": true, "settings": true, "memory": true}
  }'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (jsonb_typeof(settings) = 'object'),
  check (octet_length(settings::text) <= 65536)
);

create index if not exists ai_user_settings_updated_idx
  on public.ai_user_settings(updated_at desc);

alter table public.ai_user_settings enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'ai_user_settings'
      and policyname = 'Users can read their AI settings'
  ) then
    create policy "Users can read their AI settings"
      on public.ai_user_settings
      for select to authenticated
      using ((select auth.uid()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'ai_user_settings'
      and policyname = 'Users can create their AI settings'
  ) then
    create policy "Users can create their AI settings"
      on public.ai_user_settings
      for insert to authenticated
      with check ((select auth.uid()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'ai_user_settings'
      and policyname = 'Users can update their AI settings'
  ) then
    create policy "Users can update their AI settings"
      on public.ai_user_settings
      for update to authenticated
      using ((select auth.uid()) = user_id)
      with check ((select auth.uid()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'ai_user_settings'
      and policyname = 'Users can delete their AI settings'
  ) then
    create policy "Users can delete their AI settings"
      on public.ai_user_settings
      for delete to authenticated
      using ((select auth.uid()) = user_id);
  end if;
end
$$;

grant select, insert, update, delete on public.ai_user_settings to authenticated;
grant select, insert, update, delete on public.ai_user_settings to service_role;

-- Conversations are soft-deleted first. This prevents an offline device from
-- re-uploading a conversation that another device has already deleted.
alter table public.ai_conversations
  add column if not exists deleted_at timestamptz;

create index if not exists ai_conversations_user_sync_idx
  on public.ai_conversations(user_id, updated_at desc, id desc);

create index if not exists ai_conversations_user_deleted_idx
  on public.ai_conversations(user_id, deleted_at)
  where deleted_at is not null;

-- Messages are intentionally append-oriented. A conservative database-side
-- guard protects the beta service from accidental multi-megabyte text writes.
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'ai_messages_content_size_check'
      and conrelid = 'public.ai_messages'::regclass
  ) then
    alter table public.ai_messages
      add constraint ai_messages_content_size_check
      check (octet_length(content::text) <= 262144) not valid;
  end if;
end
$$;

comment on table public.ai_user_settings is
  'Portable, non-secret Meo AI preferences shared by Web and Desktop. Provider API keys and account bearer tokens must never be stored here.';

comment on column public.ai_conversations.deleted_at is
  'Soft-delete tombstone used by incremental multi-device history sync. Purge is a separate retention job.';
