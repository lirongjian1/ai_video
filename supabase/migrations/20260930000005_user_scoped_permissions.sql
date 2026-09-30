-- ============================================================
-- 权限模型统一：完全按用户隔离
--
-- 规则：
--   普通用户  = 自己的数据（项目/文件/提示词/模型/密钥/剧本/任务…）
--   管理员    = 上述全部 + 「用户管理」权限
--   除用户管理外，所有资源一律按 created_by 隔离，不存在共享。
--
-- 本文件做两件事：
--   1) 撤销上一版「模型配置全局可读」的错误策略，回归按用户隔离
--   2) 把密钥表（api_secrets）也改为按用户隔离
--
-- 幂等，可对已部署的库重复执行。
-- ============================================================

-- ------------------------------------------------------------
-- 1. 模型配置：撤销共享，回归「创建者或管理员」
-- ------------------------------------------------------------
drop policy if exists model_configs_read on public.model_configs;
drop policy if exists model_configs_write on public.model_configs;

drop policy if exists model_configs_owner on public.model_configs;
create policy model_configs_owner on public.model_configs
  for all to authenticated
  using (created_by = auth.uid() or public.is_admin())
  with check (created_by = auth.uid() or public.is_admin());

-- ------------------------------------------------------------
-- 2. 密钥：改为按用户隔离
--    api_secrets 开启了 RLS 但没有 select 策略，读写都走下面的
--    SECURITY DEFINER 函数。这里把这几个函数改为「仅操作自己的记录」。
-- ------------------------------------------------------------

-- 列表：只返回自己的密钥（管理员也只看自己的，用户管理权限不延伸到这里）
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

-- 保存：新建时归属自己；更新时只能改自己的记录
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
    -- 新建：必须提供值与引用名
    if p_value is null or btrim(p_value) = '' then
      raise exception '请填写密钥内容';
    end if;
    if p_secret_ref is null or btrim(p_secret_ref) = '' then
      raise exception '请填写引用名';
    end if;
    -- 引用名在「自己的范围内」唯一
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
    -- 更新：仅限自己的记录
    if not exists (
      select 1 from public.api_secrets where id = p_id and created_by = v_uid
    ) then
      raise exception '密钥记录不存在';  -- 不区分「无权限」与「不存在」，避免探测
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

-- 删除：仅限自己的记录；仍保留「被引用则禁删」的保护
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

  -- 若有「自己的」模型配置正在引用，禁止删除
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
-- 3. 引用名唯一性：从「全局唯一」改为「按用户唯一」
--    否则 A 用户建了 OPENAI_API_KEY，B 用户就再也建不了同名引用。
-- ------------------------------------------------------------
alter table public.api_secrets drop constraint if exists api_secrets_secret_ref_key;
create unique index if not exists uq_api_secrets_owner_ref on public.api_secrets (created_by, secret_ref);

-- ------------------------------------------------------------
-- 4. Edge Function 取密钥：按「模型配置的归属者」查找
--    新增按 owner 查找的重载：先按 owner + ref 找，找不到再全局兜底。
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

revoke all on function public.get_api_secret_plain_for(text, uuid) from public, anon, authenticated;
grant execute on function public.get_api_secret_plain_for(text, uuid) to service_role;

-- 权限收紧（函数签名未变，这里重复声明保证生效）
revoke all on function public.list_api_secrets() from public, anon;
grant execute on function public.list_api_secrets() to authenticated;

revoke all on function public.save_api_secret(bigint, text, text, text, text, text, text) from public, anon;
grant execute on function public.save_api_secret(bigint, text, text, text, text, text, text) to authenticated;

revoke all on function public.delete_api_secret(bigint) from public, anon;
grant execute on function public.delete_api_secret(bigint) to authenticated;

-- ------------------------------------------------------------
-- 5. 收紧旧的全局取密钥函数
--    密钥已按用户隔离，这个函数无法知道「是谁的密钥」，
--    继续按 ref 全局查找会串到别人头上。这里让它只在
--    「该 ref 全局只有一条记录」时才返回值（即老的单用户库兼容），
--    一旦出现多条同名密钥就返回 null，强制走 *_for(owner) 版本。
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
  -- 多个用户各有一份同名密钥时，无法判断归属，直接放弃
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

revoke all on function public.get_api_secret_plain(text) from public, anon, authenticated;
grant execute on function public.get_api_secret_plain(text) to service_role;
