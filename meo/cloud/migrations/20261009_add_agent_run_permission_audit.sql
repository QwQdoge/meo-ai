alter table public.ai_agent_runs
  add column if not exists permission_mode text not null default 'smart',
  add column if not exists requested_capabilities text[] not null default array['agent.chat']::text[];

do $$ begin
  alter table public.ai_agent_runs
    add constraint ai_agent_runs_permission_mode_check
    check (permission_mode in ('ask','smart','full_access'));
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table public.ai_agent_runs
    add constraint ai_agent_runs_requested_capabilities_nonempty
    check (cardinality(requested_capabilities) > 0);
exception when duplicate_object then null;
end $$;
