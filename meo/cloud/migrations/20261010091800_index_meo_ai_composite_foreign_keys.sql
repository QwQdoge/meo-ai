create index if not exists ai_agent_events_owner_run_idx
  on public.ai_agent_events(user_id, run_id);

create index if not exists ai_agent_runs_owner_conversation_idx
  on public.ai_agent_runs(user_id, conversation_id);

create index if not exists ai_device_enrollments_credential_idx
  on public.ai_device_enrollments(credential_id);

create index if not exists ai_messages_owner_conversation_idx
  on public.ai_messages(user_id, conversation_id);

create index if not exists ai_project_locations_owner_project_idx
  on public.ai_project_locations(user_id, project_id);
