-- Deployed to Supabase project meo-cloud-core.
-- Usage buckets are mutually exclusive: input excludes cached input, and output
-- excludes reasoning output. This keeps generated total_tokens additive across
-- Codex, Claude Code and Meo providers without double-counting cache/reasoning.

create table if not exists public.ai_usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source text not null check (source in ('meo','codex','claude_code','cline','opencode','cursor','other')),
  source_event_id text not null check (char_length(source_event_id) between 1 and 240),
  session_id text not null default '' check (char_length(session_id) <= 240),
  project_key text not null default '' check (char_length(project_key) <= 128),
  project_name text not null default '' check (char_length(project_name) <= 160),
  provider text not null default '' check (char_length(provider) <= 120),
  model text not null default '' check (char_length(model) <= 180),
  model_role text not null default 'unknown' check (model_role in ('chat','reasoning','execution','title','classification','tool','unknown')),
  occurred_at timestamptz not null,
  input_tokens bigint not null default 0 check (input_tokens >= 0),
  cached_input_tokens bigint not null default 0 check (cached_input_tokens >= 0),
  cache_write_tokens bigint not null default 0 check (cache_write_tokens >= 0),
  output_tokens bigint not null default 0 check (output_tokens >= 0),
  reasoning_tokens bigint not null default 0 check (reasoning_tokens >= 0),
  total_tokens bigint generated always as (
    input_tokens + cached_input_tokens + cache_write_tokens + output_tokens + reasoning_tokens
  ) stored,
  duration_ms bigint check (duration_ms is null or duration_ms >= 0),
  session_duration_ms bigint check (session_duration_ms is null or session_duration_ms >= 0),
  estimated_cost_microusd bigint check (estimated_cost_microusd is null or estimated_cost_microusd >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, source, source_event_id)
);

create index if not exists ai_usage_events_user_time_idx on public.ai_usage_events(user_id, occurred_at desc);
create index if not exists ai_usage_events_user_model_idx on public.ai_usage_events(user_id, model, occurred_at desc);
create index if not exists ai_usage_events_user_project_idx on public.ai_usage_events(user_id, project_key, occurred_at desc) where project_key <> '';
create index if not exists ai_usage_events_user_source_idx on public.ai_usage_events(user_id, source, occurred_at desc);

alter table public.ai_usage_events enable row level security;
create policy "Users can read their AI usage" on public.ai_usage_events for select to authenticated using ((select auth.uid()) = user_id);
create policy "Users can create their AI usage" on public.ai_usage_events for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "Users can update their AI usage" on public.ai_usage_events for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "Users can delete their AI usage" on public.ai_usage_events for delete to authenticated using ((select auth.uid()) = user_id);
create policy "Service role manages AI usage" on public.ai_usage_events for all to service_role using (true) with check (true);

create or replace function public.get_ai_usage_dashboard(p_days integer default 365)
returns jsonb language sql stable security invoker set search_path = public as $$
with params as (
  select greatest(7, least(coalesce(p_days, 365), 730))::int as days
), base as (
  select * from public.ai_usage_events where user_id = (select auth.uid())
), day_totals as (
  select occurred_at::date as day, sum(total_tokens)::bigint as tokens from base group by 1
), visible_days as (
  select day, tokens from day_totals, params where day >= current_date - (params.days - 1) order by day
), numbered_days as (
  select day, day - (row_number() over (order by day))::int as grp from day_totals
), streaks as (
  select min(day) as first_day, max(day) as last_day, count(*)::int as days from numbered_days group by grp
), model_totals as (
  select coalesce(nullif(model, ''), 'Unknown') as name,
         coalesce(nullif(provider, ''), 'Unknown') as provider,
         sum(total_tokens)::bigint as tokens, count(*)::bigint as events
  from base group by 1,2 order by tokens desc, name limit 16
), project_totals as (
  select coalesce(nullif(project_name, ''), 'Unassigned') as name, project_key,
         sum(total_tokens)::bigint as tokens, count(distinct nullif(session_id, ''))::bigint as sessions,
         max(occurred_at) as last_used_at
  from base group by 1,2 order by tokens desc, name limit 16
), source_totals as (
  select source, sum(total_tokens)::bigint as tokens, count(*)::bigint as events, max(occurred_at) as last_used_at
  from base group by source order by tokens desc, source
)
select jsonb_build_object(
  'summary', jsonb_build_object(
    'lifetime_tokens', coalesce((select sum(total_tokens)::bigint from base), 0),
    'peak_day_tokens', coalesce((select max(tokens)::bigint from day_totals), 0),
    'active_days', coalesce((select count(*)::int from day_totals), 0),
    'longest_streak', coalesce((select max(days)::int from streaks), 0),
    'current_streak', coalesce((select case when last_day >= current_date - 1 then days else 0 end from streaks order by last_day desc limit 1), 0),
    'longest_session_ms', coalesce((select max(session_duration_ms)::bigint from base), 0),
    'estimated_cost_microusd', coalesce((select sum(estimated_cost_microusd)::bigint from base), 0)
  ),
  'token_breakdown', jsonb_build_object(
    'input', coalesce((select sum(input_tokens)::bigint from base), 0),
    'cached_input', coalesce((select sum(cached_input_tokens)::bigint from base), 0),
    'cache_write', coalesce((select sum(cache_write_tokens)::bigint from base), 0),
    'output', coalesce((select sum(output_tokens)::bigint from base), 0),
    'reasoning', coalesce((select sum(reasoning_tokens)::bigint from base), 0)
  ),
  'daily', coalesce((select jsonb_agg(jsonb_build_object('date', day, 'tokens', tokens) order by day) from visible_days), '[]'::jsonb),
  'models', coalesce((select jsonb_agg(jsonb_build_object('name', name, 'provider', provider, 'tokens', tokens, 'events', events) order by tokens desc, name) from model_totals), '[]'::jsonb),
  'projects', coalesce((select jsonb_agg(jsonb_build_object('name', name, 'project_key', project_key, 'tokens', tokens, 'sessions', sessions, 'last_used_at', last_used_at) order by tokens desc, name) from project_totals), '[]'::jsonb),
  'sources', coalesce((select jsonb_agg(jsonb_build_object('source', source, 'tokens', tokens, 'events', events, 'last_used_at', last_used_at) order by tokens desc, source) from source_totals), '[]'::jsonb)
);
$$;
grant execute on function public.get_ai_usage_dashboard(integer) to authenticated;
