create unique index if not exists ai_conversations_user_id_id_uidx
  on public.ai_conversations(user_id, id);
create unique index if not exists ai_agent_runs_user_id_id_uidx
  on public.ai_agent_runs(user_id, id);
create unique index if not exists ai_projects_user_id_id_uidx
  on public.ai_projects(user_id, id);

do $$ begin
  alter table public.ai_messages
    add constraint ai_messages_owner_conversation_fkey
    foreign key (user_id, conversation_id)
    references public.ai_conversations(user_id, id)
    on delete cascade;
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table public.ai_agent_runs
    add constraint ai_agent_runs_owner_conversation_fkey
    foreign key (user_id, conversation_id)
    references public.ai_conversations(user_id, id)
    on delete set null;
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table public.ai_agent_events
    add constraint ai_agent_events_owner_run_fkey
    foreign key (user_id, run_id)
    references public.ai_agent_runs(user_id, id)
    on delete cascade;
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table public.ai_project_locations
    add constraint ai_project_locations_owner_project_fkey
    foreign key (user_id, project_id)
    references public.ai_projects(user_id, id)
    on delete cascade;
exception when duplicate_object then null;
end $$;
