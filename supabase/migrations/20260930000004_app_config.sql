-- ============================================================
-- 系统配置表：替代 alter database set app.settings.*
--
-- 为什么不直接改数据库参数：
--   Supabase 托管实例不允许普通角色执行
--   `alter database postgres set app.settings.xxx`，
--   会报 42501 permission denied to set parameter。
--   因此改用一张配置表存这些值，由 SECURITY DEFINER 函数读取。
--
-- 同时顺手把「加密主密钥」也从 GUC 迁到这张表，
-- 这样三处配置都在这一个地方，部署时只需 insert 一次。
-- ============================================================

create table if not exists public.app_config (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

comment on table public.app_config is '系统级配置（cron 密钥、项目地址、密钥加密主密钥等）';

-- 开启 RLS 且不建任何策略：前端无法直接读写。
-- cron 任务通过 SECURITY DEFINER 函数读取，Edge Function 用 service_role 直读。
alter table public.app_config enable row level security;

-- ------------------------------------------------------------
-- 读取配置（内部用；SECURITY DEFINER 保证 cron 任务能读到）
-- ------------------------------------------------------------
create or replace function public.app_config_get(p_key text, p_default text default null)
returns text
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select value from public.app_config where key = p_key),
    p_default
  );
$$;

-- ------------------------------------------------------------
-- 写入配置（仅管理员；也可在 SQL Editor 里直接 insert/update）
-- ------------------------------------------------------------
create or replace function public.app_config_set(p_key text, p_value text)
returns json
language plpgsql
security definer
set search_path = public
as $$
begin
  -- SQL Editor 里执行时 auth.uid() 为 null，走下面的放行分支
  if auth.uid() is not null and not public.is_admin() then
    raise exception '需要管理员权限';
  end if;

  insert into public.app_config (key, value, updated_at)
  values (p_key, p_value, now())
  on conflict (key) do update
    set value = excluded.value, updated_at = now();

  return json_build_object('key', p_key, 'message', '配置已保存');
end;
$$;

-- 只有 service_role 能直接读表（cron 任务走上面的函数，不受影响）
revoke all on public.app_config from public, anon, authenticated;

revoke all on function public.app_config_get(text, text) from public, anon;
grant execute on function public.app_config_get(text, text) to authenticated, service_role;

revoke all on function public.app_config_set(text, text) from public, anon;
grant execute on function public.app_config_set(text, text) to authenticated, service_role;

-- ------------------------------------------------------------
-- 把密钥加密主密钥的读取改为查这张表
--   （原先读 GUC app.settings.secret_key，同样受 42501 限制）
-- ------------------------------------------------------------
create or replace function public.app_secret_key()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select value from public.app_config where key = 'secret_key'),
    'local-development-secret-change-me'
  );
$$;

-- 初始化默认值（已存在则不覆盖）
insert into public.app_config (key, value) values
  ('secret_key', 'local-development-secret-change-me')
on conflict (key) do nothing;
