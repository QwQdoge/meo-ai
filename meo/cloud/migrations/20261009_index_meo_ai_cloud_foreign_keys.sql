create index if not exists ai_agent_events_user_idx
  on public.ai_agent_events(user_id);
create index if not exists ai_agent_runs_conversation_idx
  on public.ai_agent_runs(conversation_id);
create index if not exists ai_messages_user_idx
  on public.ai_messages(user_id);
create index if not exists ai_project_locations_user_device_idx
  on public.ai_project_locations(user_id, device_id);
create index if not exists ai_project_locations_user_idx
  on public.ai_project_locations(user_id);
