-- ============================================================
-- 热修复：密钥管理对「所有登录用户」开放（按用户隔离）
--
-- 症状：普通用户打开「密钥管理」页报「需要管理员权限」。
-- 原因：线上 list_api_secrets / save_api_secret / delete_api_secret
--       还是旧版（内部 if not is_admin() then raise），即 005 未执行。
--
-- 本脚本只做密钥这一块，可单独粘贴执行；执行完普通用户即可正常使用。
-- 幂等，可重复执行。
-- ============================================================

-- ------------------------------------------------------------
-- 1. 引用名唯一性：从「全局唯一」改为「按用户唯一」
-- ------------------------------------------------------------
alter table public.api_secrets drop constraint if exists api_secrets_secret_ref_key;
create unique index if not exists uq_api_secrets_owner_ref on public.api_secrets (created_by, secret_ref);

-- ------------------------------------------------------------
-- 2. 列表：只返回自己的密钥，任何人都能用（不再要求管理员）
-- ------------------------------------------------------------
create or replace function public.list_api_secrets()
returns setof json
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception '未登录';
  end if;

  return query
    select json_build_object(
      'id', s.id,
      'name', s.name,
      'provider', s.provider,
      'description', s.description,
      'masked', s.masked,
      'secret_ref', s.secret_ref,
      'status', s.status,
      'created_at', s.created_at,
      'updated_at', s.updated_at
    )
    from public.api_secrets s
    where s.created_by = auth.uid()
    order by s.updated_at desc;
end;
$$;

-- ------------------------------------------------------------
-- 3. 保存：新建归属自己；更新只能改自己的
-- ------------------------------------------------------------
create or replace function public.save_api_secret(
  p_id bigint default null,
  p_name text default null,
  p_provider text default '',
  p_description text default null,
  p_secret_ref text default null,
  p_value text default null,
  p_status text default 'ENABLED'
)
returns json
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row public.api_secrets;
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception '未登录';
  end if;

  if p_id is null then
    if p_value is null or btrim(p_value) = '' then
      raise exception '请填写密钥内容';
    end if;
    if p_secret_ref is null or btrim(p_secret_ref) = '' then
      raise exception '请填写引用名';
    end if;
    if exists (
      select 1 from public.api_secrets
      where secret_ref = btrim(p_secret_ref) and created_by = v_uid
    ) then
      raise exception '引用名 % 已存在', p_secret_ref;
    end if;

    insert into public.api_secrets (
      name, provider, description, secret_cipher, masked, secret_ref, status, created_by
    ) values (
      coalesce(nullif(btrim(p_name), ''), btrim(p_secret_ref)),
      coalesce(p_provider, ''),
      p_description,
      extensions.pgp_sym_encrypt(btrim(p_value), public.app_secret_key()),
      public.mask_secret(btrim(p_value)),
      btrim(p_secret_ref),
      coalesce(p_status, 'ENABLED'),
      v_uid
    )
    returning * into v_row;
  else
    if not exists (
      select 1 from public.api_secrets where id = p_id and created_by = v_uid
    ) then
      raise exception '密钥记录不存在';
    end if;

    if p_secret_ref is not null and btrim(p_secret_ref) <> '' then
      if exists (
        select 1 from public.api_secrets
        where secret_ref = btrim(p_secret_ref) and created_by = v_uid and id <> p_id
      ) then
        raise exception '引用名 % 已存在', p_secret_ref;
      end if;
    end if;

    update public.api_secrets set
      name = coalesce(nullif(btrim(p_name), ''), name),
      provider = coalesce(p_provider, provider),
      description = coalesce(p_description, description),
      secret_ref = coalesce(nullif(btrim(p_secret_ref), ''), secret_ref),
      status = coalesce(p_status, status),
      secret_cipher = case
        when p_value is null or btrim(p_value) = '' then secret_cipher
        else extensions.pgp_sym_encrypt(btrim(p_value), public.app_secret_key())
      end,
      masked = case
        when p_value is null or btrim(p_value) = '' then masked
        else public.mask_secret(btrim(p_value))
      end
    where id = p_id and created_by = v_uid
    returning * into v_row;

    if v_row is null then
      raise exception '密钥记录不存在';
    end if;
  end if;

  return json_build_object(
    'id', v_row.id,
    'name', v_row.name,
    'provider', v_row.provider,
    'description', v_row.description,
    'masked', v_row.masked,
    'secret_ref', v_row.secret_ref,
    'status', v_row.status,
    'updated_at', v_row.updated_at
  );
end;
$$;

-- ------------------------------------------------------------
-- 4. 删除：仅限自己的记录
-- ------------------------------------------------------------
create or replace function public.delete_api_secret(p_id bigint)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_ref text;
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception '未登录';
  end if;

  select secret_ref into v_ref
  from public.api_secrets
  where id = p_id and created_by = v_uid;

  if v_ref is null then
    raise exception '密钥记录不存在';
  end if;

  if exists (
    select 1 from public.model_configs
    where secret_ref = v_ref and created_by = v_uid
  ) then
    raise exception '仍有模型配置引用「%」，请先解除引用', v_ref;
  end if;

  delete from public.api_secrets where id = p_id and created_by = v_uid;
  return json_build_object('message', '密钥已删除');
end;
$$;

-- ------------------------------------------------------------
-- 5. 取密钥给 Edge Function 用（按归属者查找，仅 service_role 可调）
-- ------------------------------------------------------------
create or replace function public.get_api_secret_plain_for(
  p_ref text,
  p_owner uuid
)
returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_cipher bytea;
  v_status text;
begin
  select secret_cipher, status into v_cipher, v_status
  from public.api_secrets
  where secret_ref = p_ref and created_by = p_owner
  order by id desc
  limit 1;

  if v_cipher is null or v_status <> 'ENABLED' then
    return null;
  end if;

  return extensions.pgp_sym_decrypt(v_cipher, public.app_secret_key());
end;
$$;

-- ------------------------------------------------------------
-- 6. 收紧旧的全局取密钥函数（多用户各有一份同名密钥时放弃）
-- ------------------------------------------------------------
create or replace function public.get_api_secret_plain(p_ref text)
returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_cipher bytea;
  v_status text;
  v_count int;
begin
  select count(*) into v_count from public.api_secrets where secret_ref = p_ref;
  if v_count <> 1 then
    return null;
  end if;

  select secret_cipher, status into v_cipher, v_status
  from public.api_secrets
  where secret_ref = p_ref
  limit 1;

  if v_cipher is null or v_status <> 'ENABLED' then
    return null;
  end if;

  return extensions.pgp_sym_decrypt(v_cipher, public.app_secret_key());
end;
$$;

-- ------------------------------------------------------------
-- 7. 函数执行权限：登录用户即可调用；取明文只给 service_role
-- ------------------------------------------------------------
revoke all on function public.list_api_secrets() from public, anon;
grant execute on function public.list_api_secrets() to authenticated;

revoke all on function public.save_api_secret(bigint, text, text, text, text, text, text) from public, anon;
grant execute on function public.save_api_secret(bigint, text, text, text, text, text, text) to authenticated;

revoke all on function public.delete_api_secret(bigint) from public, anon;
grant execute on function public.delete_api_secret(bigint) to authenticated;

revoke all on function public.get_api_secret_plain_for(text, uuid) from public, anon, authenticated;
grant execute on function public.get_api_secret_plain_for(text, uuid) to service_role;

revoke all on function public.get_api_secret_plain(text) from public, anon, authenticated;
grant execute on function public.get_api_secret_plain(text) to service_role;
