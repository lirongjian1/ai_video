-- ============================================================
-- AI Video Workflow — Supabase 初始化迁移
-- 说明：由原 MySQL 结构迁移而来，表名去掉 ai_ 前缀以便直连
--       sys_user 由 Supabase Auth 接管，改用 profiles
-- ============================================================

create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- 通用：updated_at 自动维护
-- ------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ------------------------------------------------------------
-- profiles：用户档案，关联 auth.users
-- 原 sys_user 的 username/nickname/status/last_login_time 迁到这里
-- role 用于替代原「管理员」概念
-- ------------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  username text not null unique,
  nickname text not null default '',
  role text not null default 'USER' check (role in ('ADMIN', 'USER')),
  status text not null default 'ENABLED' check (status in ('ENABLED', 'DISABLED')),
  last_login_time timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_profiles_username on public.profiles (username);
create index if not exists ix_profiles_role on public.profiles (role);

drop trigger if exists trg_profiles_touch on public.profiles;
create trigger trg_profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

-- 注册后自动建档
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, username, nickname)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'username', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data ->> 'nickname', '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- 判断是否管理员（RLS 里复用）
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'ADMIN' and status = 'ENABLED'
  );
$$;

-- ------------------------------------------------------------
-- projects
-- ------------------------------------------------------------
create table if not exists public.projects (
  id bigserial primary key,
  name text not null,
  description text,
  cover_file_id bigint,
  status text not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED', 'DISABLED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_projects_name on public.projects (name);
create index if not exists ix_projects_status on public.projects (status);
create index if not exists ix_projects_created_by on public.projects (created_by);

drop trigger if exists trg_projects_touch on public.projects;
create trigger trg_projects_touch before update on public.projects
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- files：资产文件（图片 / 视频）
-- storage_path 改为存储桶内相对路径，url 由前端现算
-- ------------------------------------------------------------
create table if not exists public.files (
  id bigserial primary key,
  project_id bigint references public.projects (id) on delete set null,
  file_name text not null,
  original_name text not null,
  file_type text not null check (file_type in ('IMAGE', 'VIDEO')),
  mime_type text not null,
  file_size bigint not null default 0,
  storage_bucket text not null default 'media',
  storage_path text not null,
  thumbnail_path text,
  width integer,
  height integer,
  duration double precision,
  source_type text not null default 'UPLOAD'
    check (source_type in ('UPLOAD', 'AI_IMAGE', 'AI_VIDEO', 'VIDEO_MERGE')),
  source_id bigint,
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_files_project on public.files (project_id);
create index if not exists ix_files_name on public.files (file_name);
create index if not exists ix_files_type on public.files (file_type);
create index if not exists ix_files_source on public.files (source_type);
create index if not exists ix_files_created_by on public.files (created_by);

drop trigger if exists trg_files_touch on public.files;
create trigger trg_files_touch before update on public.files
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- prompts
-- ------------------------------------------------------------
create table if not exists public.prompts (
  id bigserial primary key,
  project_id bigint references public.projects (id) on delete set null,
  name text not null,
  prompt_type text not null
    check (prompt_type in ('CHARACTER', 'SCENE', 'SCRIPT', 'STORYBOARD', 'VIDEO', 'CUSTOM')),
  content text not null,
  negative_prompt text,
  variables jsonb not null default '{}'::jsonb,
  status text not null default 'ENABLED' check (status in ('ENABLED', 'DISABLED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_prompts_name on public.prompts (name);
create index if not exists ix_prompts_project on public.prompts (project_id);
create index if not exists ix_prompts_type on public.prompts (prompt_type);

drop trigger if exists trg_prompts_touch on public.prompts;
create trigger trg_prompts_touch before update on public.prompts
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- model_configs：模型配置
-- 注意：api_key 不入库，改为引用 Edge Function Secrets 的名称
-- ------------------------------------------------------------
create table if not exists public.model_configs (
  id bigserial primary key,
  name text not null,
  model_type text not null check (model_type in ('TEXT', 'IMAGE', 'VIDEO')),
  provider text not null,
  base_url text,
  model_name text not null,
  secret_ref text,
  extra_config jsonb not null default '{}'::jsonb,
  status text not null default 'ENABLED' check (status in ('ENABLED', 'DISABLED')),
  is_default boolean not null default false,
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_model_configs_name on public.model_configs (name);
create index if not exists ix_model_configs_type on public.model_configs (model_type);
create index if not exists ix_model_configs_status on public.model_configs (status);

drop trigger if exists trg_model_configs_touch on public.model_configs;
create trigger trg_model_configs_touch before update on public.model_configs
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- characters
-- ------------------------------------------------------------
create table if not exists public.characters (
  id bigserial primary key,
  project_id bigint not null references public.projects (id) on delete cascade,
  name text not null,
  description text,
  appearance text,
  personality text,
  reference_file_id bigint references public.files (id) on delete set null,
  prompt_id bigint references public.prompts (id) on delete set null,
  status text not null default 'ACTIVE' check (status in ('ACTIVE', 'DISABLED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_characters_project on public.characters (project_id);
create index if not exists ix_characters_name on public.characters (name);

drop trigger if exists trg_characters_touch on public.characters;
create trigger trg_characters_touch before update on public.characters
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- scenes
-- ------------------------------------------------------------
create table if not exists public.scenes (
  id bigserial primary key,
  project_id bigint not null references public.projects (id) on delete cascade,
  name text not null,
  description text,
  environment text,
  atmosphere text,
  reference_file_id bigint references public.files (id) on delete set null,
  prompt_id bigint references public.prompts (id) on delete set null,
  status text not null default 'ACTIVE' check (status in ('ACTIVE', 'DISABLED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_scenes_project on public.scenes (project_id);
create index if not exists ix_scenes_name on public.scenes (name);

drop trigger if exists trg_scenes_touch on public.scenes;
create trigger trg_scenes_touch before update on public.scenes
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- scripts：剧本
-- ------------------------------------------------------------
create table if not exists public.scripts (
  id bigserial primary key,
  project_id bigint not null references public.projects (id) on delete cascade,
  title text not null,
  summary text,
  content text not null default '',
  duration integer,
  status text not null default 'DRAFT' check (status in ('DRAFT', 'READY', 'ARCHIVED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_scripts_project on public.scripts (project_id);
create index if not exists ix_scripts_title on public.scripts (title);

drop trigger if exists trg_scripts_touch on public.scripts;
create trigger trg_scripts_touch before update on public.scripts
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- storyboards：分镜（固定 6 段）
-- ------------------------------------------------------------
create table if not exists public.storyboards (
  id bigserial primary key,
  script_id bigint not null references public.scripts (id) on delete cascade,
  project_id bigint not null references public.projects (id) on delete cascade,
  sequence integer not null default 1,
  title text not null,
  description text,
  duration double precision,
  camera text,
  dialogue text,
  video_prompt text,
  scene_id bigint references public.scenes (id) on delete set null,
  character_ids jsonb not null default '[]'::jsonb,
  reference_file_ids jsonb not null default '[]'::jsonb,
  status text not null default 'DRAFT' check (status in ('DRAFT', 'READY', 'GENERATED')),
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_storyboards_script on public.storyboards (script_id);
create index if not exists ix_storyboards_project on public.storyboards (project_id);

drop trigger if exists trg_storyboards_touch on public.storyboards;
create trigger trg_storyboards_touch before update on public.storyboards
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- tasks：任务
-- provider_task_id / provider_status 提列，便于轮询查询
-- ------------------------------------------------------------
create table if not exists public.tasks (
  id bigserial primary key,
  project_id bigint references public.projects (id) on delete set null,
  name text not null,
  task_type text not null check (task_type in ('TEXT', 'IMAGE', 'VIDEO', 'MERGE')),
  target_type text,
  target_id bigint,
  model_config_id bigint references public.model_configs (id) on delete set null,
  status text not null default 'PENDING'
    check (status in ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')),
  progress integer not null default 0,
  provider_task_id text,
  provider_status text,
  request_payload jsonb not null default '{}'::jsonb,
  result_payload jsonb not null default '{}'::jsonb,
  error_message text,
  started_at timestamptz,
  finished_at timestamptz,
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_tasks_name on public.tasks (name);
create index if not exists ix_tasks_project on public.tasks (project_id);
create index if not exists ix_tasks_type on public.tasks (task_type);
create index if not exists ix_tasks_status on public.tasks (status);
-- 轮询函数靠这个索引捞待处理任务
create index if not exists ix_tasks_pending_poll on public.tasks (status, provider_task_id)
  where status in ('PENDING', 'RUNNING') and provider_task_id is not null;

drop trigger if exists trg_tasks_touch on public.tasks;
create trigger trg_tasks_touch before update on public.tasks
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- 存储桶：media（公开读，写受 RLS 控制）
-- ------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('media', 'media', true)
on conflict (id) do nothing;

-- ------------------------------------------------------------
-- RLS 策略：登录用户可读写自己的数据，管理员放行全部
-- ------------------------------------------------------------
alter table public.profiles       enable row level security;
alter table public.projects       enable row level security;
alter table public.files          enable row level security;
alter table public.prompts        enable row level security;
alter table public.model_configs  enable row level security;
alter table public.characters     enable row level security;
alter table public.scenes         enable row level security;
alter table public.scripts        enable row level security;
alter table public.storyboards    enable row level security;
alter table public.tasks          enable row level security;

-- profiles：本人可读，本人或管理员可改
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles
  for select to authenticated
  using (id = auth.uid() or public.is_admin());

drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles
  for update to authenticated
  using (id = auth.uid() or public.is_admin())
  with check (id = auth.uid() or public.is_admin());

-- 其余业务表统一：创建者可读写自己的行，管理员全放行
do $$
declare
  t text;
begin
  foreach t in array array[
    'projects', 'files', 'prompts', 'model_configs',
    'characters', 'scenes', 'scripts', 'storyboards', 'tasks'
  ]
  loop
    execute format('drop policy if exists %I_owner on public.%I', t, t);
    execute format(
      'create policy %I_owner on public.%I for all to authenticated
         using (created_by = auth.uid() or public.is_admin())
         with check (created_by = auth.uid() or public.is_admin())',
      t, t
    );
  end loop;
end;
$$;

-- ------------------------------------------------------------
-- Storage 策略
-- ------------------------------------------------------------
drop policy if exists media_public_read on storage.objects;
create policy media_public_read on storage.objects
  for select to public
  using (bucket_id = 'media');

drop policy if exists media_auth_insert on storage.objects;
create policy media_auth_insert on storage.objects
  for insert to authenticated
  with check (bucket_id = 'media');

drop policy if exists media_owner_update on storage.objects;
create policy media_owner_update on storage.objects
  for update to authenticated
  using (bucket_id = 'media' and owner = auth.uid())
  with check (bucket_id = 'media' and owner = auth.uid());

drop policy if exists media_owner_delete on storage.objects;
create policy media_owner_delete on storage.objects
  for delete to authenticated
  using (bucket_id = 'media' and (owner = auth.uid() or public.is_admin()));

-- ------------------------------------------------------------
-- 默认模型唯一：同类型只允许一个 is_default
-- ------------------------------------------------------------
create unique index if not exists uq_model_configs_default
  on public.model_configs (model_type) where is_default;
