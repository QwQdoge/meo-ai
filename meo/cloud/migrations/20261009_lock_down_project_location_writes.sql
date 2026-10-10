drop policy if exists "Users can create their AI project locations" on public.ai_project_locations;
drop policy if exists "Users can update their AI project locations" on public.ai_project_locations;
drop policy if exists "Users can delete their AI project locations" on public.ai_project_locations;

create policy "Service role manages AI project locations"
  on public.ai_project_locations for all to service_role
  using (true) with check (true);
