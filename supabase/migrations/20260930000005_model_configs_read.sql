-- ============================================================
-- 修复：模型配置改为全局可读
--
-- 背景：
--   原 001_init.sql 把 model_configs 与业务表统一套用了
--   「created_by = auth.uid() or is_admin()」策略，
--   导致普通用户读不到管理员配置的模型，
--   在「模型管理」页是空列表，生成剧本时也选不到模型 → 功能不可用。
--
-- 修正：
--   模型是全局共享资源 —— 所有登录用户可读，仅创建者/管理员可写。
--   本文件可对已部署的库重复执行（幂等）。
-- ============================================================

-- 移除旧的统一策略
drop policy if exists model_configs_owner on public.model_configs;

-- 读：所有登录用户
drop policy if exists model_configs_read on public.model_configs;
create policy model_configs_read on public.model_configs
  for select to authenticated
  using (true);

-- 写：仅创建者或管理员
drop policy if exists model_configs_write on public.model_configs;
create policy model_configs_write on public.model_configs
  for all to authenticated
  using (created_by = auth.uid() or public.is_admin())
  with check (created_by = auth.uid() or public.is_admin());
