-- ============================================================
-- 密钥管理：把模型 API Key 加密存入数据库
-- 设计：
--   明文 Key 用 pgcrypto 的对称加密（密钥存在 app_config 表里），
--   通过 SECURITY DEFINER 函数读写，RLS 禁止直接 select 密文列，
--   保证前端永远拿不到明文（只能写入、只能读掩码）。
-- ============================================================

create extension if not exists pgcrypto with schema extensions;

-- 注意：加密主密钥 app_secret_key() 由 20260930000004_app_config.sql 定义，
-- 值存在 public.app_config 表里。本文件只管密钥表本身与读写函数。
-- 若单独执行本文件（不执行 004），pgp_sym_encrypt 会因找不到密钥函数而报错，
-- 所以请按 001 → 003 → 004 → 002 的顺序执行。

-- ------------------------------------------------------------
-- 表：api_secrets
-- ------------------------------------------------------------
create table if not exists public.api_secrets (
  id bigserial primary key,
  name text not null,
  provider text not null default '',
  description text,
  -- 密文（pgp_sym_encrypt 产出 bytea）
  secret_cipher bytea not null,
  -- 掩码，供列表展示（如 sk-1***abcd）
  masked text not null default '',
  -- 供 Edge Function 通过引用名读取
  secret_ref text not null unique,
  status text not null default 'ENABLED' check (status in ('ENABLED', 'DISABLED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_api_secrets_name on public.api_secrets (name);
create index if not exists ix_api_secrets_ref on public.api_secrets (secret_ref);

drop trigger if exists trg_api_secrets_touch on public.api_secrets;
create trigger trg_api_secrets_touch before update on public.api_secrets
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- 开启 RLS，且不给任何 select 策略：
--   前端不能直接查这张表（避免密文/掩码以外信息泄露），
--   所有读写一律走下面的 SECURITY DEFINER 函数。
-- ------------------------------------------------------------
alter table public.api_secrets enable row level security;

-- ------------------------------------------------------------
-- 生成掩码：保留前 4 位和后 4 位
-- ------------------------------------------------------------
create or replace function public.mask_secret(plain text)
returns text
language sql
immutable
as $$
  select case
    when length(plain) <= 8 then repeat('*', greatest(length(plain), 4))
    else left(plain, 4) || '****' || right(plain, 4)
  end;
$$;

-- ------------------------------------------------------------
-- 写入 / 更新密钥（仅管理员）
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
  if not public.is_admin() then
    raise exception '需要管理员权限';
  end if;

  if p_id is null then
    -- 新建：必须提供值
    if p_value is null or btrim(p_value) = '' then
      raise exception '请填写密钥内容';
    end if;
    if p_secret_ref is null or btrim(p_secret_ref) = '' then
      raise exception '请填写引用名';
    end if;
    if exists (select 1 from public.api_secrets where secret_ref = btrim(p_secret_ref)) then
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
    -- 更新：值为空表示不改密钥
    if p_secret_ref is not null and btrim(p_secret_ref) <> '' then
      if exists (
        select 1 from public.api_secrets
        where secret_ref = btrim(p_secret_ref) and id <> p_id
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
    where id = p_id
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
-- 列出密钥（仅管理员，返回掩码，绝不返回明文/密文）
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
  if not public.is_admin() then
    raise exception '需要管理员权限';
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
    order by s.updated_at desc;
end;
$$;

-- ------------------------------------------------------------
-- 删除密钥（仅管理员）
-- ------------------------------------------------------------
create or replace function public.delete_api_secret(p_id bigint)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_ref text;
begin
  if auth.uid() is null then
    raise exception '未登录';
  end if;
  if not public.is_admin() then
    raise exception '需要管理员权限';
  end if;

  select secret_ref into v_ref from public.api_secrets where id = p_id;
  if v_ref is null then
    raise exception '密钥记录不存在';
  end if;

  -- 若有模型配置正在引用，禁止删除
  if exists (
    select 1 from public.model_configs
    where secret_ref = v_ref
  ) then
    raise exception '仍有模型配置引用「%」，请先解除引用', v_ref;
  end if;

  delete from public.api_secrets where id = p_id;
  return json_build_object('message', '密钥已删除');
end;
$$;

-- ------------------------------------------------------------
-- 供 Edge Function（service_role）解密读取
--   仅 service_role 可执行；前端用 anon key 调不到。
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
begin
  select secret_cipher, status into v_cipher, v_status
  from public.api_secrets
  where secret_ref = p_ref;

  if v_cipher is null then
    return null;
  end if;
  if v_status <> 'ENABLED' then
    return null;
  end if;

  return extensions.pgp_sym_decrypt(v_cipher, public.app_secret_key());
end;
$$;

-- 收紧执行权限：默认 PUBLIC 可执行，这里收回
revoke all on function public.get_api_secret_plain(text) from public, anon, authenticated;
grant execute on function public.get_api_secret_plain(text) to service_role;

revoke all on function public.save_api_secret(bigint, text, text, text, text, text, text) from public, anon;
grant execute on function public.save_api_secret(bigint, text, text, text, text, text, text) to authenticated;

revoke all on function public.list_api_secrets() from public, anon;
grant execute on function public.list_api_secrets() to authenticated;

revoke all on function public.delete_api_secret(bigint) from public, anon;
grant execute on function public.delete_api_secret(bigint) to authenticated;
