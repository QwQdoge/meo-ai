do $$ begin
  alter table public.ai_project_locations
    add constraint ai_project_locations_workspace_ref_format_check
    check (
      length(workspace_ref) between 3 and 128
      and workspace_ref !~ '[\\/\\\\\n\r\t]'
    );
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table public.ai_agent_runs
    add constraint ai_agent_runs_workspace_ref_format_check
    check (
      workspace_ref is null
      or (
        length(workspace_ref) between 3 and 128
        and workspace_ref !~ '[\\/\\\\\n\r\t]'
      )
    );
exception when duplicate_object then null;
end $$;
