-- ============================================================
-- V2.0 结构化改造（内容故事 → 剧本二次生成）
--
-- 1. prompts.prompt_type 增加 STORY_CONTENT（内容故事）
-- 2. scripts 增加 story_prompt_id（引用的内容故事）
-- 3. storyboards 增加 plot（本段剧情）/ subject_action（本段主体动作），
--    语义调整为「分镜段」（每条 10 秒）
-- 4. 新增 storyboard_shots 表：段 → 镜头 两级结构
--    每段 1~2 个镜头，段内时长均分
--
-- 幂等：可重复执行。
-- ============================================================

-- ------------------------------------------------------------
-- 1. prompts.prompt_type 枚举扩容
--    约束名可能随建表方式变化，这里扫描 pg_constraint 精确删除，
--    避免残留旧约束导致 STORY_CONTENT 仍被拒绝。
-- ------------------------------------------------------------
do $$
declare
  c record;
begin
  for c in
    select conname
    from pg_constraint
    where conrelid = 'public.prompts'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%prompt_type%'
  loop
    execute format('alter table public.prompts drop constraint %I', c.conname);
  end loop;
end;
$$;

alter table public.prompts
  add constraint prompts_prompt_type_check
  check (prompt_type in (
    'CHARACTER', 'SCENE', 'SCRIPT', 'STORYBOARD', 'VIDEO', 'CUSTOM',
    'STORY_CONTENT'
  ));

comment on column public.prompts.prompt_type is
  '提示词类型：CHARACTER 角色三视图 / SCENE 场景 / STORY_CONTENT 内容故事 / SCRIPT 剧本 / STORYBOARD 分镜 / VIDEO 视频 / CUSTOM 自定义';

-- ------------------------------------------------------------
-- 2. scripts 关联「内容故事」
-- ------------------------------------------------------------
alter table public.scripts
  add column if not exists story_prompt_id bigint
    references public.prompts (id) on delete set null;

comment on column public.scripts.story_prompt_id is
  '生成本剧本所依据的「内容故事」提示词；老剧本可能为空（不支持重新生成）';

create index if not exists ix_scripts_story_prompt on public.scripts (story_prompt_id);

-- ------------------------------------------------------------
-- 3. storyboards 升级为「分镜段」
-- ------------------------------------------------------------
alter table public.storyboards
  add column if not exists plot text;

alter table public.storyboards
  add column if not exists subject_action text;

comment on column public.storyboards.plot is '本段剧情';
comment on column public.storyboards.subject_action is '本段主体动作';
comment on column public.storyboards.description is '本段画面描述';
comment on column public.storyboards.video_prompt is
  '提交给视频模型的提示词（已按固定前缀 + 固定结尾拼装，≤150 字符）';

-- ------------------------------------------------------------
-- 4. storyboard_shots：段内镜头
-- ------------------------------------------------------------
create table if not exists public.storyboard_shots (
  id bigserial primary key,
  storyboard_id bigint not null references public.storyboards (id) on delete cascade,
  project_id bigint references public.projects (id) on delete cascade,
  sequence integer not null default 1,
  description text,
  duration double precision,
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.storyboard_shots is
  '分镜段内的镜头；每段 1~2 个，段内时长均分（段 10 秒 → 每镜头 5 秒或 10 秒）';

create index if not exists ix_storyboard_shots_storyboard on public.storyboard_shots (storyboard_id);
create index if not exists ix_storyboard_shots_project on public.storyboard_shots (project_id);

drop trigger if exists trg_storyboard_shots_touch on public.storyboard_shots;
create trigger trg_storyboard_shots_touch before update on public.storyboard_shots
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- 5. RLS：按 created_by 隔离（与其他资源一致，无共享）
-- ------------------------------------------------------------
alter table public.storyboard_shots enable row level security;

drop policy if exists storyboard_shots_owner on public.storyboard_shots;
create policy storyboard_shots_owner on public.storyboard_shots
  for all to authenticated
  using (created_by = auth.uid() or public.is_admin())
  with check (created_by = auth.uid() or public.is_admin());

-- 顺带把新表纳入统一的删除/查询权限
grant select, insert, update, delete on public.storyboard_shots to authenticated;
grant usage, select on sequence public.storyboard_shots_id_seq to authenticated;
