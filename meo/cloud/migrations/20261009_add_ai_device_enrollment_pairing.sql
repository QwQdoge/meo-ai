create table if not exists public.ai_device_enrollments (
  id uuid primary key default gen_random_uuid(),
  secret_hash text not null unique,
  user_code text not null unique,
  user_id uuid references auth.users(id) on delete cascade,
  device_id text not null,
  display_name text not null,
  capabilities text[] not null default '{}',
  requested_scopes text[] not null default '{relay.connect,agent.run}',
  state text not null default 'pending' check (state in ('pending','approved','rejected','expired','consumed')),
  credential_id uuid references public.ai_device_credentials(id) on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  approved_at timestamptz,
  consumed_at timestamptz,
  check (expires_at > created_at),
  check (cardinality(capabilities) > 0),
  check (cardinality(requested_scopes) > 0),
  check (user_code ~ '^[A-Z2-9]{8}$')
);

create index if not exists ai_device_enrollments_pending_expiry_idx
  on public.ai_device_enrollments(state, expires_at)
  where state = 'pending';
create index if not exists ai_device_enrollments_user_idx
  on public.ai_device_enrollments(user_id, created_at desc)
  where user_id is not null;

alter table public.ai_device_enrollments enable row level security;
create policy "Service role manages AI device enrollments"
  on public.ai_device_enrollments
  for all to service_role
  using (true)
  with check (true);
