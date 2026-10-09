create or replace function public.service_consume_ai_device_enrollment(
  target_secret_hash text,
  new_token_hash text,
  credential_expires_at timestamptz
)
returns table(
  account_user_id uuid,
  device_id text,
  credential_id uuid,
  scopes text[]
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  enrollment public.ai_device_enrollments%rowtype;
  new_credential_id uuid;
begin
  select * into enrollment
  from public.ai_device_enrollments
  where secret_hash = target_secret_hash
  for update;

  if not found
     or enrollment.state <> 'approved'
     or enrollment.user_id is null
     or enrollment.expires_at <= now()
     or credential_expires_at <= now() then
    return;
  end if;

  insert into public.ai_devices (
    user_id, device_id, display_name, capabilities, last_seen_at, updated_at
  ) values (
    enrollment.user_id,
    enrollment.device_id,
    enrollment.display_name,
    enrollment.capabilities,
    now(),
    now()
  )
  on conflict (user_id, device_id) do update set
    display_name = excluded.display_name,
    capabilities = excluded.capabilities,
    revoked_at = null,
    updated_at = now();

  insert into public.ai_device_credentials (
    user_id, device_id, token_hash, scopes, expires_at
  ) values (
    enrollment.user_id,
    enrollment.device_id,
    new_token_hash,
    enrollment.requested_scopes,
    credential_expires_at
  ) returning id into new_credential_id;

  update public.ai_device_enrollments
  set state = 'consumed',
      credential_id = new_credential_id,
      consumed_at = now()
  where id = enrollment.id;

  return query
  select enrollment.user_id,
         enrollment.device_id,
         new_credential_id,
         enrollment.requested_scopes;
end;
$$;

revoke all on function public.service_consume_ai_device_enrollment(text, text, timestamptz)
  from public, anon, authenticated;
grant execute on function public.service_consume_ai_device_enrollment(text, text, timestamptz)
  to service_role;
