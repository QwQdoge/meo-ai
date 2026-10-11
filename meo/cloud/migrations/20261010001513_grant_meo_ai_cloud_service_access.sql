-- RLS policies do not grant table privileges. The Cloud backend uses the
-- service-role Data API; keep these grants independent of dashboard defaults.
grant select, insert, update, delete on table
  public.ai_conversations,
  public.ai_messages,
  public.ai_devices,
  public.ai_device_credentials,
  public.ai_agent_runs,
  public.ai_agent_events,
  public.ai_projects,
  public.ai_project_locations,
  public.ai_device_enrollments
to service_role;

grant usage, select on sequence public.ai_agent_events_id_seq to service_role;
